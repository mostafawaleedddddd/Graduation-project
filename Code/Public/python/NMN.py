"""
NMN.py  —  Dynamic Neural Modular Network for ModuVision
=========================================================

Architecture
------------
                         ┌─────────────────────────────┐
  pipeline change  ────► │  set_modules(["A","B","C"])  │  ← builds graph ONCE
                         │  _topological_sort()          │
                         │  _build_stages()              │
                         │  _install_bridges()           │
                         └─────────────┬───────────────┘
                                       │  (graph cached)
                         ┌─────────────▼───────────────┐
  every frame     ────►  │       process(frame)         │
                         │                              │
                         │  Stage 0: [A, B]  ← parallel │
                         │       ▼  composite            │
                         │  Stage 1: [C]     ← serial   │
                         └─────────────────────────────┘

Key Design Decisions
--------------------
1. ZERO model loading per frame.
   Models are injected once at server startup via register().
   set_modules() and process() never touch disk or GPU init paths.

2. Execution graph built ONCE per pipeline change, reused every frame.
   _topological_sort()  →  resolves which module must run before another.
   _build_stages()      →  groups independent modules into parallel stages.

3. Cross-module context (FrameContext).
   Module A writes metadata (bounding boxes, counts …) into a shared dict.
   Module B reads that dict and uses it to process smarter, not just harder.

4. Context bridges.
   When a synergistic pair is active (e.g. Tracking + Attendance),
   _install_bridges() replaces the downstream module's plain process() call
   with a bridge function that wires the upstream context into it.
   Bridge functions live at module scope — easy to add new ones.

5. Parallel stage compositing.
   Modules in the same stage each receive a copy of the current frame,
   run concurrently on the thread pool, and their annotation deltas
   are merged with _composite_overlay() (pixel-wise delta mask).

Adding a new module
-------------------
  1. Add its dependencies to MODULE_DEPS.
  2. If it produces re-usable metadata, add a key to CONTEXT_KEYS and
     write a context_extract_fn.
  3. If it benefits from upstream context, write a bridge function and
     register it in DynamicNMN._install_bridges().
  4. Call nmn.register() in the server with the model instance.

Nothing else changes — set_modules() and process() adapt automatically.
"""

from __future__ import annotations

import logging
import time
import threading
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

import cv2
import numpy as np

logger = logging.getLogger("NMN")

# ─────────────────────────────────────────────────────────────────────────────
# §1  DEPENDENCY MAP
#     Key   = module name (must match the string used in the server pipeline list)
#     Value = list of module names whose output this module wants as context
#             before it runs.  Empty list = no dependencies = earliest stage.
# ─────────────────────────────────────────────────────────────────────────────
MODULE_DEPS: Dict[str, List[str]] = {
    # ── producers (no upstream dependency) ──────────────────────────────────
    "Tracking":           [],
    "Color Detection":    [],
    "Object Counting":    [],
    "Parking Management": [],
    # ── consumers (depend on a producer's context) ───────────────────────────
    "Attendance":         ["Tracking"],         # ROI-guided face search
    "Security":           ["Tracking", "Attendance"],
    "Heatmap":            ["Tracking"],         # centroid-driven accumulation
    "Gap Detection":      ["Object Counting"],  # gap logic enriched by counts
    "Weapon Detection":   ["Tracking"],         # use tracked person boxes to associate weapons with people
    # ── Smart Security: needs Tracking for person ROIs and Attendance for ID ─
    "Smart Security":     ["Tracking", "Attendance"],
}

# ─────────────────────────────────────────────────────────────────────────────
# §2  CONTEXT PROTOCOL
#     The string key each module writes into FrameContext.
#     Downstream modules read these keys — changing them here is a
#     breaking change between producer and consumer.
# ─────────────────────────────────────────────────────────────────────────────
CONTEXT_KEYS: Dict[str, str] = {
    "Tracking":        "tracked_boxes",   # List[Tuple[x1,y1,x2,y2,track_id]]
    "Attendance":      "attendance_info", # Dict[str, Any] from the Attendance model
    "Object Counting": "object_counts",   # Dict[class_name, int]
    "Gap Detection":   "gap_regions",     # List[Tuple[x1,y1,x2,y2]]
}


