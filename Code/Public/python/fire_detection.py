import cv2
import numpy as np
import torch
import time
from datetime import datetime
from collections import defaultdict
from ultralytics import YOLO


class FireSmokeDetector:

    # How many consecutive seconds of detection trigger an alert
    ALERT_THRESHOLDS = {"fire": 3.0, "smoke": 5.0}

    # Gap tolerance: a class can be absent for this many seconds before
    # its streak resets (absorbs the occasional dropped frame without
    # resetting a genuine 3-second fire alarm)
    GAP_TOLERANCE = 1.0

    def __init__(self, weights="best_fire_2.pt", conf=0.45, iou=0.50, imgsz=512):

        # ================= LOAD MODEL ON GPU =================
        print("🔄 Loading Fire & Smoke model on GPU...")
        self.device = "cuda:0" if torch.cuda.is_available() else "cpu"
        self.model  = YOLO(weights)
        self.model.to(self.device)
        print(f"✅ Model loaded on: {self.device.upper()}")

        # ================= SETTINGS =================
        self.conf  = conf   # raised to 0.45 to reduce hand false-positives
        self.iou   = iou
        self.imgsz = imgsz

        # Class names — order matches how the model was trained
        self.class_names = {0: "fire", 1: "smoke"}
        self.colors      = {0: (0, 80, 255),    # fire  → red-orange (BGR)
                            1: (160, 160, 160)}  # smoke → grey

        # ================= ALERT TRACKING =================
        self.alert_log   = []          # list of {class, confidence, time}
        self.frame_count = 0

        # Consecutive detection streak tracking per class
        # _streak_start[cls]:  wall-clock time when the current streak began
        #                      (None = no active streak)
        # _last_seen[cls]:     wall-clock time of the most recent frame this
        #                      class was detected in
        self._streak_start: dict[str, float | None] = {
            cls: None for cls in self.ALERT_THRESHOLDS
        }
        self._last_seen: dict[str, float] = {
            cls: 0.0 for cls in self.ALERT_THRESHOLDS
        }

        print("✅ FireSmokeDetector ready")

    # ================= PROCESS FRAME =================
    def process(self, frame: np.ndarray) -> np.ndarray:
        """
        Runs detection on a single BGR frame (OpenCV format).
        Draws bounding boxes + labels and returns the annotated frame.
        Updates streak counters used by get_alert_status().
        """
        self.frame_count += 1
        now = time.monotonic()

        results = self.model.predict(
            source  = frame,
            conf    = self.conf,
            iou     = self.iou,
            imgsz   = self.imgsz,
            device  = self.device,
            verbose = False,
        )

        detections    = results[0].boxes
        detected_this_frame: set[str] = set()

        if detections is not None and len(detections):
            for box in detections:
                x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                cls_id  = int(box.cls[0])
                conf_sc = float(box.conf[0])

                cls_name = self.class_names.get(cls_id, str(cls_id))
                # Swap labels if training order was inverted
                if cls_name == "fire":
                    cls_name = "smoke"
                elif cls_name == "smoke":
                    cls_name = "fire"

                color = self.colors.get(cls_id, (0, 255, 0))
                label = f"{cls_name.upper()} ({conf_sc:.2f})"

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

                detected_this_frame.add(cls_name)
                self._log_detection(cls_name, conf_sc)

        # ── Update streak counters ─────────────────────────────────────
        for cls_name in self.ALERT_THRESHOLDS:
            if cls_name in detected_this_frame:
                # Class detected this frame — start or extend streak
                self._last_seen[cls_name] = now
                if self._streak_start[cls_name] is None:
                    self._streak_start[cls_name] = now
            else:
                # Class not detected — reset streak if gap exceeds tolerance
                gap = now - self._last_seen[cls_name]
                if gap > self.GAP_TOLERANCE:
                    self._streak_start[cls_name] = None

        return frame

    # ================= ALERT STATUS =================
    def get_alert_status(self) -> dict:
       
        now    = time.monotonic()
        status = {}

        for cls_name, threshold in self.ALERT_THRESHOLDS.items():
            streak_start = self._streak_start[cls_name]
            last_seen    = self._last_seen[cls_name]
            still_active = (now - last_seen) <= self.GAP_TOLERANCE

            if streak_start is not None and still_active:
                elapsed = now - streak_start
                status[cls_name] = {
                    "alert":           elapsed >= threshold,
                    "elapsed_seconds": round(elapsed, 1),
                    "threshold":       threshold,
                }
            else:
                status[cls_name] = {
                    "alert":           False,
                    "elapsed_seconds": 0.0,
                    "threshold":       threshold,
                }

        return status

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
        """Clears the detection log, frame counter and streaks."""
        self.alert_log   = []
        self.frame_count = 0
        for cls_name in self.ALERT_THRESHOLDS:
            self._streak_start[cls_name] = None
            self._last_seen[cls_name]    = 0.0
        print("✅ Detection log cleared")


# ════════════════════════════════════════════════════════════════
#  EXAMPLE USAGE — webcam / video file
# ════════════════════════════════════════════════════════════════
if __name__ == "__main__":

    detector = FireSmokeDetector(
        weights = r"E:\fire_detection\results\runs\final\weights\best.pt",
        conf    = 0.45,
        iou     = 0.50,
        imgsz   = 512,
    )

    cap = cv2.VideoCapture(0)
    print("\n  Press Q to quit\n")

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        frame = detector.process(frame)

        # Print alert status every second
        status = detector.get_alert_status()
        for cls, info in status.items():
            if info["alert"]:
                print(f"🚨 ALERT: {cls.upper()} detected for {info['elapsed_seconds']}s!")

        cv2.imshow("Fire & Smoke Detection", frame)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()