import cv2
import numpy as np

# ================== COLOR RANGES ==================
COLOR_RANGES = {
    'red': [
        (np.array([0, 120, 70]), np.array([10, 255, 255])),
        (np.array([170, 120, 70]), np.array([180, 255, 255]))
    ],
    'green': [(np.array([40, 50, 50]), np.array([80, 255, 255]))],
    'blue': [(np.array([100, 50, 50]), np.array([130, 255, 255]))],
    'yellow': [(np.array([20, 100, 100]), np.array([30, 255, 255]))],
    'orange': [(np.array([10, 100, 100]), np.array([20, 255, 255]))],
    'purple': [(np.array([130, 50, 50]), np.array([160, 255, 255]))],
    'pink': [(np.array([150, 50, 50]), np.array([170, 255, 255]))],
    'white': [(np.array([0, 0, 200]), np.array([180, 30, 255]))],
    'black': [(np.array([0, 0, 0]), np.array([180, 255, 30]))]
}

COLOR_DISPLAY = {
    'red': (0, 0, 255),
    'green': (0, 255, 0),
    'blue': (255, 0, 0),
    'yellow': (0, 255, 255),
    'orange': (0, 165, 255),
    'purple': (128, 0, 128),
    'pink': (203, 192, 255),
    'white': (255, 255, 255),
    'black': (0, 0, 0)
}

DEFAULT_COLORS = ['red', 'green', 'blue', 'yellow', 'orange']

# ================== INTERNAL HELPERS ==================
def _detect_color(frame, color_name):
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    mask = np.zeros(hsv.shape[:2], dtype=np.uint8)

    for lower, upper in COLOR_RANGES[color_name]:
        mask |= cv2.inRange(hsv, lower, upper)

    kernel = np.ones((3, 3), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

    contours, _ = cv2.findContours(
        mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )
    return contours

def _draw_detections(frame, color_name, contours, min_area):
    color = COLOR_DISPLAY[color_name]

    for c in contours:
        if cv2.contourArea(c) < min_area:
            continue

        x, y, w, h = cv2.boundingRect(c)
        cv2.rectangle(frame, (x, y), (x + w, y + h), color, 2)
        cv2.putText(
            frame,
            color_name.upper(),
            (x, y - 5),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            color,
            2
        )

# ================== PUBLIC PIPELINE FUNCTION ==================
def apply_color_detection(frame, config=None):
    """
    frame: OpenCV BGR frame
    config: optional dict (colors, min_area)
    returns: modified frame
    """

    if config is None:
        config = {}

    colors = config.get("colors", DEFAULT_COLORS)
    min_area = config.get("min_area", 300)

    output = frame.copy()

    for color_name in colors:
        if color_name not in COLOR_RANGES:
            continue
        contours = _detect_color(frame, color_name)
        _draw_detections(output, color_name, contours, min_area)

    return output
