import os
import cv2
import numpy as np
from collections import defaultdict
from insightface.app import FaceAnalysis
from datetime import datetime

class AttendanceSystem:

    def __init__(self, dataset_path="attendance_images", threshold=0.30):

        self.dataset_path = dataset_path
        self.threshold = threshold

        # ================= LOAD MODEL ON GPU =================
        print("🔄 Loading InsightFace on GPU...")
        # providers=['CUDAExecutionProvider'] forces the math to your RTX 3050
        self.app = FaceAnalysis(name="buffalo_l", providers=['CUDAExecutionProvider'])
        # ctx_id=0 specifies the first NVIDIA GPU found
        self.app.prepare(ctx_id=0, det_size=(320, 320))
        print("✅ InsightFace running on GPU (ID: 0)")

        # ================= STORAGE =================
        self.person_embeddings = defaultdict(list)
        self.centroids = {}

        # Attendance tracking
        self.marked_names = set()
        self.attendance_log = []

        # Ensure the image folder exists to prevent errors
        if not os.path.exists(self.dataset_path):
            os.makedirs(self.dataset_path)

        # ================= BUILD DATABASE =================
        self._build_database()

    # ================= BUILD DATABASE =================
    def _build_database(self):
        print("📥 Building face database...")

        for file in os.listdir(self.dataset_path):
            img_path = os.path.join(self.dataset_path, file)

            # Skip non-image files
            if not file.lower().endswith((".jpg", ".png", ".jpeg")):
                continue

            img = cv2.imread(img_path)
            if img is None:
                continue

            # Model processing happens on GPU
            faces = self.app.get(img)
            if len(faces) == 0:
                print(f"⚠️ No face found in {file}")
                continue

            emb = faces[0].embedding
            emb = emb / np.linalg.norm(emb)

            # Use filename as person name
            person_name = os.path.splitext(file)[0]
            self.person_embeddings[person_name].append(emb)

        self._update_centroids()
        print("✅ Persons loaded:", len(self.person_embeddings))

    def _update_centroids(self):
        """Calculates the average embedding (centroid) for each person."""
        for person, embs in self.person_embeddings.items():
            self.centroids[person] = np.mean(embs, axis=0)
        print("✅ Centroids updated")

    # ================= ATTENDANCE LOGGING =================
    def _mark_attendance(self, name):
        now = datetime.now().strftime("%H:%M:%S")
        if name not in self.marked_names:
            self.marked_names.add(name)
            self.attendance_log.append({
                "name": name,
                "time": now
            })
            print(f"Attendance Marked: {name}")

    def add_image(self, filepath, name):
        """Adds a new face to the system and immediately updates the GPU-ready centroids."""
        img = cv2.imread(filepath)
        if img is None:
            print("❌ Failed to load image")
            return

        faces = self.app.get(img)

        if len(faces) == 0:
            print("❌ No face found in image")
            return

        # Fixed: Using your self.person_embeddings logic instead of non-existent classNames
        embedding = faces[0].embedding
        embedding = embedding / np.linalg.norm(embedding)
        
        self.person_embeddings[name].append(embedding)
        self._update_centroids() # Re-calculate average face for this person
        print(f"✅ Added new face: {name}")

    # ================= PROCESS FRAME =================
    def process(self, frame):
        # Face detection and feature extraction happens on GPU
        faces = self.app.get(frame)

        for face in faces:
            x1, y1, x2, y2 = map(int, face.bbox)
            emb = face.embedding
            emb = emb / np.linalg.norm(emb)

            # ================= MATCH WITH CENTROIDS =================
            best_person = None
            best_score = -1

            for person, centroid in self.centroids.items():
                # Dot product for cosine similarity
                score = np.dot(emb, centroid)

                if score > best_score:
                    best_score = score
                    best_person = person

            # ================= DECISION =================
            if best_score > self.threshold:
                name = best_person.upper()
                color = (0, 255, 0)
                self._mark_attendance(name)
            else:
                name = "UNKNOWN"
                color = (0, 0, 255)

            # ================= DRAWING (CPU) =================
            # Drawing cannot be offloaded to GPU, but with GPU math it is much faster
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            cv2.putText(
                frame,
                f"{name} ({best_score:.2f})",
                (x1, y1 - 10),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                color,
                2
            )

        return frame

    # ================= GET RESULTS =================
    def get_results(self):
        return self.attendance_log

    # ================= RESET =================
    def reset(self):
        self.marked_names.clear()
        self.attendance_log = []