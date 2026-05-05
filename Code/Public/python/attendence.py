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

        # ================= LOAD MODEL =================
        print("🔄 Loading InsightFace...")
        self.app = FaceAnalysis(name="buffalo_l")
        self.app.prepare(ctx_id=0, det_size=(320, 320))

        # ================= STORAGE =================
        self.person_embeddings = defaultdict(list)
        self.centroids = {}

        # Attendance tracking
        self.marked_names = set()
        self.attendance_log = []

        # ================= BUILD DATABASE =================
        self._build_database()

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

            faces = self.app.get(img)
            if len(faces) == 0:
                print(f"⚠️ No face found in {file}")
                continue

            emb = faces[0].embedding
            emb = emb / np.linalg.norm(emb)

            # 🔥 Use filename as person name
            person_name = os.path.splitext(file)[0]

            self.person_embeddings[person_name].append(emb)

        print("✅ Persons loaded:", len(self.person_embeddings))

        # ================= BUILD CENTROIDS =================
        for person, embs in self.person_embeddings.items():
            self.centroids[person] = np.mean(embs, axis=0)

        print("✅ Centroids created")

    # ================= ATTENDANCE =================
    def _mark_attendance(self, name):
        now = datetime.now().strftime("%H:%M:%S")
        if name not in self.marked_names:
            self.marked_names.add(name)
            self.attendance_log.append({
                "name": name,
                "time": now
            })
            print(f"Attendance Marked: {name}")

    # ================= PROCESS FRAME =================
    def process(self, frame):

        faces = self.app.get(frame)

        for face in faces:

            x1, y1, x2, y2 = map(int, face.bbox)
            emb = face.embedding
            emb = emb / np.linalg.norm(emb)

            # ================= MATCH WITH CENTROIDS =================
            best_person = None
            best_score = -1

            for person, centroid in self.centroids.items():
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

            # ================= DRAW =================
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
    

    def add_image(self, filepath, name):

        img = cv2.imread(filepath)
        if img is None:
            print("❌ Failed to load image")
            return

        faces = self.app.get(img)

        if len(faces) == 0:
            print("❌ No face found in image")
            return

        embedding = faces[0].embedding
        self.known_embeddings.append(embedding)
        self.classNames.append(name)
        print(f"✅ Added new face: {name}")
    # ================= GET RESULTS =================
    def get_results(self):
        return self.attendance_log

    # ================= RESET =================
    def reset(self):
        self.marked_names.clear()
        self.attendance_log = []