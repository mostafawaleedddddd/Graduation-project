from pathlib import Path
from threading import Thread
from time import perf_counter
from datetime import datetime
from collections import deque

import numpy as np
import torch
import cv2
from ultralytics import YOLO
import supervision as sv
from emailsettings import send_email


# ================= CONFIGURATION =================
MODEL_CANDIDATES = (
    "yolov8n.pt",
    "yolo26n.pt",
)
INFERENCE_IMAGE_SIZE = 416
INFERENCE_EVERY_N_FRAMES = 2
EMAIL_JPEG_QUALITY = 95
ALERT_RESET_FRAMES = 45  # Reset alert after 45 frames of no detection
UNKNOWN_ALERT_SECONDS = 5.0  # Require 5 consecutive seconds of unknowns before alerting


def send_security_alert_async(people_count=1, frame=None, receiver_email=None):
    """
    Send security alert email asynchronously.

    receiver_email: the logged-in user's address. Email is only sent when
                    a logged-in user email is provided.
    """
    if not receiver_email:
        print("⚠️ No alert recipient set. Skipping security email.")
        return False
    image_bytes = None
    if frame is not None:
        success, encoded_img = cv2.imencode(
            ".jpg",
            frame,
            [int(cv2.IMWRITE_JPEG_QUALITY), EMAIL_JPEG_QUALITY],
        )
        if success:
            image_bytes = encoded_img.tobytes()

    sent = send_email(
        subject=f"Security Alert: {people_count} people detected",
        body=f"ALERT - {people_count} person detected in the latest camera frame.",
        image_bytes=image_bytes,
        receiver_email=receiver_email,
    )
    if sent:
        print("✅ Alert email sent to", receiver_email)


