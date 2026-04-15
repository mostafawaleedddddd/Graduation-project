import cv2
from ultralytics import solutions


class ParkingManagementBlock:
    def __init__(self):
        self.model = None
        self.initialized = False

        # paths (you can change later)
        self.model_path = "best.pt"
        self.json_path = "parking_regions.json"

    # ==============================
    # STEP 1: RUN REGION SELECTION
    # ==============================
    def setup_parking_regions(self):
        """
        This runs the UI to draw parking regions
        and generates the JSON file.
        """
        print("🅿️ Launching Parking Region Selector...")

        solutions.ParkingPtsSelection()

        print("✅ Parking regions saved!")

    # ==============================
    # STEP 2: INITIALIZE MODEL
    # ==============================
    def initialize(self):
        """
        Initialize model AFTER selecting regions.
        """
        if not self.initialized:
            self.setup_parking_regions()

            self.model = solutions.ParkingManagement(
                model=self.model_path,
                json_file=self.json_path
            )

            self.initialized = True
            print("🚀 Parking model initialized")

    # ==============================
    # STEP 3: PROCESS FRAME
    # ==============================
    def process(self, frame):
        """
        Run parking detection on frame.
        """
        if not self.initialized:
            self.initialize()

        results = self.model(frame)

        # return annotated frame
        return results.plot_im