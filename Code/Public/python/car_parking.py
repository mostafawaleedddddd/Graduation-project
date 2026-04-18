from ultralytics import solutions
import threading


class ParkingManagementBlock:
    def __init__(self):
        self.model = None
        self.initialized = False
        self.setting_up = False  # 🔥 important flag

        self.model_path = "best.pt"
        self.json_path = "bounding_boxes.json"

    def run_setup(self):
        if self.setting_up:
            return

        self.setting_up = True

        def setup_task():
            print("🅿️ Opening Parking Region Selector...")

            solutions.ParkingPtsSelection()

            print("✅ Regions saved. Initializing model...")

            self.model = solutions.ParkingManagement(
                model=self.model_path,
                json_file=self.json_path
            )

            self.initialized = True
            self.setting_up = False

            print("🚀 Parking model ready")

        threading.Thread(target=setup_task, daemon=True).start()

    def process(self, frame):

        # 🔥 If not initialized → trigger setup ONCE
        if not self.initialized:
            self.run_setup()
            return frame  # don't block stream

        results = self.model(frame)
        return results.plot_im