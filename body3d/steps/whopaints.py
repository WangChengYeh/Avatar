"""Who may paint where on the body, beyond "the most frontal photo wins" (bake33.py).

Both rules came from Gemini avatar_001 rendered beside its photos (2026-11-28): a second, paler strap inside the
racer back, a doubled neckline, finger marks on the hips, a patch of skin around the shoulder in the side view.

1. The tilted rings (30° up, 20° down) and the top view fill in what the level ring cannot see. They used to compete
   with the level photos wherever the surface leans toward them (the top of the chest, under the shoulder blades):
   an AI draws those rings a little differently (the torso 1 cm wider per side, a strap 2 cm off), and the two
   were mixed half and half exactly there. The hand-over is a share of the final colour, set by how well the best
   level photo faces the surface, not a weight (a weight moves the hand-over into the tail: the cheek line, 2.28.0).
   Handing over later (0.3 / 0.5) left streaks on the shoulders: a level photo that slanted stretches every pixel.

2. A photo that looks along the arms (the side views) may not paint the torso around the arm. Seen end-on, a T-pose
   arm is a small disc in front of the shoulder; an AI draws the forearm and hand foreshortened across the chest or
   the hip instead, and everything it covers beyond the model's own arm was painted onto the torso behind.
"""
import cv2
import numpy as np

LEVEL_SEES = (0.50, 0.70)     # the best level photo's facing (cos): below, the tilted views paint; above, the level ring
ARM_X = 0.20                  # m from the body's axis at 1.65 m height: beyond this the surface is the arm
ARM_SHADOW = 0.10             # m: how far around the model's arm an end-on photo's own arm may reach


def smoothstep(lo, hi, v):
    f = np.clip((np.asarray(v, float) - lo) / (hi - lo), 0, 1)
    return f * f * (3 - 2 * f)


def level_share(level_best, on_head=0.0):
    """the share (0-1) of the final colour that the level ring and the close-ups have against the tilted views.
    level_best: the best facing (cos, 0 if hidden) of any level photo; on_head: 1 where the close-ups paint"""
    s = smoothstep(LEVEL_SEES[0], LEVEL_SEES[1], level_best)
    return 1 - (1 - s) * (1 - np.asarray(on_head, float))


def arm_shadow(marks, radius_cells):
    """where a photo's own arm may lie: the cells the model's arm covers in this view (a boolean grid), grown by
    radius_cells"""
    r = max(1, int(round(radius_cells)))
    return cv2.dilate(np.asarray(marks, np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))) > 0