class SecuritySystem:
    """Security monitoring system for real-time person detection and threat alerts."""

    def __init__(self, confidence_threshold=0.5, enable_email_alerts=True,
                 receiver_email=None):
        """
        Initialize the SecuritySystem.

        Args:
            confidence_threshold: Confidence threshold for person detection
            enable_email_alerts:  Enable email alerts for intrusions
            receiver_email:       Address to send alerts to.  Can be set later
                                  via set_receiver_email().
        """
        self.confidence_threshold = confidence_threshold
        self.enable_email_alerts  = enable_email_alerts
        self.receiver_email       = receiver_email

        self.device = "cuda" if torch.cuda.is_available() else "cpu"

        if self.device == "cuda":
            torch.backends.cudnn.benchmark = True

        print(f"🔒 Security System initializing on {self.device.upper()}")

        # ================= LOAD GPU MODEL =================
        self.model = self._load_model()
        self.model_path = self.model.ckpt_path or "loaded model"
        self.class_names = self.model.model.names

        # Find person class IDs
        self.person_class_ids = [
            int(class_id)
            for class_id, class_name in self.class_names.items()
            if class_name.lower() == "person"
        ]

        if not self.person_class_ids:
            print("⚠️ Warning: model has no 'person' class. Model names:", self.class_names)
        else:
            print(f"✅ Person detection ready. Class IDs: {self.person_class_ids}")
            print(f"📦 Model: {self.model_path}")

        # ================= VISUALIZATION TOOLS =================
        self.box_annotator   = sv.BoxAnnotator(thickness=2)
        self.label_annotator = sv.LabelAnnotator()

        # ================= STATE MANAGEMENT =================
        self.alert_active           = False
        self.missing_person_frames  = 0
        self.absence_reset_frames   = ALERT_RESET_FRAMES
        self.unknown_alert_start    = None
        self.unknown_alert_sent     = False
        self.last_frame_time        = perf_counter()
        self.current_fps            = 0.0
        self.frame_counter          = 0
        self.last_results           = None

        # ================= SECURITY LOG =================
        self.detection_log = deque(maxlen=100)
        self.alert_log     = deque(maxlen=50)

        print("✅ Security System initialized successfully")

    # ──────────────────────────────────────────────────────────────────────────
    # Public API: set the alert recipient at runtime
    # ──────────────────────────────────────────────────────────────────────────

    def set_receiver_email(self, email: str | None) -> None:
        """
        Update the email address that receives security alerts.

        Called by the FastAPI server whenever a user's session email is
        known (e.g. after login or when the Security pipeline is activated).

        Pass None to revert to the hardcoded fallback in emailsettings.py.
        """
        self.receiver_email = email or None
        label = email if email else "no recipient set"
        print(f"📧 Security alerts will be sent to: {label}")

    # ──────────────────────────────────────────────────────────────────────────

    def _load_model(self):
        """Load YOLO model with person detection capability."""
        for candidate in MODEL_CANDIDATES:
            candidate_path = Path(__file__).with_name(candidate)
            if not candidate_path.exists():
                continue

            model = YOLO(str(candidate_path))
            model.fuse()

            names = model.model.names
            has_person = any(str(name).lower() == "person" for name in names.values())
            if has_person:
                print(f"📦 Loaded model: {candidate}")
                return model

        raise FileNotFoundError(
            f"❌ Could not find YOLO model with 'person' class. "
            f"Tried: {', '.join(MODEL_CANDIDATES)}"
        )

    def _process_frame_gpu(self, frame):
        """Run YOLO inference on GPU."""
        return self.model(
            frame,
            conf=self.confidence_threshold,
            classes=self.person_class_ids or None,
            device=self.device,
            imgsz=INFERENCE_IMAGE_SIZE,
            half=self.device == "cuda",
            verbose=False,
        )

    def _update_fps(self):
        """Update FPS calculation."""
        now   = perf_counter()
        delta = now - self.last_frame_time
        if delta > 0:
            instant_fps = 1.0 / delta
            self.current_fps = (
                instant_fps
                if self.current_fps == 0
                else (self.current_fps * 0.85 + instant_fps * 0.15)
            )
        self.last_frame_time = now

    def _annotate_frame(self, frame, detections, labels, person_count):
        """Draw bounding boxes and labels on frame."""
        annotated_frame = self.box_annotator.annotate(
            scene=frame.copy(),
            detections=detections,
        )
        annotated_frame = self.label_annotator.annotate(
            scene=annotated_frame,
            detections=detections,
            labels=labels,
        )

        text  = f"People: {person_count} | FPS: {self.current_fps:.1f}"
        color = (0, 255, 0) if person_count == 0 else (0, 165, 255)
        cv2.putText(annotated_frame, text, (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)

        if self.alert_active:
            cv2.putText(annotated_frame, "🚨 ALERT ACTIVE 🚨", (10, 70),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)

        return annotated_frame

    def _log_detection(self, person_count):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.detection_log.append({
            "timestamp":    timestamp,
            "people_count": person_count,
            "alert_active": self.alert_active,
        })

    def _log_alert(self, person_count):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.alert_log.append({
            "timestamp":    timestamp,
            "people_count": person_count,
            "message":      f"Security alert: {person_count} person(s) detected",
        })

    def _run_detection(self, frame):
        self._update_fps()
        self.frame_counter += 1

        should_infer = (
            self.last_results is None
            or self.frame_counter % INFERENCE_EVERY_N_FRAMES == 0
        )
        if should_infer:
            self.last_results = self._process_frame_gpu(frame)

        results = self.last_results

        detections = sv.Detections.from_ultralytics(results[0])
        labels = []
        person_count = 0

        if results[0].boxes is not None and results[0].boxes.cls is not None:
            confidences = results[0].boxes.conf.tolist()
            for cls, confidence in zip(results[0].boxes.cls, confidences):
                class_id = int(cls)
                if class_id in self.person_class_ids:
                    person_count += 1
                    labels.append(f"person {confidence:.2f}")

        return frame, detections, labels, person_count

    def _finalize_frame(self, frame, detections, labels, person_count, allow_email=True):
        if person_count > 0:
            self.missing_person_frames = 0
            self._log_detection(person_count)

            if not self.alert_active and allow_email and self.enable_email_alerts:
                alert_frame = self._annotate_frame(frame, detections, labels, person_count)
                Thread(
                    target=send_security_alert_async,
                    kwargs={
                        "people_count":   person_count,
                        "frame":          alert_frame.copy(),
                        "receiver_email": self.receiver_email,
                    },
                    daemon=True,
                ).start()

                self._log_alert(person_count)
                self.alert_active = True
                print(f"🚨 SECURITY ALERT: {person_count} person(s) detected!")
        else:
            self.missing_person_frames += 1
            self._log_detection(person_count)

            if (self.alert_active
                    and self.missing_person_frames >= self.absence_reset_frames):
                self.alert_active          = False
                self.missing_person_frames = 0
                print("✅ Scene cleared. Ready for next detection.")

        return self._annotate_frame(frame, detections, labels, person_count)

    def process(self, frame):
        frame, detections, labels, person_count = self._run_detection(frame)
        return self._finalize_frame(frame, detections, labels, person_count, allow_email=True)

    def process_with_context(self, frame, tracked_boxes, attendance_info):
        if not attendance_info:
            self.unknown_alert_start = None
            self.unknown_alert_sent = False
            return self.process(frame)

        recognitions = attendance_info.get("recognitions", [])
        has_known = any(rec.get("name") != "UNKNOWN" for rec in recognitions)
        has_unknown = any(rec.get("name") == "UNKNOWN" for rec in recognitions)

        if has_known:
            self.unknown_alert_start = None
            self.unknown_alert_sent = False
            allow_email = False
        elif has_unknown:
            now = perf_counter()
            if self.unknown_alert_start is None:
                self.unknown_alert_start = now
            elapsed = now - self.unknown_alert_start
            allow_email = elapsed >= UNKNOWN_ALERT_SECONDS and not self.unknown_alert_sent
            if allow_email:
                self.unknown_alert_sent = True
        else:
            self.unknown_alert_start = None
            self.unknown_alert_sent = False
            allow_email = False

        frame, detections, labels, person_count = self._run_detection(frame)
        result = self._finalize_frame(frame, detections, labels, person_count, allow_email=allow_email)

        if has_known and self.alert_active:
            self.alert_active = False

        if person_count == 0:
            self.unknown_alert_start = None
            self.unknown_alert_sent = False

        return result

    def get_results(self):
        """Get security detection log."""
        return {
            "detections":    list(self.detection_log),
            "alerts":        list(self.alert_log),
            "alert_active":  self.alert_active,
            "total_alerts":  len(self.alert_log),
            "alert_email":   self.receiver_email,
        }

    def reset(self):
        """Reset security system state."""
        self.alert_active          = False
        self.missing_person_frames = 0
        self.detection_log.clear()
        self.alert_log.clear()
        print("🔄 Security system reset")