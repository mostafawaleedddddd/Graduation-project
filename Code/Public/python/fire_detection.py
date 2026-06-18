import cv2
import numpy as np
import torch
import time
from datetime import datetime
from threading import Thread
from ultralytics import YOLO
from emailsettings import send_email

EMAIL_JPEG_QUALITY = 95


class FireSmokeDetector:

    # How many consecutive seconds of detection trigger an alert
    ALERT_THRESHOLDS = {"fire": 3.0, "smoke": 5.0}

    # Gap tolerance: a class can be absent for this many seconds before
    # its streak resets (absorbs the occasional dropped frame without
    # resetting a genuine 3-second fire alarm)
    GAP_TOLERANCE = 1.0

    def __init__(self, weights="best_fire_2.pt", conf=0.65, iou=0.50, imgsz=512):

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
        self.colors      = {0: (160, 160, 160),    # fire  → red-orange (BGR)
                            1: (0, 80, 255)}  # smoke → grey

        # ================= ALERT TRACKING =================
        self.alert_log   = []          # list of {class, confidence, time}
        self.frame_count = 0
        self.receiver_email = None
        self._email_sent = {cls: False for cls in self.ALERT_THRESHOLDS}
        self._last_frame: np.ndarray | None = None

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
        self._last_frame = frame.copy()

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

    def set_receiver_email(self, email: str | None):
        """
        Set the email address that should receive fire/smoke alerts.
        Pass None to disable email notifications.
        """
        self.receiver_email = email
        label = email if email else "no recipient set"
        print(f"📧 Alert emails will be sent to: {label}")

    def _send_alert_email(self, cls_name: str, elapsed: float, frame: np.ndarray | None = None):
        """
        Send a one-shot email alert for the given class once the threshold is reached.
        Includes the latest frame as an attachment when available.
        """
        if self._email_sent[cls_name] or not self.receiver_email:
            return

        subject = f"🚨 {cls_name.upper()} Alert Detected"
        body = (
            f"{cls_name.upper()} has been detected continuously for "
            f"{elapsed:.1f} seconds."
        )

        image_bytes = None
        if frame is not None:
            success, encoded_img = cv2.imencode(
                ".jpg",
                frame,
                [int(cv2.IMWRITE_JPEG_QUALITY), EMAIL_JPEG_QUALITY],
            )
            if success:
                image_bytes = encoded_img.tobytes()

        def _send():
            sent = send_email(
                subject=subject,
                body=body,
                image_bytes=image_bytes,
                receiver_email=self.receiver_email,
            )
            if sent:
                print(f"✅ {cls_name.upper()} alert email sent to {self.receiver_email}")

        self._email_sent[cls_name] = True
        Thread(target=_send, daemon=True).start()

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
                is_alert = elapsed >= threshold
                status[cls_name] = {
                    "alert":           is_alert,
                    "elapsed_seconds": round(elapsed, 1),
                    "threshold":       threshold,
                }
                if is_alert and cls_name == "fire":
                    self._send_alert_email(cls_name, elapsed, frame=self._last_frame)
            else:
                status[cls_name] = {
                    "alert":           False,
                    "elapsed_seconds": 0.0,
                    "threshold":       threshold,
                }
                if not still_active:
                    self._email_sent[cls_name] = False

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
            self._email_sent[cls_name]   = False
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