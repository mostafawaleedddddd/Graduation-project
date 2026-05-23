import os
import cv2
import time
import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI, UploadFile, File, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from ultralytics import YOLO

# --- YOUR ORIGINAL IMPORTS ---
from color_detection_pi import apply_color_detection
from human_tracking import HumanTracker
from object_countingtry import ObjectCounterBlock
from two_models import DualModelObjectCounter
from shelf_gap_detect_images import ShelfGapDetector
from attendence import AttendanceSystem
from security import SecuritySystem
from car_parking import ParkingSlotDetector
from heatmap_ipcam import HeatmapBlock
from NMN1 import ShelfOrchestrator
from fire_detection import FireSmokeDetector
from weapon_detection import WeaponDetector                          # ── NEW ──

# ── Dynamic NMN ──────────────────────────────────────────────────────────────
from NMN import (
    DynamicNMN,
    tracking_extractor,
    object_count_extractor,
    attendance_extractor,
    SmartSecurityGuard   
)

# ─── Thread pool for JPEG encoding (keeps async loop free) ───────────────────
_encode_executor = ThreadPoolExecutor(max_workers=6)

def _frame_only(result):
    """Normalize model outputs so the streaming pipeline always receives a frame."""
    if isinstance(result, tuple):
        return result[0]
    return result


def _encode_frame(frame, quality: int = 75):
    """Synchronous JPEG encode — called via run_in_executor."""
    ret, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
    return buffer.tobytes() if ret else None


def _open_capture(url: str) -> cv2.VideoCapture:
    """
    Open a VideoCapture with settings that prevent the libavutil
    'Assertion val || !min_size failed' crash under memory pressure.

    Root cause: FFmpeg's default UDP transport drops/corrupts packets when
    the system is busy (e.g. two cameras + heavy GPU model), causing it to
    try to allocate a zero-size decode buffer → hard C assertion failure.

    Fixes applied:
      • rtsp_transport=tcp  — TCP never drops packets mid-stream
      • buffer_size=65536   — small network buffer, avoids stale data
      • stimeout=3000000    — 3 s socket timeout so hung reads don't block
      • CAP_PROP_BUFFERSIZE=1 — keep only the latest decoded frame in memory
    """
    url_str = str(url)
    if url_str.startswith("rtsp://"):
        # Pass FFmpeg options via the GStreamer/FFmpeg environment string
        os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = (
            "rtsp_transport;tcp|"
            "buffer_size;65536|"
            "stimeout;3000000"
        )
        cap = cv2.VideoCapture(url_str, cv2.CAP_FFMPEG)
    else:
        cap = cv2.VideoCapture(url_str)

    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    cap.set(cv2.CAP_PROP_FPS, 30)
    return cap


# ─── Atomic frame store ───────────────────────────────────────────────────────
class AtomicFrame:
    def __init__(self):
        self._frame = None
        self._lock  = threading.Lock()
        self._event = threading.Event()

    def put(self, frame):
        with self._lock:
            self._frame = frame
        self._event.set()

    def get(self, timeout: float = 1.0):
        if self._event.wait(timeout):
            self._event.clear()
            with self._lock:
                return self._frame
        return None

    def get_nowait(self):
        with self._lock:
            return self._frame

    @property
    def ready(self):
        return self._frame is not None


# ─── Frame-skip config ────────────────────────────────────────────────────────
HEAVY_MODELS = {"Attendance", "Security", "Shelf Orchestrator", "Gap Detection", "Heatmap"}
SKIP_N       = 2

# ─── NMN is active when this set of module names is the pipeline ─────────────
#     Extend this set to test additional combinations in the future.
NMN_TRIGGER_SETS = [
    {"Attendance", "Tracking"},           
    {"Security",   "Tracking"},           
    {"Security",   "Attendance"},
    {"Heatmap",    "Tracking"},           
    {"Attendance", "Security", "Tracking"},
    {"Smart Security", "Tracking"}
    
]


def _pipeline_uses_nmn(pipeline: list) -> bool:
    
    pipeline_set = set(pipeline)
    return any(trigger <= pipeline_set for trigger in NMN_TRIGGER_SETS)


