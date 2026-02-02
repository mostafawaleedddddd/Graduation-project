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





# ================== APP SETUP ==================
app = Flask(__name__)
CORS(app)

# ================== MODELS ==================
model = YOLO("yolov8s.pt")
human_tracker = HumanTracker()
object_counter = ObjectCounterBlock()
dual_counter = DualModelObjectCounter()
gap_detector = ShelfGapDetector()
# ================== PIPELINE ==================
pipeline = []   # ["Color Detection", "Object Detection", "Tracking"]

# ================== CAMERA CONFIG ==================
CAMERA_INDEX = 0
FRAME_WIDTH = 1280
FRAME_HEIGHT = 720
FPS = 30

# ================== SHARED STATE ==================
raw_frame = None
processed_frame = None
lock = threading.Lock()
running = True

# ================== CAMERA THREAD ==================
def camera_loop():
    global raw_frame
    cap = cv2.VideoCapture(CAMERA_INDEX, cv2.CAP_DSHOW)

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)
    cap.set(cv2.CAP_PROP_FPS, FPS)

    if not cap.isOpened():
        raise RuntimeError("❌ Camera not opened")

    print("✅ Camera started")

    while running:
        ret, frame = cap.read()
        if not ret:
            continue
        with lock:
            raw_frame = frame.copy()

    cap.release()

# ================== PIPELINE PROCESSOR THREAD ==================
def processing_loop():
    global processed_frame

    while running:
        with lock:
            if raw_frame is None:
                continue
            frame = raw_frame.copy()

        # === APPLY PIPELINE IN ORDER ===
        for step in pipeline:

            if step == "Object Detection":
                results = model(frame, conf=0.4)
                for box in results[0].boxes:
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 0, 0), 2)

            elif step == "Tracking":
                frame = human_tracker.process(frame)

            elif step == "Color Detection":
                frame = apply_color_detection(frame)
                
            elif step == "  ":
                frame = object_counter.process(frame)
                
            elif step == "Gap Detection":
                frame = gap_detector.process(frame)
        with lock:
            processed_frame = frame

        time.sleep(1 / FPS)

# ================== VIDEO STREAM ==================
def generate_frames():
    while True:
        with lock:
            frame = processed_frame

        if frame is None:
            continue

        _, buffer = cv2.imencode(".jpg", frame)
        yield (
            b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n\r\n" +
            buffer.tobytes() +
            b"\r\n"
        )

@app.route("/video")
def video():
    return Response(
        generate_frames(),
        mimetype="multipart/x-mixed-replace; boundary=frame"
    )

# ================== PIPELINE API ==================
@app.route("/set_pipeline", methods=["POST"])
def set_pipeline():
    global pipeline
    pipeline = request.json.get("pipeline", [])
    print("PIPELINE UPDATED:", pipeline)
    return jsonify({"status": "ok", "pipeline": pipeline})

# ================== START THREADS ==================
camera_thread = threading.Thread(target=camera_loop, daemon=True)
processor_thread = threading.Thread(target=processing_loop, daemon=True)

camera_thread.start()
processor_thread.start()

# ================== RUN ==================
if __name__ == "__main__":
    print("🚀 Server running")
    app.run(host="127.0.0.1", port=5000, debug=False, use_reloader=False)
