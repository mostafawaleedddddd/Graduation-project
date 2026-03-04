from flask import Flask, Response, request, jsonify
from flask_cors import CORS
import cv2
import threading
import time
from ultralytics import YOLO

from color_detection_pi import apply_color_detection
from human_tracking import HumanTracker
from object_countingtry import ObjectCounterBlock
from two_models import DualModelObjectCounter
from shelf_gap_detect_images import ShelfGapDetector


class LiveStreamServer:

    def __init__(self):
        # ================== APP SETUP ==================
        self.app = Flask(__name__)
        CORS(self.app)

        # ================== MODELS ==================
        self.model = YOLO("yolov8s.pt")
        self.human_tracker = HumanTracker()
        self.object_counter = ObjectCounterBlock()
        self.dual_counter = DualModelObjectCounter()
        self.gap_detector = ShelfGapDetector()

        # ================== PIPELINE ==================
        self.pipeline = []

        # ================== CAMERA CONFIG ==================
        self.CAMERA_INDEX = 0
        self.FRAME_WIDTH = 1280
        self.FRAME_HEIGHT = 720
        self.FPS = 30

        # ================== SHARED STATE ==================
        self.raw_frame = None
        self.processed_frame = None
        self.lock = threading.Lock()
        self.running = True

        # ================== ROUTES ==================
        self.setup_routes()

        # ================== THREADS ==================
        self.camera_thread = threading.Thread(
            target=self.camera_loop, daemon=True
        )
        self.processor_thread = threading.Thread(
            target=self.processing_loop, daemon=True
        )

        self.camera_thread.start()
        self.processor_thread.start()

    # ================== CAMERA THREAD ==================
    def camera_loop(self):
        cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)

        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.FRAME_WIDTH)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.FRAME_HEIGHT)
        cap.set(cv2.CAP_PROP_FPS, self.FPS)

        if not cap.isOpened():
            raise RuntimeError("❌ Camera not opened")

        print("✅ Camera started")

        while self.running:
            ret, frame = cap.read()
            if not ret:
                continue

            with self.lock:
                self.raw_frame = frame.copy()

        cap.release()

    # ================== PROCESSING THREAD ==================
    def processing_loop(self):
        while self.running:

            with self.lock:
                if self.raw_frame is None:
                    continue
                frame = self.raw_frame.copy()

            for step in self.pipeline:

                if step == "Object Detection":
                    results = self.model(frame, conf=0.4)
                    for box in results[0].boxes:
                        x1, y1, x2, y2 = map(int, box.xyxy[0])
                        cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 0, 0), 2)

                elif step == "Tracking":
                    frame = self.human_tracker.process(frame)

                elif step == "Color Detection":
                    frame = apply_color_detection(frame)

                elif step == "Object Counting":
                    frame = self.object_counter.process(frame)

                elif step == "Gap Detection":
                    frame = self.gap_detector.process(frame)

            with self.lock:
                self.processed_frame = frame

            time.sleep(1 / self.FPS)

    # ================== STREAM GENERATOR ==================
    def generate_frames(self):
        while True:
            with self.lock:
                frame = self.processed_frame

            if frame is None:
                continue

            _, buffer = cv2.imencode(".jpg", frame)

            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n" +
                buffer.tobytes() +
                b"\r\n"
            )

    # ================== ROUTES ==================
    def setup_routes(self):

        @self.app.route("/video")
        def video():
            return Response(
                self.generate_frames(),
                mimetype="multipart/x-mixed-replace; boundary=frame"
            )

        @self.app.route("/set_pipeline", methods=["POST"])
        def set_pipeline():
            self.pipeline = request.json.get("pipeline", [])
            print("PIPELINE UPDATED:", self.pipeline)
            return jsonify({"status": "ok", "pipeline": self.pipeline})

    # ================== RUN SERVER ==================
    def run(self):
        print("🚀 Server running")
        self.app.run(
            host="127.0.0.1",
            port=5000,
            debug=False,
            use_reloader=False
        )
    

if __name__ == "__main__":
    server = LiveStreamServer()
    server.run()