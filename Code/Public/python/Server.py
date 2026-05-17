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
# from attendence import AttendanceSystem
from security import SecuritySystem
from car_parking import ParkingManagementBlock
from heatmap_ipcam import HeatmapBlock
from NMN1 import ShelfOrchestrator
from fire_detection import FireSmokeDetector
# ── NEW: Dynamic NMN ─────────────────────────────────────────────────────────
from NMN import (
    DynamicNMN,
    tracking_extractor,
    object_count_extractor,
)

# ─── Thread pool for JPEG encoding (keeps async loop free) ───────────────────
_encode_executor = ThreadPoolExecutor(max_workers=2)


def _encode_frame(frame, quality: int = 75):
    """Synchronous JPEG encode — called via run_in_executor."""
    ret, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
    return buffer.tobytes() if ret else None


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
    {"Heatmap",    "Tracking"},           
    {"Attendance", "Security", "Tracking"},
    
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

        self.human_tracker      = HumanTracker()
        self.object_counter     = ObjectCounterBlock()
        self.dual_counter       = DualModelObjectCounter()
        self.gap_detector       = ShelfGapDetector()
        # self.attendance         = AttendanceSystem()
        self.security           = SecuritySystem()
        self.parking_model      = ParkingManagementBlock()
        self.heatmap            = HeatmapBlock()
        self.shelf_orchestrator = ShelfOrchestrator()
        self.fire_smoke_detector = FireSmokeDetector()
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
            # ── context_extract_fn pulls tracked bounding boxes ──────────
            # Requires HumanTracker.get_tracks() — see NMN.py §7 for how to
            # add it.  Works with or without it; downstream modules degrade
            # gracefully to full-frame processing when context is absent.
            context_extract_fn=tracking_extractor,
        )

        # self.nmn.register(
        #     "Attendance",
        #     self.attendance,
        #     raw_process_fn=self.attendance.process,
        #     # No extract_fn needed — Attendance is a consumer, not a producer.
        # )

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
            raw_process_fn=self.parking_model.process,
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
                    if str(self.camera_source).startswith("rtsp://"):
                        cap = cv2.VideoCapture(self.camera_source, cv2.CAP_FFMPEG)
                    else:
                        cap = cv2.VideoCapture(self.camera_source)

                    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  640)
                    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                    cap.set(cv2.CAP_PROP_FPS, 30)

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
                            frame = cached
                    else:
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

                    # elif step == "Attendance":
                    #     frame = self.attendance.process(frame)

                    elif step == "Security":
                        frame = self.security.process(frame)

                    elif step == "Parking Management":
                        frame = self.parking_model.process(frame)

                    elif step == "Heatmap":
                        frame = self.heatmap.process(frame)
                    elif step == "Fire & Smoke Detection":
                        frame = self.fire_smoke_detector.process(frame)
                    

                self.latest_output.put(frame)

            except Exception as e:
                print(f"⚠️ Processing Error: {e}")

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

                await asyncio.sleep(1 / 30)

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

        # ── NEW: NMN diagnostic endpoint ──────────────────────────────────
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

                if "Parking Management" in new_pipeline:
                    def setup():
                        self.running = False
                        self.parking_model.run_setup()
                        self.running = True
                    threading.Thread(target=setup, daemon=True).start()

            return {
                "status":     "ok",
                "camera_id":  camera_id,
                "nmn_active": self._nmn_active,
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
                cap = [cv2.VideoCapture(cam_url)]
                try:
                    while True:
                        ret, frame = await loop.run_in_executor(None, cap[0].read)
                        if not ret or frame is None:
                            await asyncio.sleep(0.2)
                            await loop.run_in_executor(None, cap[0].release)
                            cap[0] = cv2.VideoCapture(cam_url)
                            continue
                        jpeg = await loop.run_in_executor(_encode_executor, _encode_frame, frame, 70)
                        if jpeg is None:
                            continue
                        yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n"
                        await asyncio.sleep(1 / 25)
                finally:
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
                cap = [cv2.VideoCapture(cam_url)]
                frame_count = 0

                try:
                    while True:
                        ret, frame = await loop.run_in_executor(None, cap[0].read)
                        if not ret or frame is None:
                            await asyncio.sleep(0.2)
                            await loop.run_in_executor(None, cap[0].release)
                            cap[0] = cv2.VideoCapture(cam_url)
                            continue

                        frame = cv2.resize(frame, (640, 480))
                        frame_count += 1
                        run_heavy = (frame_count % SKIP_N == 0)
                        pipeline  = server_ref.camera_pipelines.get(cam_id, [])

                        try:
                            if pipeline:
                                if _pipeline_uses_nmn(pipeline):
                                    if run_heavy:
                                        frame = server_ref.nmn.process(frame)
                                else:
                                    for step in pipeline:
                                        if not run_heavy and step in HEAVY_MODELS:
                                            continue
                                        if step == "Color Detection":
                                            frame = apply_color_detection(frame)
                                        elif step == "Tracking":
                                            frame = server_ref.human_tracker.process(frame)
                                        elif step == "Object Counting":
                                            frame, _ = server_ref.object_counter.process(frame)
                                        elif step == "Gap Detection":
                                            frame = server_ref.gap_detector.process(frame)
                                        # elif step == "Attendance":
                                        #     frame = server_ref.attendance.process(frame)
                                        elif step == "Security":
                                            frame = server_ref.security.process(frame)
                                        elif step == "Parking Management":
                                            frame = server_ref.parking_model.process(frame)
                                        elif step == "Heatmap":
                                            frame = server_ref.heatmap.process(frame)
                                        elif step == "Fire & Smoke Detection":
                                            frame = server_ref.fire_smoke_detector.process(frame)
                        except Exception as e:
                            print(f"⚠️ Split pipeline error [{cam_id}]: {e}")

                        jpeg = await loop.run_in_executor(_encode_executor, _encode_frame, frame, 75)
                        if jpeg is None:
                            continue

                        yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n"
                        await asyncio.sleep(1 / 20)
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