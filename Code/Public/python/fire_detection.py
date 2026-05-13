import cv2
import numpy as np
import torch
from datetime import datetime
from collections import defaultdict
from ultralytics import YOLO


class FireSmokeDetector:

    def __init__(self, weights="best_fire.pt", conf=0.25, iou=0.50, imgsz=512):

        # ================= LOAD MODEL ON GPU =================
        print("🔄 Loading Fire & Smoke model on GPU...")
        self.device = "cuda:0" if torch.cuda.is_available() else "cpu"
        self.model  = YOLO(weights)
        self.model.to(self.device)
        print(f"✅ Model loaded on: {self.device.upper()}")

        # ================= SETTINGS =================
        self.conf  = conf
        self.iou   = iou
        self.imgsz = imgsz

        # Class names — order matches how the model was trained
        # (0 = fire, 1 = smoke  OR  swapped — adjust if needed)
        self.class_names = {0: "fire", 1: "smoke"}
        self.colors      = {0: (0, 80, 255),    # fire  → red-orange (BGR)
                            1: (160, 160, 160)}  # smoke → grey

        # ================= ALERT TRACKING =================
        self.alert_log   = []          # list of {class, confidence, time}
        self.frame_count = 0

        print("✅ FireSmokeDetector ready")

    # ================= PROCESS FRAME =================
    def process(self, frame: np.ndarray) -> np.ndarray:
        """
        Runs detection on a single BGR frame (OpenCV format).
        Draws bounding boxes + labels and returns the annotated frame.
        Also logs any detections to self.alert_log.
        """
        self.frame_count += 1

        results = self.model.predict(
            source  = frame,
            conf    = self.conf,
            iou     = self.iou,
            imgsz   = self.imgsz,
            device  = self.device,
            verbose = False,
        )

        detections = results[0].boxes  # all boxes for this frame

        if detections is not None and len(detections):
            for box in detections:
                x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                cls_id  = int(box.cls[0])
                conf_sc = float(box.conf[0])

                cls_name = self.class_names.get(cls_id, str(cls_id))
                if(cls_name == "fire"):
                    cls_name = "smoke"
                elif(cls_name == "smoke"):
                    cls_name = "fire"
                color    = self.colors.get(cls_id, (0, 255, 0))
                label    = f"{cls_name.upper()} ({conf_sc:.2f})"
                
                # ── Draw box ──────────────────────────────────────────
                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

                # ── Label background + text ───────────────────────────
                (tw, th), _ = cv2.getTextSize(
                    label, cv2.FONT_HERSHEY_SIMPLEX, 0.65, 2)
                cv2.rectangle(
                    frame,
                    (x1, y1 - th - 10), (x1 + tw + 6, y1),
                    color, -1)
                cv2.putText(
                    frame, label,
                    (x1 + 3, y1 - 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.65,
                    (255, 255, 255), 2)

                # ── Log detection ─────────────────────────────────────
                self._log_detection(cls_name, conf_sc)

        return frame

    # ================= ALERT LOGGING =================
    def _log_detection(self, cls_name: str, confidence: float):
        now = datetime.now().strftime("%H:%M:%S")
        self.alert_log.append({
            "class"     : cls_name,
            "confidence": round(confidence, 3),
            "time"      : now,
            "frame"     : self.frame_count,
        })
        print(f"🔥 Detected: {cls_name.upper()}  conf={confidence:.2f}  @ {now}")

    # ================= GET RESULTS =================
    def get_results(self) -> list:
        """Returns the full detection log."""
        return self.alert_log

    # ================= RESET =================
    def reset(self):
        """Clears the detection log and frame counter."""
        self.alert_log   = []
        self.frame_count = 0
        print("✅ Detection log cleared")


# ════════════════════════════════════════════════════════════════
#  EXAMPLE USAGE — webcam / video file
# ════════════════════════════════════════════════════════════════
if __name__ == "__main__":

    detector = FireSmokeDetector(
        weights = r"E:\fire_detection\results\runs\final\weights\best.pt",
        conf    = 0.25,
        iou     = 0.50,
        imgsz   = 512,
    )

    # 0 = webcam  |  replace with r"E:\video.mp4" for a file
    cap = cv2.VideoCapture(0)

    print("\n  Press Q to quit\n")

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        frame = detector.process(frame)
        cv2.imshow("Fire & Smoke Detection", frame)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()

    print("\n  Detection log:")
    for entry in detector.get_results():
        print(f"  Frame {entry['frame']:>5} | {entry['time']} | "
              f"{entry['class']:<6} | conf={entry['confidence']:.3f}")