from flask import Flask, Response, request
from flask_cors import CORS
import cv2
from ultralytics import YOLO
from modules.color_detection_pi import apply_color_detection

# ================== APP SETUP ==================
app = Flask(__name__)
CORS(app)

# ================== MODELS ==================
model = YOLO("yolov8s.pt")

# ================== PIPELINE ==================
pipeline = []   # e.g. ["Color Detection", "Object Detection", "Tracking"]

# ================== CAMERA ==================
# IMPORTANT:
# 0 = Integrated camera
# 1 = Iriun webcam (most common)
# Change index ONLY if needed
cap = cv2.VideoCapture(1, cv2.CAP_DSHOW)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
cap.set(cv2.CAP_PROP_FPS, 30)
if not cap.isOpened():
    raise RuntimeError("❌ Camera not opened. Check Iriun or camera index.")

# ================== PIPELINE LOGIC ==================
def apply_pipeline(frame):
    for step in pipeline:

        # if step == "Object Detection":
        #     results = model(frame, conf=0.4)
        #     for box in results[0].boxes:
        #         x1, y1, x2, y2 = map(int, box.xyxy[0])
        #         cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 0, 0), 2)

        # elif step == "Tracking":
        #     results = model.track(frame, persist=True)
        #     for box in results[0].boxes:
        #         if box.id is None:
        #             continue
        #         x1, y1, x2, y2 = map(int, box.xyxy[0])
        #         tid = int(box.id)
        #         cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
        #         cv2.putText(
        #             frame,
        #             f"ID {tid}",
        #             (x1, y1 - 10),
        #             cv2.FONT_HERSHEY_SIMPLEX,
        #             0.6,
        #             (0, 255, 0),
        #             2
        #         )

        if step == "Color Detection":
            pass

    return frame

# ================== VIDEO STREAM ==================
def generate_frames():
    while True:
        success, frame = cap.read()
        if not success:
            continue

        frame = apply_pipeline(frame)
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
    print("PIPELINE:", pipeline)
    return {"status": "ok", "pipeline": pipeline}

# ================== DEBUG ==================
print("REGISTERED ROUTES:")
print(app.url_map)

# ================== RUN ==================
if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
