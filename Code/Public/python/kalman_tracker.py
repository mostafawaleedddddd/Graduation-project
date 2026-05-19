import numpy as np
from filterpy.kalman import KalmanFilter


class KalmanBoxTracker:
    """
    Tracks a bounding box using a Kalman Filter.

    State vector (7D):  [cx, cy, s, r, vcx, vcy, vs]
        cx, cy  = center of box
        s       = area (w * h)
        r       = aspect ratio (w / h)
        vcx,vcy = velocity of center
        vs      = velocity of area

    Measurement (4D):   [cx, cy, s, r]
    """

    def __init__(self, bbox: np.ndarray, track_id: int):
        self.id = track_id

        self.kf = KalmanFilter(dim_x=7, dim_z=4)

        # ── State transition ────────────────────────────────────────────────
        # Constant-velocity model: position += velocity each step
        self.kf.F = np.array([
            [1, 0, 0, 0, 1, 0, 0],
            [0, 1, 0, 0, 0, 1, 0],
            [0, 0, 1, 0, 0, 0, 1],
            [0, 0, 0, 1, 0, 0, 0],
            [0, 0, 0, 0, 1, 0, 0],
            [0, 0, 0, 0, 0, 1, 0],
            [0, 0, 0, 0, 0, 0, 1],
        ], dtype=float)

        # ── Observation matrix ──────────────────────────────────────────────
        # We observe cx, cy, s, r directly
        self.kf.H = np.array([
            [1, 0, 0, 0, 0, 0, 0],
            [0, 1, 0, 0, 0, 0, 0],
            [0, 0, 1, 0, 0, 0, 0],
            [0, 0, 0, 1, 0, 0, 0],
        ], dtype=float)

        # ── Measurement noise R ─────────────────────────────────────────────
        # Area (s) and aspect ratio (r) are noisier than center position
        self.kf.R = np.diag([1.0, 1.0, 10.0, 10.0])

        # ── Process noise Q ─────────────────────────────────────────────────
        # Velocity components are much less certain than position components
        self.kf.Q = np.diag([1.0, 1.0, 1.0, 1.0, 0.01, 0.01, 0.01])

        # ── Initial state covariance P ──────────────────────────────────────
        # High uncertainty on velocity at birth; moderate on position/size
        self.kf.P = np.diag([10.0, 10.0, 10.0, 10.0, 1e4, 1e4, 1e4])

        # Seed state from the first detection
        self.kf.x[:4] = self._xyxy_to_xysr(bbox)

    # ── Helpers ─────────────────────────────────────────────────────────────

    @staticmethod
    def _xyxy_to_xysr(bbox: np.ndarray) -> np.ndarray:
        """Convert [x1,y1,x2,y2] → [[cx],[cy],[s],[r]]."""
        x1, y1, x2, y2 = bbox
        w = x2 - x1
        h = y2 - y1
        cx = x1 + w / 2.0
        cy = y1 + h / 2.0
        s  = w * h
        r  = w / (h + 1e-6)
        return np.array([[cx], [cy], [s], [r]], dtype=float)

    # ── Public API ───────────────────────────────────────────────────────────

    def predict(self) -> None:
        """Advance one time step (no measurement)."""
        # Prevent negative area from propagating
        if (float(self.kf.x[2, 0]) + float(self.kf.x[6, 0])) <= 0:
            self.kf.x[6, 0] = 0.0
        self.kf.predict()

    def update(self, bbox: np.ndarray) -> None:
        """Correct the filter with a new detection."""
        self.kf.update(self._xyxy_to_xysr(bbox))

    def apply_affine(self, M: np.ndarray) -> None:
        """
        Apply a 2×3 affine matrix (from CMC) to the track's predicted position.
        This compensates for camera motion before the association step.
        """
        cx = float(self.kf.x[0, 0])
        cy = float(self.kf.x[1, 0])

        # Transform center point
        new_cx = M[0, 0] * cx + M[0, 1] * cy + M[0, 2]
        new_cy = M[1, 0] * cx + M[1, 1] * cy + M[1, 2]
        self.kf.x[0, 0] = new_cx
        self.kf.x[1, 0] = new_cy

        # Scale the area by |det(M[:2,:2])| to keep the box consistent
        scale = abs(M[0, 0] * M[1, 1] - M[0, 1] * M[1, 0])
        if scale > 0:
            self.kf.x[2, 0] = float(self.kf.x[2, 0]) * scale

    def get_state(self) -> np.ndarray | None:
        """Return [x1,y1,x2,y2], or None if the state is degenerate."""
        cx, cy, s, r = self.kf.x[:4].reshape(-1)
        if s <= 0 or r <= 0:
            return None
        w = np.sqrt(s * r)
        h = s / (w + 1e-6)
        return np.array([cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2])