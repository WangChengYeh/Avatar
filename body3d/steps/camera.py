"""Shared camera model for every pipeline step.

A camera dict has phi (deg, camera toward her left = +), th (deg, camera above = +), s (px per metre at the body
centre), cu, cv (pixel of the body-centre reference) and optionally D (metres from the body centre C0 to the
camera). Without D the camera is orthographic:
    col = cu + s * (P·r),   row = cv - s * (P·u)
With D it is a pinhole camera at C0 + D·f looking at C0 (same scale s at the centre plane):
    k = D / (D - (P - C0)·f),   col = cu + s * (C0·r + k (P - C0)·r),   row = cv - s * (C0·u + k (P - C0)·u)
AI images are usually drawn with some perspective (the camera is "close"), most of all the elevated views; the
D of those views is estimated in cams33.py / refine33.py.
"""
import numpy as np

C0 = np.array([0.0, 0.85, 0.0])


def axes(phi, th):
    """image right r, image up u, toward-camera f (unit vectors)"""
    p, t = np.radians(phi), np.radians(th)
    r = np.array([np.cos(p), 0.0, -np.sin(p)])
    u = np.array([-np.sin(t) * np.sin(p), np.cos(t), -np.sin(t) * np.cos(p)])
    f = np.array([np.sin(p) * np.cos(t), np.sin(t), np.cos(p) * np.cos(t)])
    return r, u, f


def project(P, c):
    """(col, row) arrays for points P (N, 3)"""
    r, u, f = axes(c['phi'], c['th'])
    D = c.get('D')
    if not D:
        return c['cu'] + c['s'] * (P @ r), c['cv'] - c['s'] * (P @ u)
    Q = P - C0
    k = D / np.maximum(0.05 * D, D - Q @ f)
    return c['cu'] + c['s'] * (C0 @ r + k * (Q @ r)), c['cv'] - c['s'] * (C0 @ u + k * (Q @ u))


def toward(P, c):
    """unit vectors from the points toward the camera (N, 3)"""
    _, _, f = axes(c['phi'], c['th'])
    D = c.get('D')
    if not D:
        return np.broadcast_to(f, P.shape)
    v = C0 + D * f - P
    return v / np.linalg.norm(v, axis=1, keepdims=True)


def depth(P, c):
    """larger = closer to the camera (for z-buffers)"""
    _, _, f = axes(c['phi'], c['th'])
    D = c.get('D')
    if not D:
        return P @ f
    return -np.linalg.norm(C0 + D * f - P, axis=1)


# nominal angles of the rings and how far registration may move them: a silhouette alone cannot separate tilt,
# camera distance and scale, so without limits the fit trades one for the other and the texture lands wrong
FIXED_ELEVATION_RINGS = frozenset({'el30', 'low20'})


NOMINAL_TH = {'main': 0.0, 'el30': 30.0, 'low20': -20.0, 'top': 90.0, 'head': 0.0}
import json as _json, os as _os


def _limits():
    """How far registration may move phi / th from the nominal angles.
    Photos that passed the strict photo check (run_all writes check_status.json in the work dir): the checker has
    verified the angles (sections 4 / 8 within ±6°, perspective 10b, ring ratios 10c), so the nominal angles are
    trusted: ±3°. Otherwise (including incomplete face checks): ±10° azimuth / ±16° tilt. Silhouettes alone cannot
    pin the tilt: on perfect photos free fitting turns 30° into 16–27°.
    The elevation of the +30° and −20° rings follows the input spec exactly.
    Environment variables BODY3D_MAX_DPHI / BODY3D_MAX_DTH override the limits on free angles."""
    passed = False
    if _os.path.exists('check_status.json'):
        try:
            passed = bool(_json.load(open('check_status.json')).get('passed'))
        except ValueError:
            passed = False
    dp, dt = (3.0, 3.0) if passed else (10.0, 16.0)
    return float(_os.environ.get('BODY3D_MAX_DPHI', dp)), float(_os.environ.get('BODY3D_MAX_DTH', dt)), passed


MAX_DPHI, MAX_DTH, CHECK_PASSED = _limits()


def nominal(name, kind):
    import re
    m = re.search(r'(\d{3})deg', name)
    return (float(m.group(1)) if m else 0.0), NOMINAL_TH.get(kind, 0.0)


def within_limits(name, c):
    """True when phi / th stay within MAX_DPHI / MAX_DTH of the file-name angle and the ring's nominal tilt"""
    kind = c.get('kind', 'main')
    ph0, th0 = nominal(name, kind)
    dphi = (c['phi'] - ph0 + 180) % 360 - 180
    tilt_limit = 0.0 if kind in FIXED_ELEVATION_RINGS else MAX_DTH
    return abs(dphi) <= MAX_DPHI and abs(c['th'] - th0) <= tilt_limit and c['th'] <= 90.0
