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
# Change CAMERA_INDEX if needed
CAMERA_INDEX = 0

# Camera will be opened lazily inside the streaming generator to avoid
# issues with Flask's reloader / debug process that can cause the camera
# device to be opened in a different process than the server.

# ================== PIPELINE LOGIC ==================
def apply_pipeline(frame):
    # Skip heavy processing for now - just stream raw frames
    # We can optimize later once we confirm basic streaming works
    
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
frame_count = 0

def generate_frames():
    """Open camera lazily here to ensure the camera device is opened
    in the same process that's serving requests (avoids debug/reloader issues).
    """
    global frame_count
    consecutive_failures = 0

    # Try to open camera with fallback backends (include MSMF on Windows)
    cap = None
    backends = []
    if hasattr(cv2, 'CAP_MSMF'):
        backends.append((cv2.CAP_MSMF, "MSMF"))
    if hasattr(cv2, 'CAP_DSHOW'):
        backends.append((cv2.CAP_DSHOW, "DirectShow"))
    backends.append((0, "Default"))

    for backend_id, backend_name in backends:
        try:
            if backend_id == 0:
                cap = cv2.VideoCapture(CAMERA_INDEX)
            else:
                cap = cv2.VideoCapture(CAMERA_INDEX, backend_id)

            if cap.isOpened():
                # Try to force conversion to RGB if supported by backend
                try:
                    if hasattr(cv2, 'CAP_PROP_CONVERT_RGB'):
                        cap.set(cv2.CAP_PROP_CONVERT_RGB, 1)
                except Exception:
                    pass

                print(f"✓ Camera opened with {backend_name} backend")
                break
            else:
                try:
                    cap.release()
                except Exception:
                    pass
                cap = None
                print(f"✗ Failed to open with {backend_name}")
        except Exception as e:
            print(f"✗ Error with {backend_name}: {e}")

    if cap is None:
        print("❌ Camera not opened. Cannot stream video.")
        return

    # Configure camera
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    cap.set(cv2.CAP_PROP_FPS, 30)
    try:
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    except Exception:
        pass

    print("⏳ Warming up camera (discarding first 20 frames)...")
    import time
    for _ in range(20):
        cap.read()
        time.sleep(0.03)

    first_logged = False
    while True:
        success, frame = cap.read()

        if not success or frame is None:
            consecutive_failures += 1
            if consecutive_failures > 100:
                print("❌ Too many consecutive frame read failures. Camera disconnected?")
                consecutive_failures = 0
            continue

        consecutive_failures = 0
        frame_count += 1

        # Diagnostic logging on first good frame
        if not first_logged:
            first_logged = True
            try:
                import numpy as np
                ch = frame.shape[2] if frame.ndim == 3 else 1
                print(f"First frame: shape={frame.shape}, dtype={frame.dtype}, channels={ch}")
                print(f"  min={frame.min()}, max={frame.max()}, mean={frame.mean():.1f}, std={frame.std():.1f}")
            except Exception as e:
                print(f"  (diagnostic error: {e})")

        # Log every 60 frames
        if frame_count % 60 == 0:
            mean_val = frame.mean()
            print(f"Frame {frame_count}: shape={frame.shape}, mean={mean_val:.1f}")

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
    # Run without the reloader/debugger to avoid the camera device being
    # opened in a different process (which causes black frames / dropped frames).
    app.run(host="127.0.0.1", port=5000, debug=False, use_reloader=False)
