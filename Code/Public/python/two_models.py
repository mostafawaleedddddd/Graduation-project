import cv2
import numpy as np
from collections import defaultdict
from ultralytics import YOLO


def apply_nms(boxes, scores, classes, iou_threshold=0.45):
    if len(boxes) == 0:
        return [], [], []

    boxes = np.array(boxes)
    scores = np.array(scores)
    classes = np.array(classes)

    keep = []

    for cls in np.unique(classes):
        mask = classes == cls
        cls_boxes = boxes[mask]
        cls_scores = scores[mask]

        indices = cv2.dnn.NMSBoxes(
            cls_boxes.tolist(),
            cls_scores.tolist(),
            score_threshold=0.0,
            nms_threshold=iou_threshold
        )

        if len(indices) > 0:
            keep.extend(np.where(mask)[0][indices.flatten()])

    return boxes[keep], scores[keep], classes[keep]


class DualModelObjectCounter:
    def __init__(
        self,
        model1_path="best.pt",
        model2_path="yolo26n.pt",
        conf=0.25,
        iou=0.45
    ):
        self.model1 = YOLO(model1_path)
        self.model2 = YOLO(model2_path)

        self.class_names = self.model1.names
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
        enhanced = self._enhance(frame)

        r1 = self.model1(enhanced, conf=self.conf)[0]
        r2 = self.model2(enhanced, conf=self.conf)[0]

        boxes, scores, classes = [], [], []

        for res in (r1, r2):
            if res.boxes is None:
                continue

            for box in res.boxes:
                x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                boxes.append([x1, y1, x2 - x1, y2 - y1])
                scores.append(float(box.conf[0]))
                cls_id = int(box.cls[0])
                classes.append(self.class_names.get(cls_id, f"Class {cls_id}"))

        keep_boxes, keep_scores, keep_classes = apply_nms(
            boxes, scores, classes, self.iou
        )

        counts = defaultdict(int)
        out = enhanced.copy()

        for box, score, cls in zip(keep_boxes, keep_scores, keep_classes):
            x, y, w, h = map(int, box)
            cv2.rectangle(out, (x, y), (x + w, y + h), (0, 255, 0), 2)
            cv2.putText(out, f"{cls} {score:.2f}", (x, y - 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
            counts[cls] += 1

        y = 30
        for cls, cnt in counts.items():
            cv2.putText(out, f"{cls}: {cnt}", (10, y),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
            y += 30

        return out, counts
