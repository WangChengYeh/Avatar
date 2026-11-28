"""Fit a body's outline to the full-body photos: where every vertex on the model's rim should move.

In each view a vertex on the model's own outline is compared with the photo's outline and asked to move, in the image
plane, by the distance between the two. Two rules came from measuring the result against the photos (Gemini
avatar_001: the fitted body was 11 mm wider than the level photos on average, 16-20 mm at the waist):

- The level ring has LEVEL_SAY times the say of an elevated or low view (the same rule the bake uses). AI photos of
  the tilted rings drew the torso about 1 cm wider per side than the level ring; an even average over 24 views left
  the body fatter than every level photo, and the level photos are what the result is compared with.
- A vertex is measured against the model's own outline, not taken to be on it. Vertices near the rim lie a few mm
  inside the model's outline; asking them to reach the photo's outline pushed the whole body out (2-3 mm per side
  on perfect photos).
"""
import cv2
import numpy as np

import camera

LEVEL_SAY = 6.0      # the level ring against one elevated / low view
RIM = 0.25           # |normal . view direction| below this: the vertex is near the rim in this view
NEAR = 20            # px: further than this from the photo's outline, it is another outline's (an occluded rim)
OWN = 6              # px: only vertices this close to the model's own outline vote


def signed(mask):
    """distance to the outline of a mask, px: + outside, - inside"""
    m = (np.asarray(mask) > 0).astype(np.uint8)
    return (cv2.distanceTransform(1 - m, cv2.DIST_L2, 5) - cv2.distanceTransform(m, cv2.DIST_L2, 5)).astype(np.float32)


def _at(field, col, row):
    return cv2.remap(field, col.astype(np.float32).reshape(1, -1), row.astype(np.float32).reshape(1, -1),
                     cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE).ravel()


def moves(X, normals, tris, cams, photo_sdf, free=None, level_say=LEVEL_SAY):
    """(T, has): for every vertex the move (metres, 3D) that brings the model's outline onto the photos', averaged
    over the views in which it is on the rim, and which vertices got a vote.
    X, normals: (n, 3); tris: (m, 3) triangles of the same surface; cams: {name: camera}; photo_sdf: {name: signed()}"""
    free = np.ones(len(X), bool) if free is None else free
    acc = np.zeros_like(X, dtype=float); say = np.zeros(len(X))
    for n, c in cams.items():
        _, _, f = camera.axes(c['phi'], c['th'])
        nf = normals @ f
        rim = np.flatnonzero(free & (np.abs(nf) < RIM))
        col, row = camera.project(X, c)
        own = np.zeros(photo_sdf[n].shape, np.uint8)
        cv2.fillPoly(own, list(np.round(np.stack([col, row], 1)[tris]).astype(np.int32)), 1)
        mine = _at(signed(own), col[rim], row[rim])            # where the vertex sits against the model's outline
        theirs = _at(photo_sdf[n], col[rim], row[rim])         # and against the photo's
        ok = (np.abs(theirs) < NEAR) & (mine > -OWN)
        out = normals[rim] - nf[rim, None] * f                 # outward, in the image plane
        out /= np.linalg.norm(out, axis=1, keepdims=True) + 1e-9
        w = level_say if c.get('kind') == 'main' else 1.0
        acc[rim[ok]] += w * out[ok] * ((mine - theirs)[ok] / c['s'])[:, None]
        say[rim[ok]] += w
    has = say > 0
    T = np.zeros_like(acc); T[has] = acc[has] / say[has, None]
    return T, has
