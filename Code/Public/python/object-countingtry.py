import cv2
from ultralytics import solutions

# Load recorded video
cap = cv2.VideoCapture("media/shelf-test.mp4")
assert cap.isOpened(), "Error opening video file"

# Define shelf region to focus detection (adjust for your video)
# region_points = [
#     (100, 200),   # top-left
#     (900, 200),   # top-right
#     (900, 450),   # bottom-right
#     (100, 450)    # bottom-left
# ]

# Initialize object counter with enhanced accuracy settings
counter = solutions.ObjectCounter(
    model="models/best.pt",        # Use medium model for better accuracy (was yolov8s)
    # region=region_points,      # Focus on shelf region
    tracker="bytetrack.yaml",  # stable tracking
    classes=None,              # detect all objects
    conf=0.25,                 # confidence threshold (balanced for accuracy)
    iou=0.45,                  # IOU threshold for NMS
    show=False                 # manual display
)

while cap.isOpened():
    ret, frame = cap.read()
    if not ret:
        print("Video finished or cannot read frame")
        break

    # Enhance image for better detection using CLAHE (Contrast Limited Adaptive Histogram Equalization)
    lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    l = clahe.apply(l)
    enhanced_frame = cv2.merge([l, a, b])
    enhanced_frame = cv2.cvtColor(enhanced_frame, cv2.COLOR_LAB2BGR)

    # Detect, track & count
    results = counter(enhanced_frame)

    # Show live processed frame
    cv2.imshow("Shelf Object Counting - RECORDED", results.plot_im)

    # Press 'q' to exit early
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
