import cv2
import os
import numpy as np
from datetime import datetime
from insightface.app import FaceAnalysis


class AttendanceSystem:

    def __init__(self, image_path="attendance_images"):

        self.path = image_path

        self.known_embeddings = []
        self.classNames = []

        self.marked_names = set()
        self.attendance_log = []

        # 🔥 Load InsightFace model
        self.app = FaceAnalysis(name="buffalo_l")
        self.app.prepare(ctx_id=0, det_size=(640, 640))

        self._load_images()


    def _load_images(self):

        for file in os.listdir(self.path):

            img_path = os.path.join(self.path, file)
            img = cv2.imread(img_path)

            if img is None:
                continue

            faces = self.app.get(img)

            if len(faces) == 0:
                continue

            embedding = faces[0].embedding
            self.known_embeddings.append(embedding)

            name = os.path.splitext(file)[0]
            self.classNames.append(name)

        print("✅ Loaded Faces:", self.classNames)


    def _mark_attendance(self, name):

        if name not in self.marked_names:

            self.marked_names.add(name)

            now = datetime.now()
            dtString = now.strftime("%H:%M:%S")

            record = {
                "name": name,
                "time": dtString
            }

            self.attendance_log.append(record)

            print("Attendance Marked:", record)


    def process(self, frame):

        faces = self.app.get(frame)

        for face in faces:

            x1, y1, x2, y2 = map(int, face.bbox)
            embedding = face.embedding

            if len(self.known_embeddings) == 0:
                continue

            # 🔥 Cosine similarity
            sims = np.dot(self.known_embeddings, embedding) / (
                np.linalg.norm(self.known_embeddings, axis=1) * np.linalg.norm(embedding)
            )

            best_match = np.argmax(sims)

            if sims[best_match] > 0.6:  # threshold (0.4–0.6)

                name = self.classNames[best_match].upper()

                color = (0, 255, 0)
                self._mark_attendance(name)

            else:
                name = "UNKNOWN"
                color = (0, 0, 255)

            # DRAW
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            cv2.putText(frame, name, (x1, y2 - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)

        return frame


    def get_results(self):
        return self.attendance_log

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

        
    def reset(self):
        self.marked_names.clear()
        self.attendance_log = []