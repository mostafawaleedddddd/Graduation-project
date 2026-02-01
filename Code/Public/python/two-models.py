import cv2
import numpy as np
from collections import defaultdict
from ultralytics import YOLO

# -----------------------------
# Helper function for NMS
# -----------------------------
def apply_nms(all_boxes, all_scores, all_classes, iou_threshold=0.45):
    """
    Apply Non-Max Suppression to remove overlapping boxes
    """
    if len(all_boxes) == 0:
        return [], [], []

    boxes = np.array(all_boxes)
    scores = np.array(all_scores)
    classes = np.array(all_classes)

    keep = []

    # Perform class-wise NMS
    for cls in np.unique(classes):
        cls_mask = classes == cls
        cls_boxes = boxes[cls_mask]
        cls_scores = scores[cls_mask]
        cls_indices = cv2.dnn.NMSBoxes(
            bboxes=cls_boxes.tolist(),
            scores=cls_scores.tolist(),
            score_threshold=0.0,  # already filtered by confidence
            nms_threshold=iou_threshold
        )
        if len(cls_indices) > 0:
            keep.extend(np.where(cls_mask)[0][cls_indices.flatten()])

    return boxes[keep], scores[keep], classes[keep]

# -----------------------------
# Load YOLO models directly
# -----------------------------
cap = cv2.VideoCapture("media/shelf-test.mp4")
assert cap.isOpened(), "Error opening video file"

model1 = YOLO("models/best.pt")
model2 = YOLO("models/yolo26n.pt")

# Get class names from model1
class_names = model1.names

while cap.isOpened():
    ret, frame = cap.read()
    if not ret:
        break

    # Enhance frame
    lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    l = clahe.apply(l)
    enhanced_frame = cv2.merge([l, a, b])
    enhanced_frame = cv2.cvtColor(enhanced_frame, cv2.COLOR_LAB2BGR)

    # -----------------------------
    # Run both models
    # -----------------------------
    results1 = model1(enhanced_frame, conf=0.25)[0]
    results2 = model2(enhanced_frame, conf=0.25)[0]

    # -----------------------------
    # Collect all boxes, scores, classes
    # -----------------------------
    all_boxes = []
    all_scores = []
    all_classes = []

    # Model1 boxes
    if results1.boxes is not None:
        for box in results1.boxes:
            x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
            all_boxes.append([x1, y1, x2 - x1, y2 - y1])
            all_scores.append(float(box.conf[0]))
            cls_id = int(box.cls[0])
            cls_name = class_names.get(cls_id, f"Class {cls_id}")
            all_classes.append(cls_name)

    # Model2 boxes
    if results2.boxes is not None:
        for box in results2.boxes:
            x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
            all_boxes.append([x1, y1, x2 - x1, y2 - y1])
            all_scores.append(float(box.conf[0]))
            cls_id = int(box.cls[0])
            cls_name = class_names.get(cls_id, f"Class {cls_id}")
            all_classes.append(cls_name)

    # -----------------------------
    # Apply NMS
    # -----------------------------
    keep_boxes, keep_scores, keep_classes = apply_nms(all_boxes, all_scores, all_classes, iou_threshold=0.45)

    # -----------------------------
    # Draw boxes and count
    # -----------------------------
    combined_counts = defaultdict(int)
    combined_frame = enhanced_frame.copy()

    for box, score, cls in zip(keep_boxes, keep_scores, keep_classes):
        x, y, w, h = map(int, box)
        cv2.rectangle(combined_frame, (x, y), (x + w, y + h), (0, 255, 0), 2)  # green for final NMS
        cv2.putText(combined_frame, f"{cls} {score:.2f}", (x, y - 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        combined_counts[cls] += 1

    # Overlay counts on frame
    y_offset = 30
    for class_name, count in combined_counts.items():
        text = f"{class_name}: {count}"
        cv2.putText(combined_frame, text, (10, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        y_offset += 30

    cv2.imshow("Dual YOLO ObjectCounter with NMS", combined_frame)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
