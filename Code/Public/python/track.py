import numpy as np
from scipy.spatial.distance import cosine


class TrackState:
    TENTATIVE = "tentative"   # newly created, not yet confirmed
    TRACKED   = "tracked"     # actively matched
    LOST      = "lost"        # missed for a few frames


class Track:
    """
    A single target track.

    States
    ------
    TENTATIVE  →  promoted to TRACKED after MIN_HITS consecutive matches
    TRACKED    →  remains while it keeps getting matched
    LOST       →  when missed; removed after MAX_LOST_AGE frames

    Feature Bank
    ------------
    Uses an Exponential Moving Average (EMA) for fast per-frame comparison,
    AND keeps a raw feature bank for robust long-term re-identification.
    The bank stores up to BANK_SIZE features; best_feature_distance() returns
    the minimum cosine distance to any stored feature — much more reliable
    than comparing against the drifted EMA alone.
    """

    MIN_HITS     = 1      # FIX: was 3 — promoted after just 1 hit so new
                          #      people appear immediately (improves recall)
    EMA_ALPHA    = 0.9    # weight given to the existing feature vs. new one
    BANK_SIZE    = 60     # how many raw features to keep per track

    def __init__(self, kf, track_id: int, feat: np.ndarray | None):
        self.kf   = kf
        self.id   = track_id

        # ── Feature representation ───────────────────────────────────────────
        self.feat      = feat                         # EMA feature (fast match)
        self.feat_bank = [feat] if feat is not None else []  # raw bank (robust re-ID)

        # ── Book-keeping ─────────────────────────────────────────────────────
        self.age               = 0
        self.hits              = 1
        self.time_since_update = 0
        self.frames_lost       = 0   # FIX: separate counter incremented by the
                                     #      tracker each frame while in self.lost
        self.confidence        = 1.0

        self.state = TrackState.TENTATIVE

    # ── Kalman lifecycle ─────────────────────────────────────────────────────

    def predict(self) -> None:
        self.kf.predict()
        self.age               += 1
        self.time_since_update += 1
        self.confidence        *= 0.97   # gentle decay while unmatched

    def update(self, box: np.ndarray, feat: np.ndarray | None = None) -> None:
        self.kf.update(box)
        self.time_since_update = 0
        self.frames_lost       = 0
        self.hits             += 1
        self.confidence        = min(1.0, self.confidence + 0.25)

        # Promote tentative track once it has enough consecutive hits
        if self.state == TrackState.TENTATIVE and self.hits >= self.MIN_HITS:
            self.state = TrackState.TRACKED
        elif self.state == TrackState.LOST:
            self.state = TrackState.TRACKED

        if feat is not None:
            self._update_feat(feat)

    def mark_lost(self) -> None:
        self.state = TrackState.LOST

    def tick_lost(self) -> None:
        """
        Call once per frame while this track is in the lost pool.
        FIX: predict() is only called for active tracks, so lost tracks
        need their own aging counter — otherwise time_since_update stays
        frozen and MAX_LOST_AGE never fires.
        """
        self.frames_lost += 1
        self.confidence  *= 0.97   # keep decaying so very stale tracks fade

    # ── Feature management ───────────────────────────────────────────────────

    def _update_feat(self, feat: np.ndarray) -> None:
        """EMA update + append to raw bank."""
        if self.feat is None:
            self.feat = feat
        else:
            self.feat = self.EMA_ALPHA * self.feat + (1 - self.EMA_ALPHA) * feat
            norm = np.linalg.norm(self.feat)
            if norm > 1e-6:
                self.feat /= norm

        self.feat_bank.append(feat)
        if len(self.feat_bank) > self.BANK_SIZE:
            self.feat_bank.pop(0)

    def best_feature_distance(self, feat: np.ndarray | None) -> float:
        """
        Return the MINIMUM cosine distance between `feat` and any feature
        stored in the bank (plus the EMA).

        Why this matters for re-ID
        --------------------------
        The EMA drifts toward the average appearance over time.  A person
        who was seen mostly front-on may have an EMA that looks nothing like
        their side-on re-entry crop.  The bank preserves every pose, so at
        least one stored feature is likely to be a good match.
        """
        if feat is None or not self.feat_bank:
            return 1.0

        # Include EMA as a candidate too
        candidates = self.feat_bank[:]
        if self.feat is not None:
            candidates.append(self.feat)

        best = 1.0
        for stored in candidates:
            if stored is None:
                continue
            d = float(cosine(stored, feat))
            if d < best:
                best = d
        return best

    # ── Status queries ───────────────────────────────────────────────────────

    def is_confirmed(self) -> bool:
        return self.state in (TrackState.TRACKED, TrackState.LOST)

    def is_alive(self, max_age: int, min_conf: float = 0.15) -> bool:
        if self.time_since_update > max_age:
            return False
        if self.confidence < min_conf:
            return False
        return True

    def is_lost_expired(self, max_lost_age: int) -> bool:
        """Use frames_lost (not time_since_update) to age lost tracks."""
        return self.frames_lost > max_lost_age

    def get_box(self) -> np.ndarray | None:
        return self.kf.get_state()