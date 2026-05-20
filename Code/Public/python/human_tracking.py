"""
human_tracking.py
=================
Multi-stage human tracker combining YOLOv8, Kalman filtering, and deep ReID.

Key improvements in this version
---------------------------------
1. Spatial plausibility check (Stage 3):
   When a lost track tries to match a detection via ReID, we also check that
   the detection is within a reasonable distance of the track's last known
   position.  Without this, a feature that accidentally scores well can
   "teleport" a track across the entire frame, creating ghost identities.

2. min_crop_px parameter:
   Very small detections produce noisy ReID features.  This lets the tracker
   skip feature extraction for tiny crops, which both speeds up processing
   and avoids polluting the feature bank with garbage.

3. feat_conf and dup_iou are tunable constructor params (from previous fix).
"""

import cv2
import numpy as np
from scipy.optimize import linear_sum_assignment
from ultralytics import YOLO

from track import Track
from kalman_tracker import KalmanBoxTracker
from reid import DeepReID
from cmc import CameraMotionCompensation


# ── IoU helpers ──────────────────────────────────────────────────────────────

def _iou(a: np.ndarray | None, b: np.ndarray | None) -> float:
    if a is None or b is None:
        return 0.0
    x1 = max(a[0], b[0]);  y1 = max(a[1], b[1])
    x2 = min(a[2], b[2]);  y2 = min(a[3], b[3])
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    if inter <= 0:
        return 0.0
    area_a = (a[2] - a[0]) * (a[3] - a[1])
    area_b = (b[2] - b[0]) * (b[3] - b[1])
    return inter / (area_a + area_b - inter + 1e-6)


def _iou_matrix(tracks: list, dets: list) -> np.ndarray:
    if not tracks or not dets:
        return np.empty((len(tracks), len(dets)))
    M = np.zeros((len(tracks), len(dets)), dtype=float)
    for i, t in enumerate(tracks):
        for j, (det, _) in enumerate(dets):
            M[i, j] = 1.0 - _iou(t.get_box(), det)
    return M