class LiveStreamServer:

    def __init__(self):
        self.app = FastAPI()

        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_methods=["*"],
            allow_headers=["*"],
        )

        # ================= 1. GPU MODEL INITIALIZATION =================
        print("🚀 Initializing GPU Models for ModuVision...")

        self.model = YOLO("yolov8s.pt")
        self.model.to("cuda")

        self.human_tracker       = HumanTracker()
        self.object_counter      = ObjectCounterBlock()
        self.dual_counter        = DualModelObjectCounter()
        self.gap_detector        = ShelfGapDetector()
        self.attendance          = AttendanceSystem()
        self.security            = SecuritySystem()
        self.parking_model       = ParkingSlotDetector()
        self.heatmap             = HeatmapBlock()
        self.shelf_orchestrator  = ShelfOrchestrator()
        self.fire_smoke_detector = FireSmokeDetector()
        self.weapon_detector     = WeaponDetector(weights="weapon_best.pt")  # ── NEW ──

        # ================= PER-CAMERA MODEL INSTANCES =================
        # Models that are NOT thread-safe (e.g. any YOLO-based detector)
        # must have one instance per camera stream to avoid concurrent
        # GPU tensor collisions.  We lazily create and cache them here.
        # Key: camera_id  →  Value: dict of { step_name: model_instance }
        self._per_camera_models: dict[str, dict] = {}
        self._per_camera_nmn: dict[str, DynamicNMN] = {}
        self._per_camera_lock = threading.RLock()

        # ================= 2. DYNAMIC NMN SETUP =================
        # Models are injected ONCE here — NMN never loads them again.
        # raw_process_fn wraps each model's existing .process() signature.
        # context_extract_fn pulls metadata after inference (optional).
        print("🧩 Initialising Dynamic NMN...")
        self.nmn = DynamicNMN(num_workers=4)

        self.nmn.register(
            "Tracking",
            self.human_tracker,
            raw_process_fn=self.human_tracker.process,
            context_extract_fn=tracking_extractor,
        )

        self.nmn.register(
            "Attendance",
            self.attendance,
            raw_process_fn=self.attendance.process,
            context_extract_fn=attendance_extractor,
        )

        self.nmn.register(
            "Security",
            self.security,
            raw_process_fn=self.security.process,
        )

        self.nmn.register(
            "Heatmap",
            self.heatmap,
            raw_process_fn=self.heatmap.process,
        )

        self.nmn.register(
            "Object Counting",
            self.object_counter,
            # ObjectCounterBlock.process() returns (frame, _) — unwrap the tuple.
            raw_process_fn=lambda f: self.object_counter.process(f)[0],
            context_extract_fn=object_count_extractor,
        )

        self.nmn.register(
            "Gap Detection",
            self.gap_detector,
            raw_process_fn=self.gap_detector.process,
        )

        self.nmn.register(
            "Color Detection",
            None,                           # stateless helper, no model object
            raw_process_fn=apply_color_detection,
        )

        self.nmn.register(
            "Parking Management",
            self.parking_model,
            raw_process_fn=lambda f: _frame_only(self.parking_model.process(f)),
        )

        self.smart_security_guard = SmartSecurityGuard(enable_email_alerts=True)
        self.nmn.register(
            "Smart Security",
            self.smart_security_guard,
            raw_process_fn=self.smart_security_guard.process,
        )
        
        print("✅ NMN ready — all modules registered.")

        # ================= 3. ATOMIC FRAME STORES =================
        self.latest_raw    = AtomicFrame()
        self.latest_output = AtomicFrame()

        # ================= 4. STATE MANAGEMENT =================
        self.pipeline          = []
        self.camera_pipelines  = {"default": []}
        self.camera_source     = 1
        self.camera_sources    = {"default": self.camera_source}
        self.current_camera_id = "default"
        self.running           = True
        self.FPS               = 20

        self._frame_count      = 0

        # Flag: is the NMN currently the active processor?
        # Set in set_pipeline — avoids re-checking every frame.
        self._nmn_active       = False

        self._ws_clients: list[WebSocket] = []
        self._ws_lock = threading.Lock()

        self.setup_routes()

        threading.Thread(target=self.camera_reader_loop,  daemon=True).start()
        threading.Thread(target=self.gpu_processing_loop, daemon=True).start()

    # ================= THREAD 1: CAMERA CAPTURE =================
    def camera_reader_loop(self):
        print(f"📷 Camera reader started on source: {self.camera_source}")
        cap = None

        while True:
            if not self.running:
                if cap:
                    cap.release()
                    cap = None
                time.sleep(0.1)
                continue

            if cap is None or not cap.isOpened():
                try:
                    cap = _open_capture(self.camera_source)
                except Exception as e:
                    print(f"❌ Camera connection error: {e}")
                    time.sleep(1)
                    continue

            ret, frame = cap.read()
            if not ret or frame is None:
                cap.release()
                cap = None
                continue

            self.latest_raw.put(frame)

    # ================= THREAD 2: GPU PROCESSING =================
    def gpu_processing_loop(self):
        print("🧠 GPU Worker Thread active...")
        while True:
            try:
                raw_frame = self.latest_raw.get(timeout=1)
                if raw_frame is None:
                    continue

                frame = cv2.resize(raw_frame, (640, 480))
                self._frame_count += 1
                run_heavy = (self._frame_count % SKIP_N == 0)

                # ── NMN PATH ────────────────────────────────────────────────
                # When the active pipeline triggered NMN mode, hand the entire
                # frame to the DynamicNMN.  It handles ordering, context
                # sharing, bridge functions, and parallel execution internally.
                #
                # The NMN is already configured for this pipeline (set_modules
                # was called in set_pipeline when the pipeline changed), so
                # process() here is just inference — no graph rebuild, no
                # model loading.
                if self._nmn_active:
                    if not run_heavy:
                        # For heavy NMN pipelines reuse last output on skip frames
                        cached = self.latest_output.get_nowait()
                        if cached is not None:
                            # Serve the last annotated frame; skip reprocessing
                            self.latest_output.put(cached)
                            continue
                        # No cached output yet (very first frames) — fall through
                        # to run NMN anyway so we don't emit a black frame
                    frame = self.nmn.process(frame)

                    self.latest_output.put(frame)
                    continue   # skip the classic pipeline below

                # ── CLASSIC PIPELINE PATH (unchanged from original) ──────────
                current_pipeline = self.pipeline.copy()

                # Merge Gap Detection + Object Counting → Shelf Orchestrator
                if "Gap Detection" in current_pipeline and "Object Counting" in current_pipeline:
                    current_pipeline = [
                        s for s in current_pipeline
                        if s not in ("Gap Detection", "Object Counting")
                    ]
                    current_pipeline.append("Shelf Orchestrator")

                for step in current_pipeline:

                    if step in HEAVY_MODELS and not run_heavy:
                        cached = self.latest_output.get_nowait()
                        if cached is not None:
                            frame = cached
                        break

                    if step == "Tracking":
                        frame = self.human_tracker.process(frame)

                    elif step == "Color Detection":
                        frame = apply_color_detection(frame)

                    elif step == "Shelf Orchestrator":
                        frame = self.shelf_orchestrator.process(frame)

                    elif step == "Object Counting":
                        frame, _ = self.object_counter.process(frame)

                    elif step == "Gap Detection":
                        frame = self.gap_detector.process(frame)

                    elif step == "Attendance":
                        frame = self.attendance.process(frame)

                    elif step == "Security":
                        frame = self.security.process(frame)

                    elif step == "Parking Management":
                        frame = _frame_only(self.parking_model.process(frame))

                    elif step == "Heatmap":
                        frame = self.heatmap.process(frame)

                    elif step == "Fire & Smoke Detection":
                        frame = self.fire_smoke_detector.process(frame)

                    elif step == "Weapon Detection":                  # ── NEW ──
                        frame = self.weapon_detector.process(frame)  # ── NEW ──

                self.latest_output.put(frame)

            except Exception as e:
                print(f"⚠️ Processing Error: {e}")

    # ================= PER-CAMERA MODEL FACTORY ================================
    def _get_camera_model(self, cam_id: str, step: str):
        """
        Returns the model instance for (cam_id, step), creating it on first use.

        Models that share state / GPU tensors across calls (e.g. YOLO-based
        detectors) MUST NOT be shared across concurrent camera streams or you
        get "only 0-dimensional arrays can be converted to Python scalars".
        Thread-safe — protected by _per_camera_lock.
        """
        with self._per_camera_lock:
            if cam_id not in self._per_camera_models:
                self._per_camera_models[cam_id] = {}
            cam_models = self._per_camera_models[cam_id]
            if step not in cam_models:
                print(f"🔧 Creating dedicated {step} model for camera '{cam_id}'")
                if step == "Fire & Smoke Detection":
                    cam_models[step] = FireSmokeDetector()
                elif step == "Tracking":
                    cam_models[step] = HumanTracker()
                elif step == "Security":
                    cam_models[step] = SecuritySystem()
                elif step == "Attendance":
                    cam_models[step] = AttendanceSystem()
                elif step == "Object Counting":
                    cam_models[step] = ObjectCounterBlock()
                elif step == "Gap Detection":
                    cam_models[step] = ShelfGapDetector()
                elif step == "Heatmap":
                    cam_models[step] = HeatmapBlock()
                elif step == "Weapon Detection":                                  # ── NEW ──
                    cam_models[step] = WeaponDetector(weights="weapon_best.pt")  # ── NEW ──
                else:
                    # Stateless models (Color Detection etc.) — return global instance
                    return None
            return cam_models[step]

    def _build_camera_nmn(self, cam_id: str) -> DynamicNMN:
        """Create a dedicated per-camera DynamicNMN instance with camera-specific models."""
        nmn = DynamicNMN(num_workers=4)

        tracker = self._get_camera_model(cam_id, "Tracking") or self.human_tracker
        attendance = self._get_camera_model(cam_id, "Attendance") or self.attendance
        security = self._get_camera_model(cam_id, "Security") or self.security
        heatmap = self._get_camera_model(cam_id, "Heatmap") or self.heatmap
        object_counter = self._get_camera_model(cam_id, "Object Counting") or self.object_counter
        gap_detector = self._get_camera_model(cam_id, "Gap Detection") or self.gap_detector
        parking_model = self._get_camera_model(cam_id, "Parking Management") or self.parking_model
        smart_guard = SmartSecurityGuard(enable_email_alerts=True)

        nmn.register(
            "Tracking",
            tracker,
            raw_process_fn=tracker.process,
            context_extract_fn=tracking_extractor,
        )
        nmn.register(
            "Attendance",
            attendance,
            raw_process_fn=attendance.process,
            context_extract_fn=attendance_extractor,
        )
        nmn.register(
            "Security",
            security,
            raw_process_fn=security.process,
        )
        nmn.register(
            "Heatmap",
            heatmap,
            raw_process_fn=heatmap.process,
        )
        nmn.register(
            "Object Counting",
            object_counter,
            raw_process_fn=lambda f, _oc=object_counter: _oc.process(f)[0],
            context_extract_fn=object_count_extractor,
        )
        nmn.register(
            "Gap Detection",
            gap_detector,
            raw_process_fn=gap_detector.process,
        )
        nmn.register(
            "Color Detection",
            None,
            raw_process_fn=apply_color_detection,
        )
        nmn.register(
            "Parking Management",
            parking_model,
            raw_process_fn=parking_model.process,
        )
        nmn.register(
            "Smart Security",
            smart_guard,
            raw_process_fn=smart_guard.process,
        )

        return nmn

    def _get_camera_nmn(self, cam_id: str, pipeline: list) -> DynamicNMN:
        """
        Return the per-camera NMN instance, creating it on first use.
        set_modules() is called ONLY when the pipeline list actually changes —
        NOT on every frame — because it rebuilds the execution graph (expensive)
        and acquires the NMN's internal lock.  Calling it per-frame caused the
        deadlock/crash when NMN + split view were active simultaneously.
        """
        pipeline_key = tuple(pipeline)
        with self._per_camera_lock:
            if cam_id not in self._per_camera_nmn:
                print(f"🔧 Creating per-camera NMN instance for camera '{cam_id}'")
                nmn = self._build_camera_nmn(cam_id)
                self._per_camera_nmn[cam_id] = nmn
                # Record which pipeline this NMN was last configured for
                self._per_camera_nmn_pipeline: dict
                if not hasattr(self, "_per_camera_nmn_pipeline"):
                    self._per_camera_nmn_pipeline = {}
                self._per_camera_nmn_pipeline[cam_id] = None   # force set_modules below

            nmn = self._per_camera_nmn[cam_id]
            if not hasattr(self, "_per_camera_nmn_pipeline"):
                self._per_camera_nmn_pipeline = {}
            last_key = self._per_camera_nmn_pipeline.get(cam_id)

        # set_modules() is cheap on the same graph but still rebuilds — only
        # call it when the pipeline actually changed.
        if last_key != pipeline_key:
            nmn.set_modules(pipeline)
            with self._per_camera_lock:
                self._per_camera_nmn_pipeline[cam_id] = pipeline_key
            print(f"🧩 NMN graph updated for camera '{cam_id}': {pipeline}")

        return nmn

    # ================= MJPEG STREAM ===========================================
    async def generate_frames(self):
        loop = asyncio.get_event_loop()
        while True:
            frame = self.latest_output.get_nowait()
            if frame is None:
                await asyncio.sleep(0.005)
                continue

            jpeg_bytes = await loop.run_in_executor(
                _encode_executor, _encode_frame, frame, 75
            )
            if jpeg_bytes is None:
                continue

            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n"
                + jpeg_bytes
                + b"\r\n"
            )

            await asyncio.sleep(0)

    # ================= WEBSOCKET STREAM =======================================
    async def _ws_sender(self, websocket: WebSocket):
        loop = asyncio.get_event_loop()
        try:
            while True:
                frame = self.latest_output.get_nowait()
                if frame is None:
                    await asyncio.sleep(0.005)
                    continue

                jpeg_bytes = await loop.run_in_executor(
                    _encode_executor, _encode_frame, frame, 75
                )
                if jpeg_bytes:
                    await websocket.send_bytes(jpeg_bytes)

                await asyncio.sleep(0)

        except (WebSocketDisconnect, Exception):
            pass
        finally:
            with self._ws_lock:
                if websocket in self._ws_clients:
                    self._ws_clients.remove(websocket)

    # ================= ROUTES =================
    def setup_routes(self):

        @self.app.get("/video")
        async def video():
            return StreamingResponse(
                self.generate_frames(),
                media_type="multipart/x-mixed-replace; boundary=frame",
            )

        @self.app.websocket("/ws")
        async def websocket_stream(websocket: WebSocket):
            await websocket.accept()
            with self._ws_lock:
                self._ws_clients.append(websocket)
            await self._ws_sender(websocket)

        # ── NMN diagnostic endpoint ───────────────────────────────────────────
        @self.app.get("/nmn_status")
        async def nmn_status():
            """
            Returns whether NMN is active, current graph layout, and
            per-module inference timing from the last processed frame.
            Useful for debugging and performance tuning.
            """
            return JSONResponse({
                "nmn_active":   self._nmn_active,
                "graph":        self.nmn.get_graph_info(),
                "timing_ms":    self.nmn.get_timing(),
            })

        @self.app.post("/set_pipeline")
        async def set_pipeline(request: Request):
            data         = await request.json()
            camera_id    = data.get("camera_id", "default")
            new_pipeline = data.get("pipeline", [])
            print(f"📢 PIPELINE UPDATED: {new_pipeline} for {camera_id}")

            self.camera_pipelines[camera_id] = new_pipeline
            if camera_id == self.current_camera_id:
                self.pipeline = new_pipeline

                # ── Decide whether this pipeline goes through NMN ──────────
                if _pipeline_uses_nmn(new_pipeline):
                    # Build the NMN execution graph for this specific combination.
                    # set_modules() is cheap (topological sort only) and is called
                    # HERE, not in the per-frame process loop.
                    self.nmn.set_modules(new_pipeline)
                    self._nmn_active = True
                    print(f"🧩 NMN activated for pipeline: {new_pipeline}")
                    print(f"   Graph: {self.nmn.get_graph_info()}")
                else:
                    self._nmn_active = False
            elif _pipeline_uses_nmn(new_pipeline):
                # Ensure split-camera NMN instances are prepared when pipeline
                # changes. This avoids processing with a stale or empty graph.
                # Invalidate the cached pipeline key so set_modules() fires on
                # the next frame, then eagerly create the NMN if it doesn't exist.
                if hasattr(self, "_per_camera_nmn_pipeline"):
                    with self._per_camera_lock:
                        self._per_camera_nmn_pipeline[camera_id] = None  # force rebuild
                self._get_camera_nmn(camera_id, new_pipeline)

            return {
                "status":     "ok",
                "camera_id":  camera_id,
                "nmn_active": _pipeline_uses_nmn(new_pipeline),
            }

        @self.app.post("/set_camera")
        async def set_camera(request: Request):
            data      = await request.json()
            camera_id = data.get("camera_id", "default")
            new_url   = data.get("url") or self.camera_sources.get(camera_id)

            if not new_url:
                return JSONResponse({"status": "missing camera url"}, status_code=400)

            self.running = False
            await asyncio.sleep(0.5)

            self.camera_sources[camera_id] = new_url
            self.current_camera_id         = camera_id
            self.camera_source             = new_url
            self.pipeline                  = self.camera_pipelines.get(camera_id, [])

            self.running = True
            return {"status": "camera switched", "camera_id": camera_id}

        @self.app.post("/register_camera")
        async def register_camera(request: Request):
            """
            Registers a camera URL without switching the main pipeline stream.
            Used by split-view panels so /video_processed can find the URL.
            """
            data      = await request.json()
            camera_id = data.get("camera_id")
            url       = data.get("url")

            if not camera_id or not url:
                return JSONResponse({"status": "missing camera_id or url"}, status_code=400)

            self.camera_sources[camera_id] = url
            if camera_id not in self.camera_pipelines:
                self.camera_pipelines[camera_id] = []

            return {"status": "registered", "camera_id": camera_id}

        @self.app.get("/video_raw")
        async def video_raw(url: str):
            if not url:
                return JSONResponse({"error": "url param required"}, status_code=400)

            async def raw_frames(cam_url: str):
                loop = asyncio.get_event_loop()

                def _safe_open(u):
                    try:
                        return _open_capture(u)
                    except Exception as e:
                        print(f"❌ video_raw open error: {e}")
                        return None

                cap = [await loop.run_in_executor(None, _safe_open, cam_url)]
                if cap[0] is None or not cap[0].isOpened():
                    print(f"❌ video_raw: failed to open {cam_url!r}")
                    await asyncio.sleep(1)
                    cap[0] = await loop.run_in_executor(None, _safe_open, cam_url)
                    if cap[0] is None or not cap[0].isOpened():
                        print(f"❌ video_raw: persistent open failure for {cam_url!r}")
                        return
                try:
                    while True:
                        ret, frame = await loop.run_in_executor(None, cap[0].read)
                        if not ret or frame is None:
                            await asyncio.sleep(0.2)
                            await loop.run_in_executor(None, cap[0].release)
                            cap[0] = await loop.run_in_executor(None, _safe_open, cam_url) or cv2.VideoCapture()
                            continue
                        jpeg = await loop.run_in_executor(_encode_executor, _encode_frame, frame, 70)
                        if jpeg is None:
                            continue
                        yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n"
                        await asyncio.sleep(0)
                finally:
                    if cap[0]:
                        cap[0].release()

            return StreamingResponse(raw_frames(url),
                                     media_type="multipart/x-mixed-replace; boundary=frame")

        # ── PROCESSED stream per camera_id ───────────────────────────────────
        @self.app.get("/video_processed")
        async def video_processed(camera_id: str):
            if not camera_id:
                return JSONResponse({"error": "camera_id param required"}, status_code=400)

            server_ref = self

            async def processed_frames(cam_id: str):
                loop = asyncio.get_event_loop()

                # Poll up to 3 s for register_camera to store the URL
                cam_url = None
                for _ in range(30):
                    cam_url = server_ref.camera_sources.get(cam_id)
                    if cam_url:
                        break
                    await asyncio.sleep(0.1)

                if not cam_url:
                    print(f"❌ video_processed: no URL for camera_id={cam_id!r}")
                    return

                print(f"▶ video_processed: {cam_id} → {cam_url}")

                def _safe_open_proc(u):
                    try:
                        return _open_capture(u)
                    except Exception as e:
                        print(f"❌ video_processed open error [{cam_id}]: {e}")
                        return None

                cap = [await loop.run_in_executor(None, _safe_open_proc, cam_url)]
                if cap[0] is None or not cap[0].isOpened():
                    print(f"❌ video_processed: failed to open camera source {cam_url!r}")
                    await asyncio.sleep(1)
                    cap[0] = await loop.run_in_executor(None, _safe_open_proc, cam_url)
                    if cap[0] is None or not cap[0].isOpened():
                        print(f"❌ video_processed: persistent open failure for {cam_url!r}")
                        return
                frame_count = 0
                last_processed_frame = None   # cache last good NMN output for skip frames

                def _read_latest(cap_obj):
                    """Drain stale frames from the camera buffer, then decode only
                    the most recent one. Prevents the 10-second delay that builds
                    up when model inference is slower than the camera's source FPS."""
                    for _ in range(3):
                        cap_obj.grab()
                    return cap_obj.retrieve()

                try:
                    while True:
                        ret, frame = await loop.run_in_executor(None, _read_latest, cap[0])
                        if not ret or frame is None:
                            await asyncio.sleep(0.2)
                            await loop.run_in_executor(None, cap[0].release)
                            cap[0] = await loop.run_in_executor(None, _safe_open_proc, cam_url) or cv2.VideoCapture()
                            continue

                        frame = cv2.resize(frame, (640, 480))
                        frame_count += 1
                        run_heavy = (frame_count % SKIP_N == 0)
                        pipeline  = server_ref.camera_pipelines.get(cam_id, [])

                        try:
                            if pipeline:
                                if _pipeline_uses_nmn(pipeline):
                                    if run_heavy:
                                        cam_nmn = server_ref._get_camera_nmn(cam_id, pipeline)
                                        frame = cam_nmn.process(frame)
                                        last_processed_frame = frame   # cache for skip frames
                                    elif last_processed_frame is not None:
                                        # Reuse the last NMN-processed frame on skip frames
                                        # so the stream always shows annotated output
                                        frame = last_processed_frame
                                else:
                                    for step in pipeline:
                                        if not run_heavy and step in HEAVY_MODELS:
                                            continue
                                        if step == "Color Detection":
                                            frame = apply_color_detection(frame)

                                        elif step == "Parking Management":
                                            model = _frame_only(server_ref.parking_model.process(frame))
                                            if model is None:
                                                model = server_ref.parking_model
                                            frame = model.process(frame)
                                        else:
                                            # All YOLO-based models get a dedicated
                                            # per-camera instance to avoid concurrent
                                            # GPU tensor collisions between panels.
                                            model = server_ref._get_camera_model(cam_id, step)
                                            if model is None:
                                                continue  # unrecognised / stateless step
                                            if step == "Object Counting":
                                                frame, _ = model.process(frame)
                                            else:
                                                frame = model.process(frame)
                        except Exception as e:
                            import traceback
                            print(f"⚠️ Split pipeline error [{cam_id}]: {e}")
                            traceback.print_exc()

                        jpeg = await loop.run_in_executor(_encode_executor, _encode_frame, frame, 75)
                        if jpeg is None:
                            continue

                        yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n"
                        # Yield control without an artificial sleep so frames
                        # stream as fast as the camera and model allow.
                        await asyncio.sleep(0)
                finally:
                    cap[0].release()

            return StreamingResponse(processed_frames(camera_id),
                                     media_type="multipart/x-mixed-replace; boundary=frame")

        @self.app.get("/attendance_results")
        async def attendance_results():
            return JSONResponse(self.attendance.get_results())

        @self.app.get("/reset_attendance")
        async def reset_attendance():
            self.attendance.reset()
            return {"status": "reset done"}

        @self.app.post("/set_attendance_class")
        async def set_attendance_class(request: Request):
            """
            Switch the attendance recognition dataset to a specific class folder.

            Body (JSON):
              { "class_name": "class1" }   → scan attendance_images/class1/
              { "class_name": null }        → revert to base attendance_images/

            The face database is rebuilt immediately on the GPU so the live
            camera feed starts recognising the new set of students right away.
            """
            data       = await request.json()
            class_name = data.get("class_name") or None   # empty string → None

            self.attendance.set_class(class_name)

            return {
                "status":     "ok",
                "class_name": class_name or "DEFAULT",
                "persons":    len(self.attendance.person_embeddings),
                "path":       self.attendance.dataset_path,
            }

        @self.app.post("/upload_attendance_images")
        async def upload_images(images: list[UploadFile] = File(...)):
            if not images:
                return JSONResponse({"message": "No files received"}, status_code=400)

            # Always save into whichever path is currently active
            # (base path when no class selected, class subfolder when one is active)
            save_dir = self.attendance.dataset_path
            os.makedirs(save_dir, exist_ok=True)

            saved_files = []
            for file in images:
                if not file.filename:
                    continue
                name     = os.path.splitext(file.filename)[0]
                filepath = os.path.join(save_dir, file.filename)
                contents = await file.read()
                with open(filepath, "wb") as f:
                    f.write(contents)
                saved_files.append(filepath)
                self.attendance.add_image(filepath, name)

            return JSONResponse({
                "status":   "success",
                "saved":    saved_files,
                "saved_to": save_dir,
            }, status_code=200)

        @self.app.get("/security_results")
        async def security_results():
            return JSONResponse(self.security.get_results())

        @self.app.get("/reset_security")
        async def reset_security():
            self.security.reset()
            return {"status": "security reset done"}

        @self.app.post("/security_config")
        async def security_config(request: Request):
            data          = await request.json()
            threshold     = data.get("confidence_threshold", self.security.confidence_threshold)
            enable_alerts = data.get("enable_email_alerts",  self.security.enable_email_alerts)

            self.security.confidence_threshold = threshold
            self.security.enable_email_alerts  = enable_alerts

            return {
                "status":               "ok",
                "confidence_threshold": threshold,
                "enable_email_alerts":  enable_alerts,
            }

        @self.app.post("/set_alert_email")
        async def set_alert_email(request: Request):
            """
            Called by the Dashboard immediately after login and whenever the
            Security pipeline is activated.  Stores the logged-in user's email
            address on the SecuritySystem instance so that alert emails are sent
            to the correct person instead of the hardcoded fallback address.

            Body (JSON):
              { "email": "user@example.com" }   — set dynamic recipient
              { "email": null }                  — revert to hardcoded fallback
            """
            data  = await request.json()
            email = data.get("email") or None
            self.security.set_receiver_email(email)
            self.smart_security_guard.set_receiver_email(email)
            return {
                "status":      "ok",
                "alert_email": email,
            }

        # ═══════════════════════════════════════════════════════════════
        #  SHELF-GAP ALERT ENDPOINTS
        #  Polled by Dashboard.js when the Shelf Orchestrator pipeline
        #  (Object Counting + Gap Detection) is active.
        # ═══════════════════════════════════════════════════════════════

        @self.app.get("/shelf_gap_alert_status")
        async def shelf_gap_alert_status():
            """Return current gap-alert state from ShelfOrchestrator."""
            try:
                status = self.shelf_orchestrator.get_alert_status()
                return JSONResponse(status)
            except Exception as exc:
                print("❌ shelf_gap_alert_status error:", exc)
                return JSONResponse({}, status_code=500)

        @self.app.post("/shelf_gap_alert_dismiss")
        async def shelf_gap_alert_dismiss():
            """Called when the user presses OK on the frontend popup."""
            try:
                self.shelf_orchestrator.reset_alert()
                return JSONResponse({"status": "ok"})
            except Exception as exc:
                print("❌ shelf_gap_alert_dismiss error:", exc)
                return JSONResponse({}, status_code=500)

        @self.app.get("/fire_alert_status")
        async def fire_alert_status():
            """Return current fire/smoke alert status from the active detector.

            Uses a per-camera detector instance when available, otherwise
            falls back to the global `self.fire_smoke_detector` instance.
            """
            try:
                cam_id = self.current_camera_id
                model = None
                if cam_id and cam_id in self._per_camera_models:
                    model = self._per_camera_models[cam_id].get("Fire & Smoke Detection")
                if model is None:
                    model = self.fire_smoke_detector
                status = model.get_alert_status() if hasattr(model, 'get_alert_status') else {}
                return JSONResponse(status)
            except Exception as exc:
                print("❌ fire_alert_status error:", exc)
                return JSONResponse({}, status_code=500)

        # ── NEW: Weapon alert endpoints ───────────────────────────────────────

        @self.app.get("/weapon_alert_status")
        async def weapon_alert_status():
            """Return current weapon alert status from the active detector.

            Uses a per-camera detector instance when available, otherwise
            falls back to the global `self.weapon_detector` instance.
            Mirrors /fire_alert_status — poll from frontend when
            'Weapon Detection' is in the active pipeline.
            """
            try:
                cam_id = self.current_camera_id
                model  = None
                if cam_id and cam_id in self._per_camera_models:
                    model = self._per_camera_models[cam_id].get("Weapon Detection")
                if model is None:
                    model = self.weapon_detector
                status = model.get_alert_status() if hasattr(model, "get_alert_status") else {}
                summary = {
                    "alert":          False,
                    "weapon_type":    None,
                    "elapsed_seconds": 0.0,
                    "threshold":      None,
                    "classes":        status,
                }
                for cls_name, info in status.items():
                    if info.get("alert"):
                        if not summary["alert"] or info["elapsed_seconds"] > summary["elapsed_seconds"]:
                            summary["alert"] = True
                            summary["weapon_type"] = "Weapon"
                            summary["elapsed_seconds"] = info["elapsed_seconds"]
                            summary["threshold"] = info["threshold"]
                return JSONResponse(summary)
            except Exception as exc:
                print("❌ weapon_alert_status error:", exc)
                return JSONResponse({}, status_code=500)

        @self.app.get("/weapon_results")
        async def weapon_results():
            """Returns the full weapon detection log (class, confidence, time, frame)."""
            return JSONResponse(self.weapon_detector.get_results())

        @self.app.post("/reset_weapon")
        async def reset_weapon():
            """Clears the weapon detection log and streak counters."""
            self.weapon_detector.reset()
            return {"status": "weapon detection reset done"}

    def run(self):
        print("🚀 ModuVision Server Running at http://0.0.0.0:5000")
        print("   MJPEG      → http://0.0.0.0:5000/video")
        print("   WS         → ws://0.0.0.0:5000/ws")
        print("   NMN status → http://0.0.0.0:5000/nmn_status")
        uvicorn.run(
            self.app,
            host="0.0.0.0",
            port=5000,
            workers=1,
            log_level="warning",
        )


if __name__ == "__main__":
    server = LiveStreamServer()
    server.run()