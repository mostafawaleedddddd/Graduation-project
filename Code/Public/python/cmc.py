import cv2
import numpy as np


class CameraMotionCompensation:
    """
    Estimates the inter-frame camera motion as a 2×3 affine matrix using
    sparse optical-flow (Lucas-Kanade on Shi-Tomasi corners).

    Usage
    -----
    Call `warp(frame)` every frame.  The returned matrix can be passed to
    `KalmanBoxTracker.apply_affine()` so that predicted track positions are
    corrected for camera pan/zoom/rotation before association.
    """

    def __init__(self):
        self.prev_gray: np.ndarray | None = None

    def warp(self, frame: np.ndarray) -> np.ndarray:
        """
        Compute the 2×3 affine transform that maps the previous frame's
        coordinate system to the current frame's.

        Returns the identity matrix when:
          - this is the first frame (no previous frame), or
          - optical-flow or affine estimation fails.
        """
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        if self.prev_gray is None:
            self.prev_gray = gray
            return np.eye(2, 3, dtype=np.float32)

        # Detect good features in the *previous* frame
        pts1 = cv2.goodFeaturesToTrack(
            self.prev_gray,
            maxCorners=200,
            qualityLevel=0.01,
            minDistance=30,
        )

        if pts1 is None or len(pts1) < 4:
            self.prev_gray = gray
            return np.eye(2, 3, dtype=np.float32)

        # Track those features into the current frame
        pts2, status, _ = cv2.calcOpticalFlowPyrLK(
            self.prev_gray, gray, pts1, None
        )

        good1 = pts1[status.ravel() == 1]
        good2 = pts2[status.ravel() == 1]

        self.prev_gray = gray

        if len(good1) < 4:
            return np.eye(2, 3, dtype=np.float32)

        # Robust partial-affine estimation (handles pan + zoom + rotation)
        matrix, _ = cv2.estimateAffinePartial2D(
            good1, good2, method=cv2.RANSAC, ransacReprojThreshold=3.0
        )

        if matrix is None:
            return np.eye(2, 3, dtype=np.float32)

        return matrix.astype(np.float32)