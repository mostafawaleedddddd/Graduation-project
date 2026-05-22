import cv2
import numpy as np
import torch
import time
from datetime import datetime
from ultralytics import YOLO
import face_recognition  # <-- NEW: Added for facial memorization

class WeaponDetector:

    # Consecutive seconds of detection needed to trigger an alert
    ALERT_THRESHOLDS = {
        "gun":     2.0,
        "knife":   2.0,
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

        self._streak_start: dict[str, float | None] = {cls: None for cls in self.ALERT_THRESHOLDS}
        self._last_seen: dict[str, float] = {cls: 0.0 for cls in self.ALERT_THRESHOLDS}

        # ================= FACE MEMORIZATION (NEW) =================
        self.known_face_encodings = []
        self.known_face_ids = []
        self.next_person_id = 1

        print("✅ WeaponDetector ready")

    # ================= PROCESS FRAME =================
    def process(self, frame: np.ndarray) -> np.ndarray:
        self.frame_count += 1
        now = time.monotonic()


        # face_recognition requires RGB format
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        
        # Find face locations and compute encodings (the "memory" of the face)
        face_locations = face_recognition.face_locations(rgb_frame)
        face_encodings = face_recognition.face_encodings(rgb_frame, face_locations)

        for (top, right, bottom, left), face_encoding in zip(face_locations, face_encodings):
            # Check if this face matches any face we have seen before
            matches = face_recognition.compare_faces(self.known_face_encodings, face_encoding, tolerance=0.6)
            person_id = None
            
            if True in matches:
                # We've seen this person before, get their existing ID
                first_match_index = matches.index(True)
                person_id = self.known_face_ids[first_match_index]
            else:
                # This is a new face! Memorize it.
                self.known_face_encodings.append(face_encoding)
                self.known_face_ids.append(self.next_person_id)
                person_id = self.next_person_id
                self.next_person_id += 1

            # Draw the face bounding box and ID
            face_label = f"Person ID: {person_id}"
            cv2.rectangle(frame, (left, top), (right, bottom), (0, 255, 0), 2)
            cv2.putText(frame, face_label, (left, top - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 0), 2)


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