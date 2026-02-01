import cv2
from ultralytics import solutions


class ObjectCounterBlock:
    def __init__(
        self,
        model_path="best.pt",
        conf=0.25,
        iou=0.45,
        tracker="bytetrack.yaml",
        region=None
    ):
        self.counter = solutions.ObjectCounter(
            model=model_path,
            region=region,
            tracker=tracker,
            classes=None,
            conf=conf,
            iou=iou,
            show=False
        )

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
        Runs object detection + tracking + counting.
        Returns annotated frame.
        """
        enhanced = self._enhance(frame)
        results = self.counter(enhanced)
        return results.plot_im
