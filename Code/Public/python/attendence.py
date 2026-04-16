import cv2
import face_recognition
import os
import numpy as np
from datetime import datetime


class AttendanceSystem:

    def __init__(self, image_path="attendance_images"):

        self.path = image_path
        self.images = []
        self.classNames = []

        self.encodeListKnown = []
        self.marked_names = set()
        self.attendance_log = []

        self._load_images()
        self._encode_faces()

    # ==============================
    # LOAD DATABASE IMAGES
    # ==============================
    def _load_images(self):

        myList = os.listdir(self.path)

        for cl in myList:
            curImg = cv2.imread(f"{self.path}/{cl}")

            if curImg is not None:
                self.images.append(curImg)
                self.classNames.append(os.path.splitext(cl)[0])

        print("Loaded Faces:", self.classNames)

    # ==============================
    # ENCODE FACES
    # ==============================
    def _encode_faces(self):

        for img in self.images:

            img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            encodes = face_recognition.face_encodings(img)

            if len(encodes) > 0:
                self.encodeListKnown.append(encodes[0])

        print("Face Encoding Complete")

    # ==============================
    # MARK ATTENDANCE
    # ==============================
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

    # ==============================
    # MAIN PROCESS FUNCTION
    # ==============================
    def process(self, frame):

        imgS = cv2.resize(frame, (0, 0), None, 0.25, 0.25)
        imgS = cv2.cvtColor(imgS, cv2.COLOR_BGR2RGB)

        facesCurFrame = face_recognition.face_locations(imgS)
        encodesCurFrame = face_recognition.face_encodings(imgS, facesCurFrame)

        for encodeFace, faceLoc in zip(encodesCurFrame, facesCurFrame):

            faceDis = face_recognition.face_distance(
                self.encodeListKnown,
                encodeFace
            )

            if len(faceDis) == 0:
                continue

            matchIndex = np.argmin(faceDis)

            y1, x2, y2, x1 = faceLoc
            y1, x2, y2, x1 = y1*4, x2*4, y2*4, x1*4

            if faceDis[matchIndex] < 0.5:

                name = self.classNames[matchIndex].upper()

                cv2.rectangle(
                    frame,
                    (x1, y1),
                    (x2, y2),
                    (0, 255, 0),
                    2
                )

                cv2.putText(
                    frame,
                    name,
                    (x1, y2 - 10),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.8,
                    (0, 255, 0),
                    2
                )

                self._mark_attendance(name)

            else:

                cv2.rectangle(
                    frame,
                    (x1, y1),
                    (x2, y2),
                    (0, 0, 255),
                    2
                )

                cv2.putText(
                    frame,
                    "Unknown",
                    (x1, y2 - 10),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.8,
                    (0, 0, 255),
                    2
                )

        return frame

    # ==============================
    # GET ATTENDANCE RESULTS
    # ==============================
    def get_results(self):

        return self.attendance_log

    # ==============================
    # RESET ATTENDANCE
    # ==============================
    def reset(self):

        self.marked_names.clear()
        self.attendance_log = []