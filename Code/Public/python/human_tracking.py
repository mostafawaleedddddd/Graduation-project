import cv2
from ultralytics import YOLO
from reid import ReID


class HumanTracker:
    def __init__(
        self,
        model_path="yolov8s.pt",
        conf=0.35,
        iou=0.6,
        tracker_cfg="bytetrack.yaml"
    ):
        self.model = YOLO(model_path)
        self.reid = ReID()
        self.conf = conf
        self.iou = iou
        self.tracker_cfg = tracker_cfg
        self.id_map = {}
        self.next_reid_id = 1

    def process(self, frame):
        results = self.model.track(
            frame,
            persist=True,
            tracker=self.tracker_cfg,
            classes=[0],     
            conf=self.conf,
            iou=self.iou
        )

        if not results or results[0].boxes is None:
            return frame

        boxes = results[0].boxes

        for box in boxes:
            if box.id is None:
                continue

            yolo_id = int(box.id)
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            emb = self.reid.extract(frame, (x1, y1, x2, y2))
            if emb is None:
                continue
            if yolo_id not in self.id_map:
                matched_id = self.reid.match(emb)

                if matched_id is not None:
                    self.id_map[yolo_id] = matched_id
                else:
                    self.id_map[yolo_id] = self.next_reid_id
                    self.reid.remember(self.next_reid_id, emb)
                    self.next_reid_id += 1

            reid_id = self.id_map[yolo_id]
            cv2.rectangle(
                frame,
                (x1, y1),
                (x2, y2),
                (0, 255, 0),
                2
            )

            cv2.putText(
                frame,
                f"Person {reid_id}",
                (x1, y1 - 10),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 255, 0),
                2
            )

        return frame
