import os
import cv2
import time
import asyncio
import threading
from queue import Queue, Empty
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI, UploadFile, File, Request
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
from car_parking import ParkingManagementBlock
from heatmap_ipcam import HeatmapBlock
from NMN1 import ShelfOrchestrator


# ─── JPEG encode runs in a thread pool so it never blocks the async event loop ───
_encode_executor = ThreadPoolExecutor(max_workers=2)


def _encode_frame(frame, quality: int = 80):
    """Synchronous JPEG encode — called via run_in_executor."""
    ret, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
    return buffer.tobytes() if ret else None


class LiveStreamServer:

    def __init__(self):
        self.app = FastAPI()

        # ── CORS (same as before) ──
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
        self.attendance         = AttendanceSystem()   # handles its own GPU via InsightFace ctx_id=0
        self.parking_model      = ParkingManagementBlock()
        self.heatmap            = HeatmapBlock()
        self.shelf_orchestrator = ShelfOrchestrator()

        # ================= 2. QUEUE SYSTEM =================
        self.input_queue  = Queue(maxsize=1)   # fresh frames from camera
        self.output_queue = Queue(maxsize=1)   # processed frames for web

        # ================= 3. STATE MANAGEMENT =================
        self.pipeline           = []
        self.camera_pipelines   = {"default": []}
        self.camera_source      = 1
        self.camera_sources     = {"default": self.camera_source}
        self.current_camera_id  = "default"
        self.running            = True
        self.FPS                = 20   # target; actual rate is queue-driven

        self.setup_routes()

        # Start background threads
        threading.Thread(target=self.camera_reader_loop, daemon=True).start()
        threading.Thread(target=self.gpu_processing_loop,  daemon=True).start()

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
                except Exception as e:
                    print(f"❌ Camera connection error: {e}")
                    time.sleep(1)
                    continue

            ret, frame = cap.read()
            if not ret or frame is None:
                cap.release()
                cap = None
                continue

            # Always keep only the freshest frame
            if not self.input_queue.empty():
                try:
                    self.input_queue.get_nowait()
                except Exception:
                    pass
            self.input_queue.put(frame)

    # ================= THREAD 2: GPU PROCESSING =================
    def gpu_processing_loop(self):
        print("🧠 GPU Worker Thread active...")
        while True:
            try:
                raw_frame = self.input_queue.get(timeout=1)
                frame = cv2.resize(raw_frame, (640, 480))

                current_pipeline = self.pipeline.copy()

                # Merge Gap Detection + Object Counting → Shelf Orchestrator
                if "Gap Detection" in current_pipeline and "Object Counting" in current_pipeline:
                    current_pipeline = [
                        s for s in current_pipeline
                        if s not in ("Gap Detection", "Object Counting")
                    ]
                    current_pipeline.append("Shelf Orchestrator")

                # --- APPLY PIPELINE (GPU) ---
                for step in current_pipeline:
                    if step == "Object Detection":
                        results = self.model(frame, conf=0.4, device="cuda", verbose=False)
                        frame   = results[0].plot()

                    elif step == "Tracking":
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

                    elif step == "Parking Management":
                        frame = self.parking_model.process(frame)

                    elif step == "Heatmap":
                        frame = self.heatmap.process(frame)

                # Push finished frame — drop stale one if present
                if not self.output_queue.empty():
                    try:
                        self.output_queue.get_nowait()
                    except Exception:
                        pass
                self.output_queue.put(frame)

            except Empty:
                continue
            except Exception as e:
                print(f"⚠️ Processing Error: {e}")

    # ================= ASYNC STREAM GENERATOR =================
    async def generate_frames(self):
        """
        Async generator for MJPEG streaming.
        - JPEG encoding is offloaded to a thread-pool executor so it never
          blocks the uvicorn event loop (which would stall OTHER requests).
        - asyncio.sleep(0) yields control between frames so the GPU worker
          thread can schedule work without being starved.
        """
        loop = asyncio.get_event_loop()
        while True:
            try:
                # Non-blocking peek; if empty, yield control and retry
                if self.output_queue.empty():
                    await asyncio.sleep(0.005)
                    continue

                frame = self.output_queue.get_nowait()

                # Encode in thread pool — frees the event loop during CPU work
                jpeg_bytes = await loop.run_in_executor(
                    _encode_executor, _encode_frame, frame, 80
                )
                if jpeg_bytes is None:
                    continue

                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n"
                    + jpeg_bytes
                    + b"\r\n"
                )

                # Yield control so uvicorn can handle other coroutines
                await asyncio.sleep(0)

            except Empty:
                await asyncio.sleep(0.005)
            except Exception as e:
                print(f"⚠️ Stream error: {e}")
                await asyncio.sleep(0.01)

    # ================= ROUTES =================
    def setup_routes(self):

        @self.app.get("/video")
        async def video():
            return StreamingResponse(
                self.generate_frames(),
                media_type="multipart/x-mixed-replace; boundary=frame",
            )

        @self.app.post("/set_pipeline")
        async def set_pipeline(request: Request):
            data        = await request.json()
            camera_id   = data.get("camera_id", "default")
            new_pipeline = data.get("pipeline", [])
            print(f"📢 PIPELINE UPDATED: {new_pipeline} for {camera_id}")

            self.camera_pipelines[camera_id] = new_pipeline
            if camera_id == self.current_camera_id:
                self.pipeline = new_pipeline

                if "Parking Management" in new_pipeline:
                    def setup():
                        self.running = False
                        self.parking_model.run_setup()
                        self.running = True
                    threading.Thread(target=setup, daemon=True).start()

            return {"status": "ok", "camera_id": camera_id}

        @self.app.post("/set_camera")
        async def set_camera(request: Request):
            data      = await request.json()
            camera_id = data.get("camera_id", "default")
            new_url   = data.get("url") or self.camera_sources.get(camera_id)

            if not new_url:
                return JSONResponse({"status": "missing camera url"}, status_code=400)

            self.running = False
            await asyncio.sleep(0.5)

            self.camera_sources[camera_id]  = new_url
            self.current_camera_id          = camera_id
            self.camera_source              = new_url
            self.pipeline                   = self.camera_pipelines.get(camera_id, [])

            self.running = True
            return {"status": "camera switched", "camera_id": camera_id}

        @self.app.get("/attendance_results")
        async def attendance_results():
            return JSONResponse(self.attendance.get_results())

        @self.app.get("/reset_attendance")
        async def reset_attendance():
            self.attendance.reset()
            return {"status": "reset done"}

        @self.app.post("/upload_attendance_images")
        async def upload_images(images: list[UploadFile] = File(...)):
            if not images:
                return JSONResponse({"message": "No files received"}, status_code=400)

            saved_files = []
            os.makedirs("attendance_images", exist_ok=True)

            for file in images:
                if not file.filename:
                    continue
                name     = os.path.splitext(file.filename)[0]
                filepath = os.path.join("attendance_images", file.filename)
                contents = await file.read()
                with open(filepath, "wb") as f:
                    f.write(contents)
                saved_files.append(filepath)
                self.attendance.add_image(filepath, name)

            return JSONResponse({"status": "success", "saved": saved_files}, status_code=200)

    def run(self):
        print("🚀 ModuVision Server Running at http://0.0.0.0:5000")
        uvicorn.run(
            self.app,
            host="0.0.0.0",
            port=5000,
            workers=1,          # must be 1 — GPU state lives in this process
            log_level="warning",
            # NOTE: loop="uvloop" was removed — uvloop is Linux/macOS only.
            # On Windows, uvicorn uses the default asyncio ProactorEventLoop which
            # is fully async and works correctly. No performance loss on Windows.
        )


if __name__ == "__main__":
    server = LiveStreamServer()
    server.run()