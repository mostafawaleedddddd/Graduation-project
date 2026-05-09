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
    "Security":           ["Tracking"],         # focus on person regions
    "Heatmap":            ["Tracking"],         # centroid-driven accumulation
    "Gap Detection":      ["Object Counting"],  # gap logic enriched by counts
}

# ─────────────────────────────────────────────────────────────────────────────
# §2  CONTEXT PROTOCOL
#     The string key each module writes into FrameContext.
#     Downstream modules read these keys — changing them here is a
#     breaking change between producer and consumer.
# ─────────────────────────────────────────────────────────────────────────────
CONTEXT_KEYS: Dict[str, str] = {
    "Tracking":        "tracked_boxes",   # List[Tuple[x1,y1,x2,y2,track_id]]
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
            bridge = bridge_attendance_tracking \
                if ("Attendance" in active and "Tracking" in active) else None
            self._modules["Attendance"].set_bridge(bridge)
            if bridge:
                logger.info("[NMN] Bridge installed: Attendance ← Tracking")

        # Security ← Tracking
        if "Security" in self._modules:
            bridge = bridge_security_tracking \
                if ("Security" in active and "Tracking" in active) else None
            self._modules["Security"].set_bridge(bridge)
            if bridge:
                logger.info("[NMN] Bridge installed: Security ← Tracking")

        # Heatmap ← Tracking
        if "Heatmap" in self._modules:
            bridge = bridge_heatmap_tracking \
                if ("Heatmap" in active and "Tracking" in active) else None
            self._modules["Heatmap"].set_bridge(bridge)
            if bridge:
                logger.info("[NMN] Bridge installed: Heatmap ← Tracking")

        # Gap Detection ← Object Counting  (context only, no visual bridge needed)
        # The context extractor on Object Counting already writes "object_counts"
        # which GapDetector can read if it checks ctx.get("object_counts").

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
    Attendance guided by Tracking.

    Instead of running face recognition on the entire 640×480 frame, we crop
    each tracked person's bounding box (padded upward to include the head),
    run attendance on that crop, and paste the annotated crop back.

    Why this is faster / more accurate
    -----------------------------------
    • Face detector sees a tight crop → fewer false positives from background.
    • InsightFace embedding runs on ~100×150 px instead of 640×480 → ~18× less
      pixel area per person when there are several people in frame.
    • Falls back to full-frame processing if tracking context is absent.
    """
    tracked_boxes: List[Tuple] = ctx.get("tracked_boxes", [])

    if not tracked_boxes:
        # No tracking data yet (first few frames) — run normally
        return model.process(frame)

    result = frame.copy()
    processed_any = False

    for box in tracked_boxes:
        try:
            x1, y1, x2, y2 = int(box[0]), int(box[1]), int(box[2]), int(box[3])
            h   = y2 - y1
            w   = x2 - x1
            # Extend upward by one head-height to ensure the face is in crop
            pad_top = int(h * 0.5)
            pad_side = int(w * 0.1)

            cy1 = max(0, y1 - pad_top)
            cy2 = min(frame.shape[0], y2)
            cx1 = max(0, x1 - pad_side)
            cx2 = min(frame.shape[1], x2 + pad_side)

            if (cx2 - cx1) < 40 or (cy2 - cy1) < 40:
                continue   # crop too small for face recognition

            crop          = frame[cy1:cy2, cx1:cx2]
            annotated     = model.process(crop)
            if annotated is not None:
                result[cy1:cy2, cx1:cx2] = annotated
                processed_any = True

        except Exception as exc:
            logger.debug("[NMN] attendance_bridge box error: %s", exc)
            continue

    if not processed_any:
        # Every crop was too small or failed — full-frame fallback
        return model.process(frame)

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
    Pull bounding boxes from HumanTracker's internal state.

    Requires HumanTracker to expose:
        get_tracks() → List[Tuple[x1, y1, x2, y2, track_id]]

    If the method is absent, returns an empty list (no cross-module benefit,
    but nothing breaks — other modules just skip context-guided paths).

    HOW TO ADD get_tracks() TO YOUR HumanTracker
    ---------------------------------------------
    In human_tracking.py, keep a list that is populated inside process():

        self._last_tracks = []   # in __init__

        # at the end of process(), after YOLO/ByteTrack returns boxes:
        self._last_tracks = [(x1, y1, x2, y2, tid) for (x1,y1,x2,y2,tid) in track_results]

        def get_tracks(self):
            return list(self._last_tracks)   # shallow copy for thread safety
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
