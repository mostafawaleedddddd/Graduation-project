import cv2
from flask import Flask, Response, request, jsonify
from flask_cors import CORS
import threading
import time
from ultralytics import YOLO

from color_detection_pi import apply_color_detection
from human_tracking import HumanTracker
from object_countingtry import ObjectCounterBlock
from two_models import DualModelObjectCounter
from shelf_gap_detect_images import ShelfGapDetector
from attendence import AttendanceSystem
from car_parking import ParkingManagementBlock


class LiveStreamServer:

    def __init__(self):

        # ================== APP ==================
        self.app = Flask(__name__)
        CORS(self.app)

        # ================== MODELS ==================
        self.model = YOLO("yolov8s.pt")
        self.human_tracker = HumanTracker()
        self.object_counter = ObjectCounterBlock()
        self.dual_counter = DualModelObjectCounter()
        self.gap_detector = ShelfGapDetector()
        self.attendance = AttendanceSystem()
        self.parking_model = ParkingManagementBlock()

        # ================== PIPELINE ==================
        self.pipeline = []

        # ================== CAMERA ==================
        self.camera_source = 1
        self.cap = None

        # ================== STATE ==================
        self.raw_frame = None
        self.processed_frame = None
        self.lock = threading.Lock()

        self.running = True
        self.camera_thread = None

        self.FPS = 20

        # ================== ROUTES ==================
        self.setup_routes()

        # ================== START THREADS ==================
        self.start_camera_thread()
        threading.Thread(target=self.processing_loop, daemon=True).start()

    # ================== START CAMERA THREAD ==================
    def start_camera_thread(self):
        self.camera_thread = threading.Thread(
            target=self.camera_loop,
            daemon=True
        )
        self.camera_thread.start()

    # ================== CAMERA LOOP ==================
    def camera_loop(self):

        print("📷 Camera thread started")

        while True:

            # 🔴 PAUSE when switching camera
            if not self.running:
                time.sleep(0.1)
                continue

            # 🔁 CONNECT CAMERA
            if self.cap is None:
                print(f"🎥 Connecting to: {self.camera_source}")

                try:
                    if str(self.camera_source).startswith("rtsp://"):
                        self.cap = cv2.VideoCapture(self.camera_source, cv2.CAP_FFMPEG)
                    else:
                        self.cap = cv2.VideoCapture(self.camera_source)

                    self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

                    if not self.cap.isOpened():
                        print("❌ Failed to open camera")
                        self.cap.release()
                        self.cap = None
                        time.sleep(1)
                        continue

                    print("✅ Camera connected")

                except Exception as e:
                    print("Camera error:", e)
                    self.cap = None
                    time.sleep(1)
                    continue

            # 🔥 READ FRAME (DROP BUFFER)
            ret = False
            frame = None

            for _ in range(3):
                ret, frame = self.cap.read()

            if not ret:
                print("⚠️ Frame failed → reconnecting...")

                try:
                    self.cap.release()
                except:
                    pass

                self.cap = None
                time.sleep(1)
                continue

            frame = cv2.resize(frame, (640, 480))

            with self.lock:
                self.raw_frame = frame.copy()

    # ================== PROCESSING LOOP ==================
    def processing_loop(self):

        while True:

            if not self.running:
                time.sleep(0.1)
                continue

            with self.lock:
                if self.raw_frame is None:
                    continue
                frame = self.raw_frame.copy()

            # 🔁 APPLY PIPELINE
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

                elif step == "Attendance":
                    frame = self.attendance.process(frame)

                elif step == "Parking Management":
                    frame = self.parking_model.process(frame)

            with self.lock:
                self.processed_frame = frame

            time.sleep(1 / self.FPS)

    # ================== STREAM ==================
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
            print("PIPELINE:", self.pipeline)
            return jsonify({"status": "ok"})

        # 🔥 FIXED CAMERA SWITCH (NO FREEZE)
        @self.app.route("/set_camera", methods=["POST"])
        def set_camera():
            data = request.json
            new_url = data.get("url")

            print("Switching camera to:", new_url)

            # 🛑 STOP threads safely
            self.running = False
            time.sleep(0.5)

            # 🔥 RELEASE camera
            if self.cap:
                try:
                    self.cap.release()
                except:
                    pass
                self.cap = None

            # 🔄 CLEAR FRAMES
            with self.lock:
                self.raw_frame = None
                self.processed_frame = None

            # 🔁 SET NEW CAMERA
            self.camera_source = new_url

            # ▶️ RESTART
            self.running = True
            self.start_camera_thread()

            return jsonify({"status": "camera switched"})

        # ✅ ATTENDANCE RESULTS
        @self.app.route("/attendance_results")
        def attendance_results():
            return jsonify(self.attendance.get_results())

        # ✅ RESET ATTENDANCE
        @self.app.route("/reset_attendance")
        def reset_attendance():
            self.attendance.reset()
            return jsonify({"status": "reset done"})

    # ================== RUN ==================
    def run(self):
        print("🚀 Server running...")
        self.app.run(
            host="127.0.0.1",
            port=5000,
            debug=False,
            use_reloader=False
        )


if __name__ == "__main__":
    server = LiveStreamServer()
    server.run()