# ─────────────────────────────────────────────────────────────────────────────
# §3  FRAME CONTEXT  —  thread-safe shared state during one frame's execution
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class FrameContext:
    """
    Lightweight dict-wrapper shared between all modules in one process() call.
    Each frame gets a fresh instance; there is no cross-frame state here.
    """
    data: Dict[str, Any] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self.data[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return self.data.get(key, default)

    def has(self, key: str) -> bool:
        with self._lock:
            return key in self.data


# ─────────────────────────────────────────────────────────────────────────────
# §4  NEURAL MODULE WRAPPER
# ─────────────────────────────────────────────────────────────────────────────
class NeuralModule:
    """
    Wraps one vision model with a standardised call interface.

    raw_process_fn       : callable(frame: np.ndarray) → np.ndarray
                           The model's original process() method (plain, no context).
    context_extract_fn   : optional callable(result_frame, ctx, model) → Any
                           Runs AFTER the model to pull metadata out of the
                           model's internal state and populate FrameContext.
    _bridge              : set by DynamicNMN._install_bridges() when a synergistic
                           pair is active.  Signature:
                           callable(frame, ctx: FrameContext, model) → np.ndarray
    """

    def __init__(
        self,
        name: str,
        model: Any,
        raw_process_fn: Callable[[np.ndarray], np.ndarray],
        context_extract_fn: Optional[Callable] = None,
    ):
        self.name         = name
        self.model        = model
        self._raw_fn      = raw_process_fn
        self._extract_fn  = context_extract_fn
        self._bridge: Optional[Callable] = None

    # called by DynamicNMN._install_bridges
    def set_bridge(self, fn: Optional[Callable]) -> None:
        self._bridge = fn

    def run(self, frame: np.ndarray, ctx: FrameContext) -> np.ndarray:
        # ── 1. Process ───────────────────────────────────────────────────────
        if self._bridge is not None:
            result = self._bridge(frame, ctx, self.model)
        else:
            result = self._raw_fn(frame)

        if result is None:
            result = frame

        # ── 2. Extract metadata into context ─────────────────────────────────
        if self._extract_fn is not None:
            key = CONTEXT_KEYS.get(self.name)
            if key:
                try:
                    meta = self._extract_fn(result, ctx, self.model)
                    if meta is not None:
                        ctx.set(key, meta)
                except Exception as exc:
                    logger.debug("[NMN] %s extract_fn failed: %s", self.name, exc)

        return result


# ─────────────────────────────────────────────────────────────────────────────
# §5  DYNAMIC NMN — the main class
# ─────────────────────────────────────────────────────────────────────────────
class DynamicNMN:
    """
    Register models once.  Tell the NMN which subset to use via set_modules().
    Call process() every frame — zero model loading, graph already built.

    Quick-start
    -----------
        nmn = DynamicNMN()

        # Register all models at server startup:
        nmn.register("Tracking",    tracker,    tracker.process,
                     context_extract_fn=tracking_extractor)
        nmn.register("Attendance",  attendance, attendance.process)
        nmn.register("Object Counting", counter,
                     lambda f: counter.process(f)[0],      # unwrap tuple
                     context_extract_fn=object_count_extractor)
        ...

        # When the pipeline changes:
        nmn.set_modules(["Tracking", "Attendance"])

        # Every frame:
        out = nmn.process(frame)
    """

    def __init__(self, num_workers: int = 4):
        self._modules:  Dict[str, NeuralModule] = {}
        self._order:    List[str]       = []   # topologically sorted active list
        self._stages:   List[List[str]] = []   # parallel groups
        self._lock      = threading.Lock()
        self._executor  = ThreadPoolExecutor(max_workers=num_workers,
                                             thread_name_prefix="NMN")
        self._timing:   Dict[str, float] = {}  # ms per module, last frame

        # Persistent cross-frame identity memory for Attendance+Tracking bridge.
        # track_id -> recognised name; survives across frames so a person stays
        # labelled after the first hit (attendance only logs each name once).
        self.id_to_name_memory: Dict[int, str] = {}

    # ── Registration ──────────────────────────────────────────────────────────

    def register(
        self,
        name: str,
        model: Any,
        raw_process_fn: Callable,
        context_extract_fn: Optional[Callable] = None,
    ) -> None:
        """
        Register one model module.  Call once per model at server startup.
        raw_process_fn must have signature: (frame: np.ndarray) → np.ndarray
        """
        self._modules[name] = NeuralModule(name, model, raw_process_fn,
                                            context_extract_fn)
        logger.info("[NMN] Registered: %s", name)

    # ── Pipeline configuration (called on pipeline change, NOT per frame) ────

    def set_modules(self, names: List[str]) -> None:
        """
        Build (or rebuild) the execution graph for the given module subset.
        Skips names that were never registered — safe to call with the full
        server pipeline list.
        """
        with self._lock:
            active = [n for n in names if n in self._modules]
            self._order  = self._topo_sort(active)
            self._stages = self._build_stages(self._order, set(active))
            self._install_bridges(set(active))

            # Safety: if Tracking is active without Attendance, make sure its
            # labels are always visible (suppress_draw could be True from a
            # previous Tracking+Attendance session) and wipe identity memory.
            if "Tracking" in self._modules and "Attendance" not in set(active):
                tracker = self._modules["Tracking"].model
                if hasattr(tracker, "suppress_draw"):
                    tracker.suppress_draw = False
                self.id_to_name_memory.clear()

            logger.info("[NMN] Graph → stages: %s", self._stages)

    # ── Per-frame entry point ─────────────────────────────────────────────────

    def process(self, frame: np.ndarray) -> np.ndarray:
        """
        Execute the current graph on one frame.
        Thread-safe: reads a snapshot of _stages/_modules under lock,
        then releases the lock for the actual (potentially slow) inference.
        """
        with self._lock:
            stages  = list(self._stages)      # snapshot
            modules = dict(self._modules)     # snapshot (references, not copies)

        if not stages:
            return frame

        ctx     = FrameContext()
        current = frame

        for stage in stages:
            if len(stage) == 1:
                name = stage[0]
                t0   = _now()
                current = modules[name].run(current, ctx)
                self._timing[name] = (_now() - t0) * 1000
            else:
                current = self._run_parallel_stage(stage, current, ctx, modules)

        return current

    # ── Graph building helpers ────────────────────────────────────────────────

    def _topo_sort(self, active: List[str]) -> List[str]:
        """Kahn's algorithm — resolves module execution order by dependency."""
        active_set = set(active)
        in_degree: Dict[str, int] = {n: 0 for n in active}
        adj: Dict[str, List[str]] = defaultdict(list)

        for node in active:
            for dep in MODULE_DEPS.get(node, []):
                if dep in active_set:
                    in_degree[node] += 1
                    adj[dep].append(node)

        queue  = deque(n for n in active if in_degree[n] == 0)
        result: List[str] = []
        while queue:
            node = queue.popleft()
            result.append(node)
            for neighbor in adj[node]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if len(result) != len(active):
            # Cycle guard — shouldn't happen with the static DEPS above
            remaining = set(active) - set(result)
            logger.warning("[NMN] Cycle detected among: %s — appending naively.", remaining)
            result.extend(remaining)

        return result

    def _build_stages(self, ordered: List[str], active_set: set) -> List[List[str]]:
        """
        Assign each module to the earliest stage that respects its dependencies.
        Modules in the same stage are independent and run in parallel.
        """
        stage_of: Dict[str, int] = {}
        for n in ordered:
            deps = [d for d in MODULE_DEPS.get(n, []) if d in active_set]
            stage_of[n] = 0 if not deps else max(stage_of[d] for d in deps) + 1

        if not stage_of:
            return []

        buckets: Dict[int, List[str]] = defaultdict(list)
        for n, s in stage_of.items():
            buckets[s].append(n)

        return [buckets[i] for i in sorted(buckets)]

    def _install_bridges(self, active: set) -> None:
        """
        For every registered synergistic pair that is currently active,
        swap in the context-aware bridge function on the downstream module.
        For modules whose pair is NOT active, restore plain (bridgeless) mode.
        """
        # Attendance ← Tracking
        if "Attendance" in self._modules:
            if "Attendance" in active and "Tracking" in active:
                tracker_model = self._modules["Tracking"].model
                _tm  = tracker_model
                _mem = self.id_to_name_memory   # persistent dict on the NMN instance
                def _attendance_bridge_with_tracker(frame, ctx, model,
                                                     _tracker=_tm, _memory=_mem):
                    ctx.set("_tracker_model",   _tracker)
                    ctx.set("_id_to_name_memory", _memory)
                    return bridge_attendance_tracking(frame, ctx, model)
                self._modules["Attendance"].set_bridge(_attendance_bridge_with_tracker)
                logger.info("[NMN] Bridge installed: Attendance ← Tracking")
            else:
                # Bridge removed — restore normal ID label drawing on the tracker
                self._modules["Attendance"].set_bridge(None)
                self.id_to_name_memory.clear()   # wipe memory when bridge is off
                if "Tracking" in self._modules:
                    tracker = self._modules["Tracking"].model
                    if hasattr(tracker, "suppress_draw"):
                        tracker.suppress_draw = False
                        logger.info("[NMN] suppress_draw reset on Tracking model")

        # Security ← Tracking / Attendance
        if "Security" in self._modules:
            bridge = None
            if "Security" in active:
                if "Tracking" in active and "Attendance" in active:
                    bridge = bridge_security_tracking_and_attendance
                elif "Tracking" in active:
                    bridge = bridge_security_tracking
                elif "Attendance" in active:
                    bridge = bridge_security_attendance
            self._modules["Security"].set_bridge(bridge)
            if bridge:
                logger.info("[NMN] Bridge installed: Security ← Tracking/Attendance")

        # Heatmap ← Tracking
        if "Heatmap" in self._modules:
            bridge = bridge_heatmap_tracking \
                if ("Heatmap" in active and "Tracking" in active) else None
            self._modules["Heatmap"].set_bridge(bridge)
            if bridge:
                logger.info("[NMN] Bridge installed: Heatmap ← Tracking")

        # Weapon Detection ← Tracking
        if "Weapon Detection" in self._modules:
            bridge = bridge_weapon_tracking \
                if ("Weapon Detection" in active and "Tracking" in active) else None
            self._modules["Weapon Detection"].set_bridge(bridge)
            if bridge:
                logger.info("[NMN] Bridge installed: Weapon Detection ← Tracking")

        # Gap Detection ← Object Counting  (context only, no visual bridge needed)
        # The context extractor on Object Counting already writes "object_counts"
        # which GapDetector can read if it checks ctx.get("object_counts").

        # Smart Security ← Tracking + Attendance
        # Needs both upstream modules to be active for full functionality.
        # Works in degraded mode (all unknown) if only Tracking is active.
        if "Smart Security" in self._modules:
            if "Smart Security" in active and "Tracking" in active:
                self._modules["Smart Security"].set_bridge(bridge_smart_security)
                logger.info("[NMN] Bridge installed: Smart Security ← Tracking + Attendance")
            else:
                self._modules["Smart Security"].set_bridge(None)
                # Reset the guard's timer state when it leaves the pipeline
                guard = self._modules["Smart Security"].model
                if guard is not None and hasattr(guard, "reset"):
                    guard.reset()

    # ── Parallel stage execution ──────────────────────────────────────────────

    def _run_parallel_stage(
        self,
        stage: List[str],
        frame: np.ndarray,
        ctx: FrameContext,
        modules: Dict[str, NeuralModule],
    ) -> np.ndarray:
        """
        Each module in this stage runs on its own copy of `frame` concurrently.
        Their annotation deltas are composited onto the base frame.
        Context writes are thread-safe via FrameContext._lock.
        """
        base = frame
        futures = {
            self._executor.submit(modules[n].run, frame.copy(), ctx): n
            for n in stage
        }

        results: Dict[str, np.ndarray] = {}
        for fut, name in futures.items():
            try:
                t0 = _now()
                results[name] = fut.result()
                self._timing[name] = (_now() - t0) * 1000
            except Exception as exc:
                logger.error("[NMN] %s raised during parallel stage: %s", name, exc)
                results[name] = base

        # Composite annotation deltas in registered order (deterministic output)
        composited = base.copy()
        for name in stage:
            if name in results:
                composited = _composite_overlay(composited, base, results[name])

        return composited

    # ── Diagnostics ───────────────────────────────────────────────────────────

    def get_timing(self) -> Dict[str, float]:
        """Returns last-frame inference time in milliseconds per active module."""
        return {k: round(v, 1) for k, v in self._timing.items()}

    def get_graph_info(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "active_order": list(self._order),
                "stages":       [list(s) for s in self._stages],
                "registered":   list(self._modules.keys()),
            }


# ─────────────────────────────────────────────────────────────────────────────
# §6  BRIDGE FUNCTIONS
#     Context-aware replacements for a module's plain process() call.
#     Signature: (frame, ctx: FrameContext, model) → np.ndarray
#
#     These run INSIDE NeuralModule.run() when a synergistic pair is active.
#     They have access to everything the upstream module deposited in ctx.
# ─────────────────────────────────────────────────────────────────────────────

def bridge_attendance_tracking(
    frame: np.ndarray,
    ctx: FrameContext,
    model: Any,
) -> np.ndarray:
    """
    Attendance guided by Tracking — unified bounding-box mode.

    Behaviour
    ---------
    • The tracker body box stays; face boxes drawn by attendance are SUPPRESSED.
    • The body box label shows the recognised name (green) or "UNKNOWN" (orange).
    • Once a track ID is identified, that name STICKS for the rest of the session
      via id_to_name_memory stored on the DynamicNMN instance — because the
      attendance model only fires once per person (marked_names dedup).

    Falls back to full-frame attendance if no tracked boxes are available.
    """
    tracked_boxes = ctx.get("tracked_boxes", [])

    if not tracked_boxes:
        return model.process(frame)

    # ── Suppress tracker ID labels — bridge will draw names instead ──────────
    tracker_model = ctx.get("_tracker_model")
    if tracker_model is not None:
        tracker_model.suppress_draw = True

    # ── Grab the persistent memory dict from the NMN instance ────────────────
    # Injected into ctx by the wrapper closure in _install_bridges.
    memory: dict = ctx.get("_id_to_name_memory")  # track_id → name, persists across frames
    if memory is None:
        memory = {}  # safety fallback (should never happen)

    # ── Parse tracked box entries ─────────────────────────────────────────────
    def _parse_entry(entry):
        if len(entry) == 2:
            tid, coords = entry
            return int(tid), *map(int, coords)
        x1, y1, x2, y2 = map(int, entry[:4])
        tid = int(entry[4]) if len(entry) > 4 else -1
        return tid, x1, y1, x2, y2

    active_ids = set()

    for entry in tracked_boxes:
        try:
            track_id, x1, y1, x2, y2 = _parse_entry(entry)
        except Exception as exc:
            logger.debug("[NMN] attendance_bridge parse error: %s", exc)
            continue

        active_ids.add(track_id)

        # ── Already identified this track — skip recognition, keep name ──────
        if track_id in memory:
            continue

        # ── Crop the head region for face recognition ─────────────────────────
        h, w = y2 - y1, x2 - x1
        pad_top  = int(h * 0.5)
        pad_side = int(w * 0.1)
        cy1 = max(0, y1 - pad_top)
        cy2 = min(frame.shape[0], y2)
        cx1 = max(0, x1 - pad_side)
        cx2 = min(frame.shape[1], x2 + pad_side)

        if (cx2 - cx1) < 40 or (cy2 - cy1) < 40:
            continue  # crop too small — leave unidentified for now

        # ── Run attendance on throw-away crop and inspect latest recognition
        crop_copy = frame[cy1:cy2, cx1:cx2].copy()
        model.process(crop_copy, force=True)
        recognitions = getattr(model, "last_attendance_info", {}).get("recognitions", [])

        if recognitions:
            recognised_name = recognitions[-1].get("name", "UNKNOWN").upper()
            if recognised_name != "UNKNOWN":
                memory[track_id] = recognised_name
                logger.debug("[NMN] Track %s identified as %s", track_id, recognised_name)

    # ── Purge IDs that are no longer tracked (track lost / left frame) ────────
    stale = [tid for tid in memory if tid not in active_ids]
    for tid in stale:
        del memory[tid]

    # ── Store resolved mapping in ctx for other modules ───────────────────────
    ctx.set("id_to_name", dict(memory))

    # ── Redraw body boxes with names ──────────────────────────────────────────
    result = frame.copy()
    for entry in tracked_boxes:
        try:
            track_id, x1, y1, x2, y2 = _parse_entry(entry)
        except Exception:
            continue

        name  = memory.get(track_id, "UNKNOWN")
        color = (0, 255, 0) if name != "UNKNOWN" else (0, 165, 255)  # green / orange

        cv2.rectangle(result, (x1, y1), (x2, y2), color, 2)
        cv2.putText(
            result, name, (x1, y1 - 6),
            cv2.FONT_HERSHEY_SIMPLEX, 0.60, color, 2,
        )

    return result


def bridge_security_tracking(
    frame: np.ndarray,
    ctx: FrameContext,
    model: Any,
) -> np.ndarray:
    """
    Security guided by Tracking.

    Passes tracked person ROIs to the security model when it exposes a
    process_with_rois() method.  Falls back to plain process() gracefully.
    This lets the security model focus anomaly detection on known person
    regions rather than scanning the whole frame.
    """
    tracked_boxes = ctx.get("tracked_boxes", [])

    if tracked_boxes and hasattr(model, "process_with_rois"):
        try:
            return model.process_with_rois(frame, tracked_boxes)
        except Exception as exc:
            logger.debug("[NMN] security_bridge process_with_rois failed: %s", exc)

    # Graceful fallback: tracking annotations already on frame from Stage 0
    return model.process(frame)


def bridge_security_attendance(
    frame: np.ndarray,
    ctx: FrameContext,
    model: Any,
) -> np.ndarray:
    """
    Security guided by Attendance.

    If the security model exposes process_with_context or
    process_with_attendance, pass the attendance results through.
    Otherwise fall back to the standard Security.process() path.
    """
    attendance_info = ctx.get("attendance_info", {})

    if hasattr(model, "process_with_context"):
        try:
            return model.process_with_context(frame, [], attendance_info)
        except Exception as exc:
            logger.debug("[NMN] security_bridge_attendance process_with_context failed: %s", exc)

    if hasattr(model, "process_with_attendance"):
        try:
            return model.process_with_attendance(frame, attendance_info)
        except Exception as exc:
            logger.debug("[NMN] security_bridge_attendance process_with_attendance failed: %s", exc)

    return model.process(frame)


def bridge_security_tracking_and_attendance(
    frame: np.ndarray,
    ctx: FrameContext,
    model: Any,
) -> np.ndarray:
    """
    Security guided by both Tracking and Attendance.
    """
    tracked_boxes = ctx.get("tracked_boxes", [])
    attendance_info = ctx.get("attendance_info", {})

    if hasattr(model, "process_with_context"):
        try:
            return model.process_with_context(frame, tracked_boxes, attendance_info)
        except Exception as exc:
            logger.debug("[NMN] security_bridge_combined process_with_context failed: %s", exc)

    if hasattr(model, "process_with_attendance"):
        try:
            return model.process_with_attendance(frame, attendance_info)
        except Exception as exc:
            logger.debug("[NMN] security_bridge_combined process_with_attendance failed: %s", exc)

    if tracked_boxes and hasattr(model, "process_with_rois"):
        try:
            return model.process_with_rois(frame, tracked_boxes)
        except Exception as exc:
            logger.debug("[NMN] security_bridge_combined process_with_rois failed: %s", exc)

    return model.process(frame)


def bridge_heatmap_tracking(
    frame: np.ndarray,
    ctx: FrameContext,
    model: Any,
) -> np.ndarray:
    """
    Heatmap driven by Tracking centroids.

    Injects the precise centroid of every tracked person into the heatmap
    accumulator before the model renders the overlay.  This suppresses the
    noise that comes from raw detection jitter and produces smoother hotspots.
    """
    tracked_boxes = ctx.get("tracked_boxes", [])

    if tracked_boxes and hasattr(model, "update_centroids"):
        centroids = []
        for box in tracked_boxes:
            try:
                cx = int((box[0] + box[2]) / 2)
                cy = int((box[1] + box[3]) / 2)
                centroids.append((cx, cy))
            except Exception:
                continue
        if centroids:
            try:
                model.update_centroids(centroids)
            except Exception as exc:
                logger.debug("[NMN] heatmap_bridge update_centroids failed: %s", exc)

    return model.process(frame)


def bridge_weapon_tracking(
    frame: np.ndarray,
    ctx: FrameContext,
    model: Any,
) -> np.ndarray:
    """
    Weapon Detection guided by Tracking.

    If the weapon detector supports process_with_context, pass person boxes
    from the tracker so weapons can be associated with track IDs.
    """
    tracked_boxes = ctx.get("tracked_boxes", [])

    if tracked_boxes and hasattr(model, "process_with_context"):
        try:
            return model.process_with_context(frame, tracked_boxes)
        except Exception as exc:
            logger.debug("[NMN] weapon_bridge process_with_context failed: %s", exc)

    return model.process(frame)


# ─────────────────────────────────────────────────────────────────────────────
# §7  CONTEXT EXTRACTOR HELPERS
#     Passed as context_extract_fn when calling nmn.register().
#     Signature: (result_frame, ctx: FrameContext, model) → Any
#     The return value is stored under CONTEXT_KEYS[module_name].
# ─────────────────────────────────────────────────────────────────────────────

def tracking_extractor(
    result_frame: np.ndarray,
    ctx: FrameContext,
    model: Any,
) -> Optional[List[Tuple]]:
    """
    Pull bounding boxes + IDs from HumanTracker's internal state.

    get_tracks() returns List[Tuple[track_id, [x1,y1,x2,y2]]].
    The bridge_attendance_tracking function reads entries in this format.
    """
    try:
        if hasattr(model, "get_tracks"):
            tracks = model.get_tracks()
            return tracks if tracks else []
    except Exception as exc:
        logger.debug("[NMN] tracking_extractor error: %s", exc)
    return []


def object_count_extractor(
    result_frame: np.ndarray,
    ctx: FrameContext,
    model: Any,
) -> Optional[Dict[str, int]]:
    """
    Pull class counts from ObjectCounterBlock's internal state.

    Requires ObjectCounterBlock to expose:
        get_counts() → Dict[class_name, int]
    """
    try:
        if hasattr(model, "get_counts"):
            counts = model.get_counts()
            return counts if counts else {}
    except Exception as exc:
        logger.debug("[NMN] object_count_extractor error: %s", exc)
    return {}


def attendance_extractor(
    result_frame: np.ndarray,
    ctx: FrameContext,
    model: Any,
) -> Dict[str, Any]:
    """
    Extract the latest attendance recognition results from the Attendance model.
    """
    try:
        return getattr(model, "last_attendance_info", {}) or {}
    except Exception as exc:
        logger.debug("[NMN] attendance_extractor failed: %s", exc)
    return {}


# ─────────────────────────────────────────────────────────────────────────────
# §8  FRAME COMPOSITING
#     Merges annotation layers from parallel modules without doubling
#     background colours or washing out overlapping annotations.
# ─────────────────────────────────────────────────────────────────────────────

def _composite_overlay(
    target: np.ndarray,
    original: np.ndarray,
    annotated: np.ndarray,
    alpha: float = 1.0,
) -> np.ndarray:
    """
    Extract the 'annotation delta' (pixels changed vs. original) from
    `annotated` and paint them onto `target`.

    This lets multiple parallel modules each annotate their own copy of the
    frame and then be merged cleanly — shared pixels are not double-written.

    alpha < 1.0 → semi-transparent blend (useful for overlays like heatmaps).
    """
    # Boolean mask: True where this module changed the pixel
    diff = annotated.astype(np.int16) - original.astype(np.int16)
    mask = np.any(diff != 0, axis=2)

    if not mask.any():
        return target   # module produced no annotations

    out = target.copy()
    if alpha >= 1.0:
        out[mask] = annotated[mask]
    else:
        blended = (
            target[mask].astype(np.float32) * (1.0 - alpha)
            + annotated[mask].astype(np.float32) * alpha
        )
        out[mask] = np.clip(blended, 0, 255).astype(np.uint8)

    return out


def _now() -> float:
    return time.perf_counter()


# ─────────────────────────────────────────────────────────────────────────────
# §9  SMART SECURITY GUARD
#
#     A lightweight state machine that sits on top of the Attendance model.
#     It reuses the face-recognition work already done by the Attendance bridge
#     (id_to_name_memory) and adds:
#
#       • Per-track UNKNOWN timers  — a person must be continuously unrecognised
#         for UNKNOWN_ALERT_SECONDS before an alert fires.
#       • One-shot alerting         — once an alert has been sent for a given
#         intrusion window, no second email is sent until the person leaves and
#         re-enters (track ID disappears from the scene and comes back).
#       • Graceful fallback         — if Attendance context is absent the guard
#         treats every tracked person as UNKNOWN (fail-secure).
#       • Thread-safe               — all mutable state is protected by a lock
#         so the guard can be called from the NMN thread pool.
#
#     The guard does NOT load any model — it reads the id_to_name_memory dict
#     that bridge_attendance_tracking already maintains and calls
#     send_security_alert_async from security.py.
# ─────────────────────────────────────────────────────────────────────────────

UNKNOWN_ALERT_SECONDS: float = 5.0   # consecutive seconds before alert fires


class SmartSecurityGuard:
    """
    Fuses Attendance recognition with time-gated, one-shot intrusion alerting.

    Registration (Server.py)
    ------------------------
        guard = SmartSecurityGuard(receiver_email=user_email)
        nmn.register(
            "Smart Security",
            guard,
            raw_process_fn=guard.process,
        )
        # Add "Smart Security" to NMN_TRIGGER_SETS as needed.

    The guard's process() is normally called via bridge_smart_security (below),
    which injects Tracking + Attendance context before the call.
    """

    def __init__(
        self,
        receiver_email: str | None = None,
        unknown_alert_seconds: float = UNKNOWN_ALERT_SECONDS,
        enable_email_alerts: bool = True,
    ):
        self.receiver_email        = receiver_email
        self.unknown_alert_seconds = unknown_alert_seconds
        self.enable_email_alerts   = enable_email_alerts

        # track_id → wall-clock time when this track first became UNKNOWN
        self._unknown_since: Dict[int, float] = {}

        # track_id → True once an alert has been sent for this intrusion window
        self._alerted: Dict[int, bool] = {}

        self._lock = threading.Lock()

        # Public log (mirrors SecuritySystem.alert_log style)
        self.alert_log: deque = deque(maxlen=100)

    # ── Public API ────────────────────────────────────────────────────────────

    def set_receiver_email(self, email: str | None) -> None:
        self.receiver_email = email
        logger.info("[SmartSecurity] Alert recipient: %s", email or "none")

    def get_results(self) -> list:
        with self._lock:
            return list(self.alert_log)

    def reset(self) -> None:
        with self._lock:
            self._unknown_since.clear()
            self._alerted.clear()
            self.alert_log.clear()
        logger.info("[SmartSecurity] State reset.")

    # ── Core frame processor ──────────────────────────────────────────────────

    def process(self, frame: np.ndarray) -> np.ndarray:
        """
        Plain (bridge-less) fallback: no context available → treat all pixels
        as a single unknown region, which is unhelpful.  In practice this is
        always called via bridge_smart_security which injects context first.
        """
        return frame   # nothing to do without context

    def process_with_context(
        self,
        frame: np.ndarray,
        tracked_boxes: list,
        id_to_name: Dict[int, str],
    ) -> np.ndarray:
        """
        The real entry point, called by bridge_smart_security.

        Parameters
        ----------
        frame        : current BGR frame (will be annotated in place on a copy)
        tracked_boxes: list of (track_id, [x1,y1,x2,y2]) or (x1,y1,x2,y2,tid)
        id_to_name   : mapping of track_id → recognised name (or absent = UNKNOWN)
        """
        now    = time.perf_counter()
        result = frame.copy()

        # ── Helper: parse heterogeneous box formats ───────────────────────────
        def _parse(entry):
            if len(entry) == 2:
                tid, coords = entry
                x1, y1, x2, y2 = map(int, coords)
            else:
                x1, y1, x2, y2 = map(int, entry[:4])
                tid = int(entry[4]) if len(entry) > 4 else -1
            return int(tid), x1, y1, x2, y2

        active_ids: set = set()

        with self._lock:
            for entry in tracked_boxes:
                try:
                    tid, x1, y1, x2, y2 = _parse(entry)
                except Exception as exc:
                    logger.debug("[SmartSecurity] parse error: %s", exc)
                    continue

                active_ids.add(tid)

                name      = id_to_name.get(tid, "UNKNOWN")
                is_known  = (name != "UNKNOWN")

                # ── KNOWN person: clear any pending unknown timer ─────────────
                if is_known:
                    self._unknown_since.pop(tid, None)
                    self._alerted.pop(tid, None)
                    color  = (0, 220, 0)
                    label  = f"✓ {name}"

                # ── UNKNOWN person: start / advance timer ─────────────────────
                else:
                    if tid not in self._unknown_since:
                        self._unknown_since[tid] = now
                        logger.debug("[SmartSecurity] Track %d: unknown timer started", tid)

                    elapsed = now - self._unknown_since[tid]
                    remaining = max(0.0, self.unknown_alert_seconds - elapsed)

                    if elapsed >= self.unknown_alert_seconds:
                        color = (0, 0, 255)         # red — alert threshold reached
                        label = "⚠ INTRUDER"

                        # One-shot: fire only once per intrusion window
                        if not self._alerted.get(tid, False):
                            self._alerted[tid] = True
                            self._fire_alert(frame, tid, x1, y1, x2, y2)
                    else:
                        color = (0, 140, 255)       # orange — timer counting down
                        label = f"? UNKNOWN ({remaining:.1f}s)"

                # ── Annotate the bounding box ─────────────────────────────────
                cv2.rectangle(result, (x1, y1), (x2, y2), color, 2)
                cv2.putText(
                    result, label, (x1, y1 - 8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.60, color, 2,
                )

            # ── Purge stale tracks (person left the frame) ────────────────────
            stale = [tid for tid in list(self._unknown_since) if tid not in active_ids]
            for tid in stale:
                del self._unknown_since[tid]
                self._alerted.pop(tid, None)

        return result

    # ── Internal alert dispatcher ─────────────────────────────────────────────

    def _fire_alert(
        self,
        frame: np.ndarray,
        track_id: int,
        x1: int, y1: int, x2: int, y2: int,
    ) -> None:
        """Send the intrusion email in a daemon thread (non-blocking)."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.alert_log.append({
            "timestamp": timestamp,
            "track_id":  track_id,
            "message":   f"Unrecognised person (track {track_id}) detected for "
                         f"{self.unknown_alert_seconds:.0f}+ consecutive seconds.",
        })
        logger.info(
            "[SmartSecurity] 🚨 Intruder alert — track %d @ %s", track_id, timestamp
        )
        print(f"🚨 [SmartSecurity] Intruder alert: track {track_id} at {timestamp}")

        if not self.enable_email_alerts or not self.receiver_email:
            logger.warning(
                "[SmartSecurity] Email alerts disabled or no recipient set. Skipping."
            )
            return

        # Crop the person ROI for the alert image
        crop = frame[max(0, y1):y2, max(0, x1):x2].copy() if frame is not None else None

        # Import lazily so the guard can exist without security.py if needed
        try:
            from security import send_security_alert_async
            import threading as _threading
            _threading.Thread(
                target=send_security_alert_async,
                kwargs={
                    "people_count":   1,
                    "frame":          crop,
                    "receiver_email": self.receiver_email,
                },
                daemon=True,
            ).start()
        except ImportError as exc:
            logger.error("[SmartSecurity] Could not import send_security_alert_async: %s", exc)


# ─────────────────────────────────────────────────────────────────────────────
# §10  BRIDGE: Smart Security ← Tracking + Attendance
# ─────────────────────────────────────────────────────────────────────────────

def bridge_smart_security(
    frame: np.ndarray,
    ctx: FrameContext,
    model: "SmartSecurityGuard",
) -> np.ndarray:
    """
    Injects Tracking boxes and Attendance identity mappings into
    SmartSecurityGuard.process_with_context().

    Context keys consumed
    ---------------------
    "tracked_boxes"   — written by tracking_extractor (§7)
    "id_to_name"      — written by bridge_attendance_tracking (§6)
                        Falls back to {} if Attendance is not in the pipeline
                        (in which case every tracked person is treated as UNKNOWN).
    """
    tracked_boxes = ctx.get("tracked_boxes", [])
    id_to_name    = ctx.get("id_to_name",    {})   # {} = all unknown (fail-secure)

    if not tracked_boxes:
        # No tracking data yet — nothing to guard
        return frame

    return model.process_with_context(frame, tracked_boxes, id_to_name)