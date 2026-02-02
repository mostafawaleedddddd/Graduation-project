import cv2
import numpy as np
from dataclasses import dataclass
from typing import Any
from huggingface_hub import hf_hub_download
from ultralytics import YOLO


# ================= CONFIG =================
@dataclass
class GapConfig:
    hf_repo_id: str = "akul-29/Retail-Shelf-Gap-Detection_Model"
    hf_weights_filename: str | None = None
    conf: float = 0.25
    iou: float = 0.5


# ================= MODEL LOADING =================
def find_weights_file(repo_id: str, preferred: str | None) -> str:
    if preferred:
        return preferred

    candidates = [
        "best.pt",
        "weights/best.pt",
        "model.pt",
        "gap_detection.pt",
    ]

    for name in candidates:
        try:
            hf_hub_download(repo_id=repo_id, filename=name)
            return name
        except Exception:
            pass

    raise RuntimeError("Could not find YOLO weights file in HF repo")


def load_model(cfg: GapConfig) -> YOLO:
    weights = find_weights_file(cfg.hf_repo_id, cfg.hf_weights_filename)
    local_path = hf_hub_download(repo_id=cfg.hf_repo_id, filename=weights)
    return YOLO(local_path)


# ================= UTILS =================
def annotate(frame: np.ndarray, dets: list[dict[str, Any]]) -> np.ndarray:
    out = frame.copy()

    for d in dets:
        x1, y1, x2, y2 = map(int, d["xyxy"])
        conf = d["conf"]
        label = d["label"]

        cv2.rectangle(out, (x1, y1), (x2, y2), (0, 0, 255), 2)
        cv2.putText(
            out,
            f"{label} {conf:.2f}",
            (x1, y1 - 6),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0, 0, 255),
            2
        )

    return out


# ================= PIPELINE CLASS =================
class ShelfGapDetector:
    def __init__(self, cfg: GapConfig | None = None):
        self.cfg = cfg or GapConfig()
        self.model = load_model(self.cfg)

    def process(self, frame: np.ndarray) -> np.ndarray:
        """
        Apply shelf gap detection to a single frame
        """
        results = self.model.predict(
            source=frame,
            conf=self.cfg.conf,
            iou=self.cfg.iou,
            verbose=False
        )

        r = results[0]
        dets = []

        if r.boxes is not None:
            boxes = r.boxes.xyxy.cpu().numpy()
            confs = r.boxes.conf.cpu().numpy()
            cls_ids = r.boxes.cls.cpu().numpy().astype(int)
            names = r.names or {}

            for xyxy, conf, cls_id in zip(boxes, confs, cls_ids):
                dets.append({
                    "xyxy": xyxy.tolist(),
                    "conf": float(conf),
                    "label": names.get(cls_id, "gap")
                })

        return annotate(frame, dets)
