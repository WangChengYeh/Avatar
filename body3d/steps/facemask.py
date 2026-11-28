"""Which part of the face the frontal head close-up owns when the head texture is baked (bake33.py).

The frontal close-up alone paints the features (brows, eyes, nose, lips): a second copy from a side close-up, a
few mm off, shows at once. Everywhere else the close-ups are blended. Between the two the frontal close-up's share
falls smoothly to nothing at the face outline, over all the featureless skin there is (about 2 cm of cheek).

Before 2.28.0 the frontal close-up owned everything up to 7 mm inside the outline with a weight of +1000: the
hand-over to the side close-ups took 2-4 mm and showed as a line down each cheek, a mask on the head."""
import cv2
import numpy as np

# MediaPipe face-mesh indices
FEATURE_IDX = sorted({
    46, 53, 52, 65, 55, 70, 63, 105, 66, 107, 276, 283, 282, 295, 285, 300, 293, 334, 296, 336,     # brows
    33, 7, 163, 144, 145, 153, 154, 155, 133, 173, 157, 158, 159, 160, 161, 246,                    # right eye
    263, 249, 390, 373, 374, 380, 381, 382, 362, 398, 384, 385, 386, 387, 388, 466,                 # left eye
    1, 2, 4, 5, 6, 98, 327, 129, 358, 168, 195, 197,                                                # nose
    61, 146, 91, 181, 84, 17, 314, 405, 321, 375, 291, 409, 270, 269, 267, 0, 37, 39, 40, 185})     # lips
PAD = 0.004                         # the features' region is grown by this much (m)


def owner_mask(lmk, shape, pad_px):
    """float32 image the size of the frontal close-up: 1 where it alone paints (the features), 0 on and outside
    the face outline (the landmarks' hull), smooth in between. lmk: (N, 2+) landmark pixels of that close-up"""
    lmk = np.asarray(lmk)[:, :2].astype(np.int32)
    hull = np.zeros(shape, np.uint8); cv2.fillConvexPoly(hull, cv2.convexHull(lmk), 1)
    inside = cv2.distanceTransform(hull, cv2.DIST_L2, 5)
    if len(lmk) > max(FEATURE_IDX):
        feat = np.zeros(shape, np.uint8); cv2.fillConvexPoly(feat, cv2.convexHull(lmk[FEATURE_IDX]), 1)
        pad = max(1, int(round(pad_px)))
        feat = cv2.dilate(feat, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * pad + 1, 2 * pad + 1))) & hull
    else:                           # not the 468-point mesh: the middle of the outline stands in for the features
        feat = (inside > inside.max() / 2).astype(np.uint8)
    to_feat = cv2.distanceTransform(1 - feat, cv2.DIST_L2, 5)
    f = inside / np.maximum(inside + to_feat, 1e-6)
    return (f * f * (3 - 2 * f)).astype(np.float32)


THIN = 0.008                        # m: outline features thinner than this are not the head (wisps, earring threads)
PALE_CHROMA, PALE_L = 12, 150       # Lab: light and colourless
PALE_REACH = 0.007                  # m from the background: where a pale patch counts as hanging off the outline


HANG = 0.012                        # what hangs off the head by a neck thinner than this is not the head (m)
HANG_BACK = 0.002                   # the opening rounds tips off (nose, chin, lips): this much is given back (m)


def trunk(mask, scale):
    """the head's outline without what hangs off it by a thin neck: drop earrings, loose strands of hair, eyelashes.
    As part of the outline they are carved into the head: the frontal close-up of Gemini avatar_001 v015 was 157 mm
    wide at the jaw with its earrings and 131 mm without, and the finished jaw was as wide as the cheekbones.
    Ears, nose and chin stay: they join the head along their long side. mask: uint8 0 / 1; scale: px per m"""
    m = (mask > 0).astype(np.uint8)
    k = 2 * int(round(HANG / 2 * scale)) + 1
    b = 2 * int(round(HANG_BACK * scale)) + 1
    core = cv2.morphologyEx(m, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
    return m & cv2.dilate(core, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (b, b)))


def solid(mask, image, scale):
    """the head of a close-up without what hangs off its outline: pale, colourless patches next to the background
    (earrings, the matte's white fringe) and anything thinner than THIN. Baked, the frontal close-up's earrings landed
    on the jaw as white patches (Gemini avatar_001 v018). Teeth and the whites of the eyes are not next to the
    background and stay. mask: uint8 0 / 1; scale: px per m"""
    m = (mask > 0).astype(np.uint8)
    lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB).astype(np.float32)
    pale = ((np.hypot(lab[..., 1] - 128, lab[..., 2] - 128) < PALE_CHROMA) & (lab[..., 0] > PALE_L) & (m > 0)).astype(np.uint8)
    r = 2 * int(round(PALE_REACH * scale)) + 1
    near = cv2.dilate(1 - m, np.ones((r, r), np.uint8))
    n, lbl, stats, _ = cv2.connectedComponentsWithStats(cv2.morphologyEx(pale, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8)))
    hang = np.zeros_like(m)
    for i in range(1, n):
        comp = lbl == i
        if stats[i, cv2.CC_STAT_AREA] > 60 and near[comp].mean() > 0.5:
            hang[comp] = 1
    m = m & (1 - cv2.dilate(hang, np.ones((7, 7), np.uint8)))
    k = 2 * int(round(THIN / 2 * scale)) + 1
    return cv2.morphologyEx(m, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
