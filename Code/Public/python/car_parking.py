import cv2
import numpy as np
from PIL import Image
from sahi import AutoDetectionModel
from sahi.predict import get_sliced_prediction


class ParkingSlotDetector:
    def __init__(
        self,
        model_path="Parking.pt",
        conf=0.45,
        slice_height=640,
        slice_width=640,
        overlap_ratio=0.2,
        sahi_every_n=5,
        device="cuda",
    ):
        self.detection_model = AutoDetectionModel.from_pretrained(
            model_type="ultralytics",
            model_path=model_path,
            confidence_threshold=conf,
            device=device,
        )

        self.slice_height = slice_height
        self.slice_width = slice_width
        self.overlap_ratio = overlap_ratio
        self.sahi_every_n = sahi_every_n

        self.clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))

        self._frame_count = 0
        self._cached_detections = []

        self._colors = {
            "occupied": (0, 0, 255),
            "empty": (0, 255, 0),
        }
        self._default_color = (255, 255, 0)

    def run_setup(self):
        """
        Keep compatibility with the server flow.
        This detector does not need an interactive setup step.
        """
        return None

    def _enhance(self, frame: np.ndarray) -> np.ndarray:
        lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
        l_channel, a_channel, b_channel = cv2.split(lab)
        l_channel = self.clahe.apply(l_channel)
        enhanced = cv2.merge([l_channel, a_channel, b_channel])
        return cv2.cvtColor(enhanced, cv2.COLOR_LAB2BGR)

    def _run_sahi(self, frame_bgr: np.ndarray) -> list:
        pil_image = Image.fromarray(cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB))
        result = get_sliced_prediction(
            pil_image,
            self.detection_model,
            slice_height=self.slice_height,
            slice_width=self.slice_width,
            overlap_height_ratio=self.overlap_ratio,
            overlap_width_ratio=self.overlap_ratio,
            verbose=0,
        )
        return result.object_prediction_list

    def _get_color(self, class_name: str) -> tuple:
        return self._colors.get(class_name.lower(), self._default_color)

    def _dedupe_detections(self, detections: list, iou_threshold: float = 0.35) -> list:
        if not detections:
            return []

        filtered = []
        class_names = {d["class"].lower() for d in detections}

        for class_name in class_names:
            class_detections = [d for d in detections if d["class"].lower() == class_name]
            boxes = []
            scores = []

            for det in class_detections:
                x1, y1, x2, y2 = det["bbox"]
                boxes.append([x1, y1, max(1, x2 - x1), max(1, y2 - y1)])
                scores.append(float(det["conf"]))

            kept = cv2.dnn.NMSBoxes(
                boxes,
                scores,
                score_threshold=0.0,
                nms_threshold=iou_threshold,
            )

            if len(kept) == 0:
                continue

            kept_indices = np.array(kept).reshape(-1).tolist()
            filtered.extend(class_detections[i] for i in kept_indices)

        filtered.sort(key=lambda d: (d["bbox"][1], d["bbox"][0]))
        return filtered

    def process(self, frame: np.ndarray):
        self._frame_count += 1

        enhanced = self._enhance(frame)

        if self._frame_count % self.sahi_every_n == 0 or self._frame_count == 1:
            self._cached_detections = self._run_sahi(enhanced)

        output_frame = frame.copy()

        raw_detections = []
        for obj in self._cached_detections:
            bbox = obj.bbox
            raw_detections.append({
                "bbox": (
                    int(bbox.minx),
                    int(bbox.miny),
                    int(bbox.maxx),
                    int(bbox.maxy),
                ),
                "class": obj.category.name,
                "conf": float(obj.score.value),
            })

        detections = self._dedupe_detections(raw_detections)

        counts = {
            "total": len(detections),
            "occupied": sum(1 for d in detections if d["class"].lower() == "occupied"),
            "empty": sum(1 for d in detections if d["class"].lower() == "empty"),
        }

        hud = output_frame.copy()
        cv2.rectangle(hud, (8, 8), (330, 68), (20, 20, 20), -1)
        cv2.addWeighted(hud, 0.60, output_frame, 0.40, 0, output_frame)
        cv2.putText(
            output_frame,
            f"Total: {counts['total']}",
            (18, 33),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.75,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )
        cv2.putText(
            output_frame,
            f"Occupied: {counts['occupied']}",
            (18, 58),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.62,
            self._colors["occupied"],
            2,
            cv2.LINE_AA,
        )
        cv2.putText(
            output_frame,
            f"Free: {counts['empty']}",
            (175, 58),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.62,
            self._colors["empty"],
            2,
            cv2.LINE_AA,
        )

        box_overlay = output_frame.copy()
        for det in detections:
            x1, y1, x2, y2 = det["bbox"]
            color = self._get_color(det["class"])
            cv2.rectangle(box_overlay, (x1, y1), (x2, y2), color, -1)
            cv2.rectangle(output_frame, (x1, y1), (x2, y2), color, 2)

        cv2.addWeighted(box_overlay, 0.10, output_frame, 0.90, 0, output_frame)

        return output_frame, detections, counts
