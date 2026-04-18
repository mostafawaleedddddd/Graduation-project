import cv2
from ultralytics import YOLO


class ObjectCounterBlock:

    def __init__(
        self,
        model_path="best.pt",
        conf=0.25,
        iou=0.45,
    ):
        self.model = YOLO(model_path)
        self.conf = conf
        self.iou = iou

        self.clahe = cv2.createCLAHE(
            clipLimit=2.0,
            tileGridSize=(8, 8)
        )

    def _enhance(self, frame):
        lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        l = self.clahe.apply(l)
        enhanced = cv2.merge([l, a, b])
        return cv2.cvtColor(enhanced, cv2.COLOR_LAB2BGR)

    def process(self, frame):
        """
        Runs object detection only (no tracker, no labels).

        Returns:
        - annotated_frame (with plain bounding boxes only)
        - detections list [(x1, y1, x2, y2), ...]
        """

        enhanced = self._enhance(frame)

        results = self.model.predict(
            source=enhanced,
            conf=self.conf,
            iou=self.iou,
            verbose=False
        )

        r = results[0]
        detections = []

        output_frame = frame.copy()

        if r.boxes is not None:
            boxes = r.boxes.xyxy.cpu().numpy()

            for box in boxes:
                x1, y1, x2, y2 = map(int, box)
                detections.append((x1, y1, x2, y2))

                cv2.rectangle(output_frame, (x1, y1), (x2, y2), (255, 0, 0), 2)

        return output_frame, detections