import cv2
import numpy as np
import torch
import time
from datetime import datetime
from threading import Thread
from typing import List, Optional, Tuple
from ultralytics import YOLO
from emailsettings import send_email

EMAIL_JPEG_QUALITY = 95

class WeaponDetector:

    # Consecutive seconds of detection needed to trigger an alert
    ALERT_THRESHOLDS = {
        "gun":     2.0,
        "knife":   2.0,
        "pisau":   2.0,
        "rifle":   2.0,
        "bomb":    1.0,   
        "pistol":  2.0,
        "celurit": 2.0,
        "golok":   2.0,
        "kapak":   2.0,
        "pedang":  2.0,
        "senapan": 2.0,
    }

    # A class can be absent this many seconds before its streak resets
    GAP_TOLERANCE = 1.0

    def __init__(self, weights="weapon_best.pt", conf=0.4, iou=0.5, imgsz=640):

        # ================= LOAD WEAPON MODEL =================
        print("🔄 Loading Weapon Detection model on GPU...")
        self.device = "cuda:0" if torch.cuda.is_available() else "cpu"
        self.model  = YOLO(weights)
        self.model.to(self.device)
        print(f"✅ Model loaded on: {self.device.upper()}")

        # ================= SETTINGS =================
        self.conf  = conf
        self.iou   = iou
        self.imgsz = imgsz

        self.class_names = {
            0: "celurit",
            1: "golok",
            2: "kapak",
            3: "pedang",
            4: "pisau",
            5: "pistol",
            6: "senapan",
        }

        self.colors = {
            0: (0,   0,   255),   # celurit → red
            1: (0,   140, 255),   # golok   → orange
            2: (0,   255, 255),   # kapak   → yellow
            3: (255, 0,   0  ),   # pedang  → blue
            4: (255, 0,   200),   # pisau   → purple
            5: (0,   80,  255),   # pistol  → red-orange
            6: (0,   200, 100),   # senapan → green
        }

        # ================= WEAPON ALERT TRACKING =================
        self.alert_log   = []
        self.frame_count = 0
        self.receiver_email = None
        self._email_sent = {cls: False for cls in self.ALERT_THRESHOLDS}
        self._last_frame: np.ndarray | None = None

        self._streak_start: dict[str, float | None] = {cls: None for cls in self.ALERT_THRESHOLDS}
        self._last_seen: dict[str, float] = {cls: 0.0 for cls in self.ALERT_THRESHOLDS}

        print("✅ WeaponDetector ready")

    def _box_iou(self, a: Tuple[int, int, int, int], b: Tuple[int, int, int, int]) -> float:
        x1 = max(a[0], b[0])
        y1 = max(a[1], b[1])
        x2 = min(a[2], b[2])
        y2 = min(a[3], b[3])
        inter_w = max(0, x2 - x1)
        inter_h = max(0, y2 - y1)
        inter = inter_w * inter_h
        if inter == 0:
            return 0.0
        area_a = (a[2] - a[0]) * (a[3] - a[1])
        area_b = (b[2] - b[0]) * (b[3] - b[1])
        return inter / (area_a + area_b - inter + 1e-6)

    def _assign_track_id(
        self,
        box: Tuple[int, int, int, int],
        tracked_boxes: Optional[List[Tuple[int, list[int]]]],
    ) -> Optional[int]:
        if not tracked_boxes:
            return None

        best_iou = 0.0
        best_id = None
        for track_id, coords in tracked_boxes:
            track_box = tuple(map(int, coords))
            iou = self._box_iou(box, track_box)
            if iou > best_iou:
                best_iou = iou
                best_id = track_id

        return best_id if best_iou >= 0.05 else None

    # ================= PROCESS FRAME =================
    def process(
        self,
        frame: np.ndarray,
        tracked_boxes: Optional[List[Tuple[int, list[int]]]] = None,
    ) -> np.ndarray:
        self.frame_count += 1
        now = time.monotonic()
        self._last_frame = frame.copy()

        # ── 2. WEAPON DETECTION (EXISTING) ──────────────────────────────────
        results = self.model.predict(
            source  = frame,
            conf    = self.conf,
            iou     = self.iou,
            imgsz   = self.imgsz,
            device  = self.device,
            verbose = False,
        )

        detections = results[0].boxes
        detected_this_frame: set[str] = set()

        if detections is not None and len(detections):
            for box in detections:
                x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                cls_id  = int(box.cls[0])
                conf_sc = float(box.conf[0])

                cls_name = self.class_names.get(cls_id, str(cls_id))
                color    = self.colors.get(cls_id, (0, 255, 0))
                label    = f"{cls_name.upper()} ({conf_sc:.2f})"

                if tracked_boxes is not None:
                    track_id = self._assign_track_id((x1, y1, x2, y2), tracked_boxes)
                    if track_id is not None:
                        label += f" | ID {track_id}"
                        color = (0, 255, 255)

                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.65, 2)
                cv2.rectangle(frame, (x1, y1 - th - 10), (x1 + tw + 6, y1), color, -1)
                cv2.putText(frame, label, (x1 + 3, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2)

                detected_this_frame.add(cls_name)
                self._log_detection(cls_name, conf_sc)

        # ── Update weapon streak counters ─────────────────────────────────────
        for cls_name in self.ALERT_THRESHOLDS:
            if cls_name in detected_this_frame:
                self._last_seen[cls_name] = now
                if self._streak_start[cls_name] is None:
                    self._streak_start[cls_name] = now
            else:
                gap = now - self._last_seen[cls_name]
                if gap > self.GAP_TOLERANCE:
                    self._streak_start[cls_name] = None

        return frame

    def set_receiver_email(self, email: str | None):
        """
        Set the email address that should receive weapon alerts.
        Pass None to disable email notifications.
        """
        self.receiver_email = email
        label = email if email else "no recipient set"
        print(f"📧 Weapon alert emails will be sent to: {label}")

    def _send_alert_email(self, cls_name: str, elapsed: float, frame: np.ndarray | None = None):
        """
        Send a one-shot weapon alert email once the detection threshold is reached.
        Includes the latest annotated frame when available.
        """
        if self._email_sent[cls_name] or not self.receiver_email:
            return

        subject = f"🚨 Weapon Alert Detected"
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
                image_filename="weapon_detected_frame.jpg",
                receiver_email=self.receiver_email,
            )
            if sent:
                print(f"✅ {cls_name.upper()} weapon alert email sent to {self.receiver_email}")

        self._email_sent[cls_name] = True
        Thread(target=_send, daemon=True).start()

    def process_with_context(
        self,
        frame: np.ndarray,
        tracked_boxes: Optional[List[Tuple[int, list[int]]]] = None,
    ) -> np.ndarray:
        return self.process(frame, tracked_boxes)

    # ================= ALERT STATUS & LOGGING =================
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
                if is_alert:
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

    def get_results(self) -> list:
        """Returns the full weapon detection log."""
        return self.alert_log

    def reset(self):
        """Clears the weapon detection log and streak counters."""
        self.alert_log   = []
        self.frame_count = 0
        for cls_name in self.ALERT_THRESHOLDS:
            self._streak_start[cls_name] = None
            self._last_seen[cls_name]    = 0.0
            self._email_sent[cls_name]   = False

    def _log_detection(self, cls_name: str, confidence: float):
        now = datetime.now().strftime("%H:%M:%S")
        self.alert_log.append({"class": cls_name, "confidence": round(confidence, 3), "time": now, "frame": self.frame_count})


# ════════════════════════════════════════════════════════════════
#  EXAMPLE USAGE
# ════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    detector = WeaponDetector(
        weights = "weapon_best.pt",
        conf    = 0.4,
        iou     = 0.5,
        imgsz   = 640,
    )

    cap = cv2.VideoCapture(0)
    print("\n  Press Q to quit\n")

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        # Process frame (now includes face ID and weapon detection)
        frame = detector.process(frame)

        # Print alert status
        status = detector.get_alert_status()
        for cls, info in status.items():
            if info["alert"]:
                print(f"🚨 ALERT: {cls.upper()} detected for {info['elapsed_seconds']}s!")

        cv2.imshow("Weapon Detection", frame)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()
