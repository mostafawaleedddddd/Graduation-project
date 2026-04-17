import cv2
import numpy as np
from dataclasses import dataclass
from huggingface_hub import hf_hub_download
from ultralytics import YOLO

from object_countingtry import ObjectCounterBlock


class GapDetector:

    def __init__(
        self,
        hf_repo_id="akul-29/Retail-Shelf-Gap-Detection_Model",
        hf_weights_filename=None,
        conf=0.25,
        iou=0.50,
    ):
        self.repo_id = hf_repo_id
        self.weights_name = self._find_weights(hf_repo_id, hf_weights_filename)
        self.model_path = hf_hub_download(
            repo_id=hf_repo_id,
            filename=self.weights_name
        )

        self.model = YOLO(self.model_path)
        self.conf = conf
        self.iou = iou

    def _find_weights(self, repo_id, preferred):
        if preferred:
            return preferred

        for name in ("best.pt", "weights/best.pt", "model.pt", "gap_detection.pt"):
            try:
                hf_hub_download(repo_id=repo_id, filename=name)
                return name
            except Exception:
                pass

        raise RuntimeError("No weights found in HF repo")

    def process(self, frame):
        results = self.model.predict(
            source=frame,
            conf=self.conf,
            iou=self.iou,
            verbose=False
        )

        r = results[0]
        gaps = []

        if r.boxes is not None:
            boxes = r.boxes.xyxy.cpu().numpy()
            for box in boxes:
                x1, y1, x2, y2 = map(int, box)
                gaps.append((x1, y1, x2, y2))

        return gaps

def _intersection(a, b):
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b

    ix1 = max(ax1, bx1)
    iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)

    return max(0, ix2 - ix1) * max(0, iy2 - iy1)


def _area(box):
    x1, y1, x2, y2 = box
    return max(0, x2 - x1) * max(0, y2 - y1)


def _overlap_ratio(product_box, gap_box):
    inter = _intersection(product_box, gap_box)
    area = _area(product_box)

    if area == 0:
        return 0.0

    return inter / area


@dataclass
class OrchestratorConfig:
    product_model_path: str = "best.pt"
    product_conf: float = 0.25
    product_iou: float = 0.45

    gap_conf: float = 0.25
    gap_iou: float = 0.50

    suppression_threshold: float = 0.30

    product_color: tuple = (255, 0, 0)  # Blue
    gap_color: tuple = (0, 0, 255)      # Red
    thickness: int = 2

class ShelfOrchestrator:

    def __init__(self, cfg=None):
        self.cfg = cfg or OrchestratorConfig()

        self.product_detector = ObjectCounterBlock(
            model_path=self.cfg.product_model_path,
            conf=self.cfg.product_conf,
            iou=self.cfg.product_iou
        )

        self.gap_detector = GapDetector(
            conf=self.cfg.gap_conf,
            iou=self.cfg.gap_iou
        )

    def _suppress(self, products, gaps):
        surviving = []

        for pb in products:
            dominated = any(
                _overlap_ratio(pb, gb) >= self.cfg.suppression_threshold
                for gb in gaps
            )

            if not dominated:
                surviving.append(pb)

        return surviving

    def process(self, frame):
        """
        Full pipeline:
        - detect products
        - detect gaps
        - suppress overlaps
        - draw everything

        Returns annotated frame
        """

        # IMPORTANT FIX (your new format)
        _, product_boxes = self.product_detector.process(frame)

        gap_boxes = self.gap_detector.process(frame)

        surviving_products = self._suppress(product_boxes, gap_boxes)

        out = frame.copy()

        # Draw products (blue)
        for x1, y1, x2, y2 in surviving_products:
            cv2.rectangle(
                out,
                (x1, y1),
                (x2, y2),
                self.cfg.product_color,
                self.cfg.thickness
            )

        # Draw gaps (red)
        for x1, y1, x2, y2 in gap_boxes:
            cv2.rectangle(
                out,
                (x1, y1),
                (x2, y2),
                self.cfg.gap_color,
                self.cfg.thickness
            )

        print(
            f"Products: {len(product_boxes)} | "
            f"After suppression: {len(surviving_products)} | "
            f"Gaps: {len(gap_boxes)}"
        )

        return out