def _box_center(box: np.ndarray) -> tuple[float, float]:
    return (box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0


def _box_diagonal(box: np.ndarray) -> float:
    w = box[2] - box[0]
    h = box[3] - box[1]
    return float(np.sqrt(w * w + h * h))


# ── Hungarian matching ────────────────────────────────────────────────────────

def _match(cost: np.ndarray, threshold: float):
    if cost.size == 0:
        return [], list(range(cost.shape[0])), list(range(cost.shape[1]))
    rows, cols = linear_sum_assignment(cost)
    matched, matched_r, matched_c = [], set(), set()
    for r, c in zip(rows, cols):
        if cost[r, c] > threshold:
            continue
        matched.append((r, c))
        matched_r.add(r)
        matched_c.add(c)
    unmatched_t = [i for i in range(cost.shape[0]) if i not in matched_r]
    unmatched_d = [j for j in range(cost.shape[1]) if j not in matched_c]
    return matched, unmatched_t, unmatched_d


# ── Main tracker ─────────────────────────────────────────────────────────────

class HumanTracker:

    def __init__(
        self,
        high_conf      = 0.37,
        low_conf       = 0.09,
        feat_conf      = 0.55,
        match_thresh   = 0.82,
        iou_thresh     = 0.55,
        reid_thresh    = 0.49,
        w_iou          = 0.58,
        dup_iou        = 0.62,
        max_age        = 17,
        max_lost       = 881,
        min_crop_px    = 32,     # min width AND height for ReID crop (pixels)
        spatial_factor = 4.0,    # max re-ID displacement = spatial_factor × box_diagonal
                                 # prevents teleporting tracks across the frame
    ):
        self.HIGH_CONF    = high_conf
        self.LOW_CONF     = low_conf
        self.FEAT_CONF    = feat_conf

        self.MATCH_THRESH = match_thresh
        self.IOU_THRESH   = iou_thresh
        self.REID_THRESH  = reid_thresh

        self.W_IOU  = w_iou
        self.W_REID = 1 - w_iou

        self.MAX_AGE      = max_age
        self.MAX_LOST_AGE = max_lost
        self.DUP_IOU      = dup_iou

        self.MIN_CROP_PX    = min_crop_px
        self.SPATIAL_FACTOR = spatial_factor

        self.detector = YOLO("yolov8m.pt")
        self.reid     = DeepReID()
        self.cmc      = CameraMotionCompensation()

        self.tracks      = []
        self.lost        = []
        self.next_id     = 1
        self.last_tracks = []
        self.suppress_draw = False   # set True by NMN bridge to skip ID labels

    def _detect(self, frame: np.ndarray):
        results = self.detector(frame, conf=self.LOW_CONF, classes=[0], verbose=False)[0]
        dets, features = [], []
        if results.boxes is None:
            return dets, features
        boxes = results.boxes.xyxy.cpu().numpy()
        confs = results.boxes.conf.cpu().numpy()
        for box, conf in zip(boxes, confs):
            # Only extract ReID feature if confidence AND crop size are sufficient
            if conf >= self.FEAT_CONF:
                x1, y1, x2, y2 = map(int, box)
                crop_w = x2 - x1
                crop_h = y2 - y1
                feat = (
                    self.reid.extract(frame, box)
                    if crop_w >= self.MIN_CROP_PX and crop_h >= self.MIN_CROP_PX
                    else None
                )
            else:
                feat = None
            dets.append((box, float(conf)))
            features.append(feat)
        return dets, features

    # ── Spatial plausibility ─────────────────────────────────────────────────

    def _spatially_plausible(
        self,
        last_box: np.ndarray | None,
        det_box:  np.ndarray,
    ) -> bool:
        """
        Return True if `det_box` is within SPATIAL_FACTOR × diagonal of `last_box`.

        Why this matters
        ----------------
        ReID features are not perfect.  Without this check, a lost track can
        match a detection on the other side of the frame just because their
        cosine distance happens to be low.  The result looks like a person
        "jumping" across the screen and gets recorded as an ID switch.

        The threshold is deliberately loose (4× the bounding-box diagonal ≈
        several body lengths) so it doesn't block genuine fast-movers while
        still preventing full-frame teleportation.
        """
        if last_box is None:
            return True   # no position info — allow the match

        max_dist = self.SPATIAL_FACTOR * _box_diagonal(last_box)
        cx1, cy1 = _box_center(last_box)
        cx2, cy2 = _box_center(det_box)
        dist = np.sqrt((cx2 - cx1) ** 2 + (cy2 - cy1) ** 2)
        return dist <= max_dist

    # ── Main pipeline ─────────────────────────────────────────────────────

    def process(self, frame: np.ndarray) -> np.ndarray:
        self.last_tracks = []

        # 0. Camera motion compensation
        affine      = self.cmc.warp(frame)
        is_identity = np.allclose(affine, np.eye(2, 3))
        for t in self.tracks:
            t.predict()
            if not is_identity:
                t.kf.apply_affine(affine)

        # Age the lost pool (predict() is never called on lost tracks)
        for lt in self.lost:
            lt.tick_lost()

        # 1. Detect
        all_dets, all_feats = self._detect(frame)
        high_idx  = [i for i, (_, c) in enumerate(all_dets) if c >= self.HIGH_CONF]
        low_idx   = [i for i, (_, c) in enumerate(all_dets) if self.LOW_CONF <= c < self.HIGH_CONF]
        high_dets = [all_dets[i]  for i in high_idx]
        high_feat = [all_feats[i] for i in high_idx]
        low_dets  = [all_dets[i]  for i in low_idx]
        low_feat  = [all_feats[i] for i in low_idx]

        used_tracks: set[int] = set()
        used_high:   set[int] = set()

        # 2. Stage-1: active tracks <-> high-conf detections (IoU + ReID)
        if self.tracks and high_dets:
            iou_cost  = _iou_matrix(self.tracks, high_dets)
            reid_cost = np.ones_like(iou_cost)
            for i, t in enumerate(self.tracks):
                for j, feat in enumerate(high_feat):
                    if feat is not None:
                        reid_cost[i, j] = t.best_feature_distance(feat)
            cost = self.W_IOU * iou_cost + self.W_REID * reid_cost
            matched, _, _ = _match(cost, self.MATCH_THRESH)
            for r, c in matched:
                self.tracks[r].update(high_dets[c][0], high_feat[c])
                used_tracks.add(r)
                used_high.add(c)

        # 3. Stage-2: unmatched active tracks <-> low-conf detections (IoU only)
        if low_dets:
            unmatched_t_idx = [i for i in range(len(self.tracks)) if i not in used_tracks]
            sub_tracks = [self.tracks[i] for i in unmatched_t_idx]
            if sub_tracks:
                iou_cost = _iou_matrix(sub_tracks, low_dets)
                matched2, _, _ = _match(iou_cost, self.IOU_THRESH)
                for r, c in matched2:
                    real_idx = unmatched_t_idx[r]
                    self.tracks[real_idx].update(low_dets[c][0], low_feat[c])
                    used_tracks.add(real_idx)

        # 4. Unmatched active tracks -> lost pool
        new_active = []
        for i, t in enumerate(self.tracks):
            if i in used_tracks:
                new_active.append(t)
            else:
                t.mark_lost()
                self.lost.append(t)
        self.tracks = new_active

        # 5. Stage-3: lost tracks <-> unmatched high-conf dets (ReID + spatial check)
        #
        # TWO conditions must BOTH pass before a lost track is recovered:
        #   a) ReID cosine distance < reid_thresh
        #   b) Detection is spatially plausible (not on the opposite side of frame)
        #
        recycled, still_lost = [], []
        used_high_in_stage3: set[int] = set()

        for lt in self.lost:
            if lt.is_lost_expired(self.MAX_LOST_AGE):
                continue

            best_dist, best_j = self.REID_THRESH, -1
            last_box = lt.get_box()

            for j in range(len(high_dets)):
                if j in used_high or j in used_high_in_stage3:
                    continue
                if high_feat[j] is None:
                    continue

                # Spatial plausibility check — reject physically impossible matches
                det_box = high_dets[j][0]
                if not self._spatially_plausible(last_box, det_box):
                    continue

                d = lt.best_feature_distance(high_feat[j])
                if d < best_dist:
                    best_dist, best_j = d, j

            if best_j >= 0:
                lt.update(high_dets[best_j][0], high_feat[best_j])
                recycled.append(lt)
                used_high_in_stage3.add(best_j)
                used_high.add(best_j)
            else:
                still_lost.append(lt)

        self.lost = still_lost
        self.tracks.extend(recycled)

        # 6. Birth: new tracks from unmatched high-conf dets
        for j, (det, _) in enumerate(high_dets):
            if j in used_high:
                continue
            if any(_iou(t.get_box(), det) > self.DUP_IOU for t in self.tracks):
                continue
            kf = KalmanBoxTracker(det, self.next_id)
            tr = Track(kf, self.next_id, high_feat[j])
            self.tracks.append(tr)
            self.next_id += 1

        # 7. Remove dead active tracks
        self.tracks = [t for t in self.tracks if t.is_alive(self.MAX_AGE)]

        # 8. Build output (confirmed tracks only)
        output = []
        for t in self.tracks:
            if not t.is_confirmed():
                continue
            box = t.get_box()
            if box is None:
                continue
            x1, y1, x2, y2 = map(int, box)
            output.append((t.id, [x1, y1, x2, y2]))
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
            # When suppress_draw is True the NMN attendance bridge will
            # overdraw the label with the recognised person's name instead.
            if not self.suppress_draw:
                cv2.putText(frame, f"ID {t.id}", (x1, y1 - 6),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 0), 2)

        self.last_tracks = output
        return frame

    def get_tracks(self) -> list:
        """Return a shallow copy of the last confirmed track list.
        Each entry is (track_id, [x1, y1, x2, y2]).
        Used by NMN context extractor so downstream modules can read boxes."""
        return list(self.last_tracks)