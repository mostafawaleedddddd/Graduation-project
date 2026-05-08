import os
import cv2
import time
import threading
from queue import Queue, Empty
from flask import Flask, Response, request, jsonify
from flask_cors import CORS
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

class LiveStreamServer:

    def __init__(self):
        self.app = Flask(__name__)
        CORS(self.app)

        # ================= 1. GPU MODEL INITIALIZATION =================
        print("🚀 Initializing GPU Models for ModuVision...")
        
        # Main YOLO model moved to GPU
        self.model = YOLO("yolov8s.pt")
        self.model.to('cuda') 
        
        # Initialize blocks (Ensure their internal models also use .to('cuda') if needed)
        self.human_tracker = HumanTracker()
        self.object_counter = ObjectCounterBlock()
        self.dual_counter = DualModelObjectCounter()
        self.gap_detector = ShelfGapDetector()
        self.attendance = AttendanceSystem() # Attendance handles its own GPU via InsightFace ctx_id=0
        self.parking_model = ParkingManagementBlock()
        self.heatmap = HeatmapBlock()
        self.shelf_orchestrator = ShelfOrchestrator()

        # ================= 2. QUEUE SYSTEM (For Speed) =================
        # This replaces the old 'self.lock' system to allow parallel processing
        self.input_queue = Queue(maxsize=1)   # Fresh frames from camera
        self.output_queue = Queue(maxsize=1)  # Processed frames for web

        # ================= 3. STATE MANAGEMENT =================
        self.pipeline = []
        self.camera_pipelines = {"default": []}
        self.camera_source = 1
        self.camera_sources = {"default": self.camera_source}
        self.current_camera_id = "default"
        self.running = True
        self.FPS = 20 # Note: In this new system, this acts as a 'target' rather than a hard limit

        self.setup_routes()
        
        # Start Threads
        threading.Thread(target=self.camera_reader_loop, daemon=True).start()
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
                except Exception as e:
                    print(f"❌ Camera connection error: {e}")
                    time.sleep(1)
                    continue

            ret, frame = cap.read()
            if not ret or frame is None:
                cap.release()
                cap = None
                continue

            # Push only the freshest frame to the GPU worker
            if not self.input_queue.empty():
                try: self.input_queue.get_nowait()
                except: pass
            self.input_queue.put(frame)

    # ================= THREAD 2: GPU PROCESSING =================
    def gpu_processing_loop(self):
        print("🧠 GPU Worker Thread active...")
        while True:
            try:
                # Grab the next frame from the camera reader
                raw_frame = self.input_queue.get(timeout=1)
                frame = cv2.resize(raw_frame, (640, 480))

                # Copy current pipeline to avoid modification issues
                current_pipeline = self.pipeline.copy()
                
                # Logic for Shelf Orchestrator merge
                if "Gap Detection" in current_pipeline and "Object Counting" in current_pipeline:
                    current_pipeline = [s for s in current_pipeline if s not in ["Gap Detection", "Object Counting"]]
                    current_pipeline.append("Shelf Orchestrator")

                # --- APPLY PIPELINE (Now running on GPU) ---
                for step in current_pipeline:
                    if step == "Object Detection":
                        # Explicitly tell YOLO to use GPU
                        results = self.model(frame, conf=0.4, device='cuda', verbose=False)
                        frame = results[0].plot()

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

                # Push the finished frame to the output queue for streaming
                if not self.output_queue.empty():
                    try: self.output_queue.get_nowait()
                    except: pass
                self.output_queue.put(frame)

            except Empty:
                continue
            except Exception as e:
                print(f"⚠️ Processing Error: {e}")

    # ================= THREAD 3: FLASK STREAMER =================
    def generate_frames(self):
        while True:
            try:
                # Get the latest frame processed by the GPU
                frame = self.output_queue.get(timeout=1)
                ret, buffer = cv2.imencode(".jpg", frame)
                if not ret:
                    continue

                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n" +
                    buffer.tobytes() +
                    b"\r\n"
                )
            except Empty:
                time.sleep(0.01)
                continue

    def setup_routes(self):

        @self.app.route("/video")
        def video():
            return Response(
                self.generate_frames(),
                mimetype="multipart/x-mixed-replace; boundary=frame"
            )

        @self.app.route("/set_pipeline", methods=["POST"])
        def set_pipeline():
            camera_id = request.json.get("camera_id", "default")
            new_pipeline = request.json.get("pipeline", [])
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

            return jsonify({"status": "ok", "camera_id": camera_id})

        @self.app.route("/set_camera", methods=["POST"])
        def set_camera():
            data = request.json
            camera_id = data.get("camera_id", "default")
            new_url = data.get("url") or self.camera_sources.get(camera_id)

            if not new_url:
                return jsonify({"status": "missing camera url"}), 400

            self.running = False
            time.sleep(0.5)

            self.camera_sources[camera_id] = new_url
            self.current_camera_id = camera_id
            self.camera_source = new_url
            self.pipeline = self.camera_pipelines.get(camera_id, [])

            self.running = True
            return jsonify({"status": "camera switched", "camera_id": camera_id})

        @self.app.route("/attendance_results")
        def attendance_results():
            return jsonify(self.attendance.get_results())

        @self.app.route("/reset_attendance")
        def reset_attendance():
            self.attendance.reset()
            return jsonify({"status": "reset done"})
        
        @self.app.route("/upload_attendance_images", methods=["POST"])
        def upload_images():
            if "images" not in request.files:
                return jsonify({"message": "No files received"}), 400

            files = request.files.getlist("images")
            saved_files = []

            for file in files:
                if file.filename == "": continue
                name = os.path.splitext(file.filename)[0]
                filepath = os.path.join("attendance_images", file.filename)
                file.save(filepath)
                saved_files.append(filepath)
                self.attendance.add_image(filepath, name)

            return jsonify({"status": "success", "saved": saved_files}), 200

    def run(self):
        print("🚀 ModuVision Server Running at http://127.0.0.1:5000")
        # In WSL2, host '0.0.0.0' makes it easier for Windows to find the server
        self.app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)

if __name__ == "__main__":
    server = LiveStreamServer()
    server.run()