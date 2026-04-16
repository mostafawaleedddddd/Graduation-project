import cv2
import numpy as np
from ultralytics import YOLO


class HeatmapProcessor:
    def __init__(self, shape, decay, blur_r, blur_s, config):
        self.heatmap = np.zeros(shape, dtype=np.float32)
        self.decay = decay
        self.blur_r = blur_r
        self.blur_s = blur_s
        self.config = config

    def update(self, footprints):
        self.heatmap *= self.decay
        for (cx, cy, conf) in footprints:
            cv2.circle(
                self.heatmap,
                (cx, cy),
                self.config["HEAT_RADIUS"],
                conf * 1.5,
                -1
            )

    def apply_overlay(self, frame):
        blur_k = self.config["BLUR_R"] | 1
        blurred = cv2.GaussianBlur(self.heatmap, (blur_k, blur_k), self.config["BLUR_S"])

        p_max = np.percentile(blurred, self.config["NORM_PERCENTILE"]) if blurred.max() > 0 else 1.0
        if p_max == 0:
            p_max = 1.0

        heatmap_uint8 = np.clip(blurred / p_max * 255, 0, 255).astype(np.uint8)
        heatmap_color = cv2.applyColorMap(heatmap_uint8, self.config["COLORMAP"])

        alpha = (heatmap_uint8 / 255.0) ** self.config["ALPHA_POWER"]

        # Raised threshold so faint/residual heat becomes fully transparent
        threshold_mask = (heatmap_uint8 > 30).astype(np.float32)
        alpha = alpha * threshold_mask

        alpha_3ch = np.stack([alpha] * 3, axis=-1)
        blend = self.config["ALPHA_BLEND"]

        overlay = (
            frame * (1 - alpha_3ch * blend) +
            heatmap_color * (alpha_3ch * blend)
        ).astype(np.uint8)

        return overlay

    def reset(self):
        self.heatmap[:] = 0


class HeatmapBlock:
    def __init__(self):

        self.config = {
            # Slower decay (0.92 vs 0.7) — heat fades naturally over ~12 frames
            # Increase toward 0.99 for longer session-wide memory
            "DECAY": 0.92,

            "BLUR_R": 35,           # Reduced spread for smaller heatmap
            "BLUR_S": 15,

            # Smaller footprint radius
            "HEAT_RADIUS": 18,

            # Higher value = faint areas become transparent, only hot spots glow
            "ALPHA_POWER": 0.6,

            "ALPHA_BLEND": 0.85,
            "COLORMAP": cv2.COLORMAP_JET,

            # Higher percentile = only truly busy areas stay bright
            "NORM_PERCENTILE": 97,

            "MODE": "retail"        # or "cars"
        }

        self.classes = {
            "PERSON": 0,
            "CARS": [2, 3, 5, 7]
        }

        self.model = YOLO("yolov8n_heatmap.pt")

        self.processor = None
        self.initialized = False

    def initialize(self, frame_shape):
        h, w = frame_shape[:2]
        self.processor = HeatmapProcessor(
            (h, w),
            self.config["DECAY"],
            self.config["BLUR_R"],
            self.config["BLUR_S"],
            self.config
        )
        self.initialized = True
        print("🔥 Heatmap initialized")

    def process(self, frame):

        if not self.initialized:
            self.initialize(frame.shape)

        results = self.model(frame, verbose=False)[0]

        current_footprints = []
        boxes_to_draw = []
        detection_count = 0

        for box in results.boxes:
            cls = int(box.cls[0])
            conf = float(box.conf[0])

            is_retail = self.config["MODE"] == "retail" and cls == self.classes["PERSON"]
            is_cars = self.config["MODE"] == "cars" and cls in self.classes["CARS"]

            if is_retail or is_cars:
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                cx = (x1 + x2) // 2

                # FIX: Only mark the foot/bottom of the bounding box instead of
                # sampling the full body height. This ensures heat accumulates
                # on the floor where people actually stand/walk, not their torso.
                foot_y = y2
                current_footprints.append((cx, foot_y, conf))

                detection_count += 1
                boxes_to_draw.append((x1, y1, x2, y2, conf, is_retail))

        # Update heatmap
        self.processor.update(current_footprints)

        # Apply overlay
        overlay = self.processor.apply_overlay(frame)

        # Draw boxes on top
        for (x1, y1, x2, y2, conf, is_ret) in boxes_to_draw:
            cv2.rectangle(overlay, (x1, y1), (x2, y2), (0, 255, 0), 2)
            label = f"{'Person' if is_ret else 'Vehicle'} {conf:.2f}"
            cv2.putText(overlay, label, (x1, y1 - 8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)

        # HUD
        cv2.putText(overlay, f"Mode: {self.config['MODE'].upper()}", (10, 25),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

        cv2.putText(overlay, f"Detected: {detection_count}", (10, 55),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)

        return overlay

    def reset(self):
        if self.processor:
            self.processor.reset()