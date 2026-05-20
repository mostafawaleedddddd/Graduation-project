import os

# =========================================================
# TENSORRT + FP16
# =========================================================

os.environ["ORT_TENSORRT_FP16_ENABLE"] = "1"

import cv2
import numpy as np
from collections import defaultdict
from insightface.app import FaceAnalysis
from datetime import datetime

BASE_DATASET_PATH = r"attendance_images"


class AttendanceSystem:

    def __init__(
        self,
        dataset_path: str | None = None,
        threshold: float = 0.30,
        frame_skip: int = 2,
    ):

        self.base_dataset_path = dataset_path if dataset_path else BASE_DATASET_PATH
        self.dataset_path = self.base_dataset_path

        self.threshold = threshold

        # =====================================================
        # FRAME SKIP
        # =====================================================

        self.frame_skip = frame_skip
        self.frame_count = 0

        self.cached_faces = []

        # =====================================================
        # INSIGHTFACE GPU INIT
        # =====================================================

        print("🔄 Initializing GPU Attendance System...")

        self.app = FaceAnalysis(
            name="buffalo_l",
            providers=[
                "TensorrtExecutionProvider",
                "CUDAExecutionProvider",
                "CPUExecutionProvider",
            ],
        )

        # 320 is much faster than 640
        self.app.prepare(
            ctx_id=0,
            det_size=(320, 320),
        )

        print("✅ InsightFace initialized with TensorRT")

        # =====================================================
        # DATABASE
        # =====================================================

        self.person_embeddings: dict[str, list[np.ndarray]] = defaultdict(list)

        self._centroid_matrix = None
        self._centroid_names = []

        # =====================================================
        # ATTENDANCE STATE
        # =====================================================

        self.marked_names = set()
        self.attendance_log = []

        if not os.path.exists(self.dataset_path):
            os.makedirs(self.dataset_path)

        self._build_database()

    # =========================================================
    # DATABASE BUILD
    # =========================================================

    def _build_database(self):

        print(f"📥 Building attendance database: {self.dataset_path}")

        for root, _, files in os.walk(self.dataset_path):

            for file in files:

                if not file.lower().endswith(
                    (".jpg", ".jpeg", ".png")
                ):
                    continue

                path = os.path.join(root, file)

                img = cv2.imread(path)

                if img is None:
                    continue

                rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

                faces = self.app.get(rgb)

                if len(faces) == 0:
                    print(f"⚠️ No face found in {file}")
                    continue

                emb = self._normalize(faces[0].embedding)

                name = os.path.splitext(file)[0]

                self.person_embeddings[name].append(emb)

        self._update_centroids()

        print(f"✅ Loaded {len(self.person_embeddings)} persons")

    # =========================================================
    # CENTROIDS
    # =========================================================

    def _update_centroids(self):

        if not self.person_embeddings:
            self._centroid_matrix = None
            self._centroid_names = []
            return

        self._centroid_names = list(self.person_embeddings.keys())

        self._centroid_matrix = np.stack(
            [
                np.mean(embs, axis=0)
                for embs in self.person_embeddings.values()
            ],
            axis=0,
        ).astype(np.float32)

        print(
            f"✅ Centroids updated "
            f"({len(self._centroid_names)} persons)"
        )

    # =========================================================
    # MAIN PROCESS
    # =========================================================

    def process(self, frame: np.ndarray):

        if self._centroid_matrix is None:
            return frame

        self.frame_count += 1

        # =====================================================
        # FAST RGB CONVERSION
        # =====================================================

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        # =====================================================
        # DETECT ONLY EVERY N FRAMES
        # =====================================================

        if self.frame_count % self.frame_skip == 0:

            faces = self.app.get(rgb)

            self.cached_faces = faces

        else:

            faces = self.cached_faces

        # =====================================================
        # FACE RECOGNITION
        # =====================================================

        for face in faces:

            x1, y1, x2, y2 = map(int, face.bbox)

            emb = self._normalize(face.embedding)

            best_idx, best_score = self._match_embedding(emb)

            # =================================================
            # DECISION
            # =================================================

            if best_score > self.threshold:

                name = self._centroid_names[best_idx].upper()

                color = (0, 255, 0)

                self._mark_attendance(name)

            else:

                name = "UNKNOWN"

                color = (0, 0, 255)

            # =================================================
            # DRAW
            # =================================================

            cv2.rectangle(
                frame,
                (x1, y1),
                (x2, y2),
                color,
                2,
            )

            cv2.putText(
                frame,
                f"{name} {best_score:.2f}",
                (x1, y1 - 10),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                color,
                2,
            )

        return frame

    # =========================================================
    # MATCHING
    # =========================================================

    def _match_embedding(self, emb):

        scores = self._centroid_matrix @ emb

        best_idx = int(np.argmax(scores))

        best_score = float(scores[best_idx])

        return best_idx, best_score

    # =========================================================
    # NORMALIZATION
    # =========================================================

    @staticmethod
    def _normalize(emb):

        norm = np.linalg.norm(emb)

        if norm > 0:
            emb = emb / norm

        return emb.astype(np.float32)

    # =========================================================
    # ATTENDANCE
    # =========================================================

    def _mark_attendance(self, name):

        if name not in self.marked_names:

            self.marked_names.add(name)

            self.attendance_log.append(
                {
                    "name": name,
                    "time": datetime.now().strftime("%H:%M:%S"),
                }
            )

            print(f"✅ Attendance marked: {name}")

    # =========================================================
    # PUBLIC API
    # =========================================================

    def add_image(self, filepath: str, name: str):

        img = cv2.imread(filepath)

        if img is None:
            print("❌ Failed to load image")
            return

        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

        faces = self.app.get(rgb)

        if len(faces) == 0:
            print("❌ No face found")
            return

        emb = self._normalize(faces[0].embedding)

        self.person_embeddings[name].append(emb)

        self._update_centroids()

        print(f"✅ Added face: {name}")

    def get_results(self):

        return self.attendance_log

    def reset(self):

        self.marked_names.clear()

        self.attendance_log.clear()

    def set_class(self, class_name: str | None = None):

        new_path = (
            os.path.join(self.base_dataset_path, class_name)
            if class_name
            else self.base_dataset_path
        )

        if not os.path.exists(new_path):
            os.makedirs(new_path)

        self.dataset_path = new_path

        self.person_embeddings.clear()

        self._centroid_matrix = None

        self._centroid_names = []

        self.marked_names.clear()

        self.attendance_log.clear()

        self.cached_faces = []

        self.frame_count = 0

        self._build_database()

        print(
            f"✅ Switched class → "
            f"{class_name or 'DEFAULT'}"
        )