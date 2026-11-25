"""Shared camera model for every pipeline step.

A camera dict has phi (deg, camera toward her left = +), th (deg, camera above = +), s (px per metre at the body
centre), cu, cv (pixel of the body-centre reference) and optionally D (metres from the body centre C0 to the
camera). Without D the camera is orthographic:
    col = cu + s * (P·r),   row = cv - s * (P·u)
With D it is a pinhole camera at C0 + D·f looking at C0 (same scale s at the centre plane):
    k = D / (D - (P - C0)·f),   col = cu + s * (C0·r + k (P - C0)·r),   row = cv - s * (C0·u + k (P - C0)·u)
The input spec is orthographic (checked by section 10b). Only when the photos fail the check (the run still finishes, results marked _FAIL) do
cams33.py / refine33.py estimate a D for the elevated / low views, so that photos drawn with perspective can still be
reconstructed for diagnosis.
"""
import numpy as np

# The pipeline reconstructs every figure at the spec height: each view's px per metre is its figure height divided by
# SPEC_HEIGHT, so the GLB is always SPEC_HEIGHT tall (rescale it in the engine for another height). The body centre
# (the aim point of every full-body view, and the perspective reference C0) is half of it, on the rotation axis.
SPEC_HEIGHT = 1.65
BODY_CENTER_HEIGHT = SPEC_HEIGHT / 2
C0 = np.array([0.0, BODY_CENTER_HEIGHT, 0.0])
BODY_VIEWS = frozenset({'main', 'el30', 'low20', 'top'})


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
    verified the angles (sections 4 / 8: level ring within 5°, tilted rings within 7°, perspective 10b, ring ratios 10c, distance 10d, aim and tilt 10e), so the nominal angles are
    trusted: azimuth fixed to the file-name angle (±0°), tilt ±3°. Otherwise (photos with a FAIL; the run goes on, results marked _FAIL): ±10° azimuth / ±16° tilt. Silhouettes alone cannot
    pin the tilt: on perfect photos free fitting turns 30° into 16–27°.
    The elevation of the +30° and −20° rings follows the input spec exactly.
    Environment variables BODY3D_MAX_DPHI / BODY3D_MAX_DTH override the limits on free angles."""
    passed = False
    if _os.path.exists('check_status.json'):
        try:
            passed = bool(_json.load(open('check_status.json')).get('passed'))
        except ValueError:
            passed = False
    # passed: the angles are the spec (file name); refinement on perfect photos moved the 45° diagonals to the ±3° edge
    # (body 45° -> 48°, close-up 45° -> 41.9°: hull artefacts, not angle), putting the face 12 mm off (#28)
    dp, dt = (0.0, 3.0) if passed else (10.0, 16.0)
    return float(_os.environ.get('BODY3D_MAX_DPHI', dp)), float(_os.environ.get('BODY3D_MAX_DTH', dt)), passed


MAX_DPHI, MAX_DTH, CHECK_PASSED = _limits()


def nominal(name, kind):
    import re
    m = re.search(r'(\d{3})deg', name)
    return (float(m.group(1)) if m else 0.0), NOMINAL_TH.get(kind, 0.0)


def ring_lock_enabled():
    """Fixed camera distance and centre within each ring (see docs/Loop-Engineering-Theory.md).
    On by default when the photos passed the strict check, like the ±3° angle limit; BODY3D_RING_LOCK=1 / 0
    forces it on / off."""
    v = _os.environ.get('BODY3D_RING_LOCK')
    return CHECK_PASSED if v is None else v != '0'


# ---- fixed distance and centre within a ring.
# The imaginary camera orbits the figure: within one ring only the angle changes. So every view of the ring has
# the same scale s (orthographic: fixed distance = fixed px per metre), the same tilt, and is aimed at the same
# point Q, which therefore lands on the same pixel (U, V) in every view:
#     cu = U - s (Q·r),   cv = V + s (Q·u)        (orthographic; r, u from the view's own phi / th)
# Q·u is the same for every view of a level ring, so Q_y is fixed and only (U, V, Qx, Qz) are fitted.
RING_KEYS = ('s', 'U', 'V', 'qx', 'qz')
# Fixed distance across rings too (input spec, same values in check_turnaround.py section 10d): every full-body view
# (level, +30°, -20°, top) is framed BODY_FRAME metres wide, so they all share the level ring's scale, which the
# figure height fixes exactly; the head close-ups are framed HEAD_FRAME wide: HEAD_ZOOM times that scale.
BODY_FRAME, HEAD_ZOOM = 1.95, 4.0
HEAD_FRAME = BODY_FRAME / HEAD_ZOOM


def body_scale(cams):
    """px per metre of every full-body view: the level ring's (from the figure height)"""
    return float(np.median([c['s'] for c in cams.values() if c.get('kind') == 'main']))


def body_center_rig(cams, width, height):
    """Use the rotation axis at half body height as the centre of every full-body image."""
    return dict(s=body_scale(cams), U=width / 2, V=height / 2,
                qx=0.0, qy=BODY_CENTER_HEIGHT, qz=0.0, D=None)


def ring_views(cams, kind):
    return sorted(n for n, c in cams.items() if c.get('kind') == kind)


def ring_apply(c, ring):
    """camera c (phi, th, D kept) placed on the ring: shared scale and aim point"""
    r, u, _ = axes(c['phi'], c['th'])
    Q = np.array([ring['qx'], ring['qy'], ring['qz']])
    out = dict(c, s=float(ring['s']), cu=float(ring['U'] - ring['s'] * (Q @ r)), cv=float(ring['V'] + ring['s'] * (Q @ u)))
    if ring.get('D'):
        out['D'] = float(ring['D'])
    else:
        out.pop('D', None)
    return out


def ring_fit(cams, kind, qy=None, s=None):
    """shared ring parameters from freely fitted per-view cameras: scale s (given by the spec, else the median of
    the free fits) and the least-squares aim point"""
    names = ring_views(cams, kind)
    s = float(np.median([cams[n]['s'] for n in names]) if s is None else s)
    qy = float(C0[1] if qy is None else qy)
    A, b = [], []
    for n in names:
        c = cams[n]
        r, u, _ = axes(c['phi'], c['th'])
        A.append([1, 0, -s * r[0], -s * r[2]]); b.append(c['cu'])
        A.append([0, 1, s * u[0], s * u[2]]); b.append(c['cv'] - s * u[1] * qy)
    U, V, qx, qz = np.linalg.lstsq(np.array(A, float), np.array(b, float), rcond=None)[0]
    Ds = [cams[n].get('D') for n in names]
    D = float(np.median([d for d in Ds if d])) if sum(1 for d in Ds if d) * 2 > len(Ds) else None
    return dict(s=s, U=float(U), V=float(V), qx=float(qx), qy=qy, qz=float(qz), D=D)


def ring_deviation(cams, kind, ring):
    """how far each freely fitted camera is from the ring model: scale (%) and aim-point offset (mm)"""
    out = {}
    for n in ring_views(cams, kind):
        c, m = cams[n], ring_apply(cams[n], ring)
        Q = np.array([ring['qx'], ring['qy'], ring['qz']])
        col0, row0 = project(Q[None], c); col1, row1 = project(Q[None], m)
        out[n] = dict(scale_pct=100 * (c['s'] / ring['s'] - 1),
                      centre_mm=float(1000 * np.hypot(col0[0] - col1[0], row0[0] - row1[0]) / ring['s']))
    return out


def ring_report(cams, kind, ring, label):
    dev = ring_deviation(cams, kind, ring)
    if not dev:
        return dev
    sc = max(abs(d['scale_pct']) for d in dev.values()); ce = max(d['centre_mm'] for d in dev.values())
    print(f'{label} {kind}: shared scale {ring["s"]:.1f} px/m, aim point ({ring["qx"]:+.3f}, {ring["qy"]:.2f}, '
          f'{ring["qz"]:+.3f}) m at pixel ({ring["U"]:.0f}, {ring["V"]:.0f}); free fit deviates up to '
          f'{sc:.1f}% scale / {ce:.0f} mm centre', flush=True)
    return dev


def within_limits(name, c):
    """True when phi / th stay within MAX_DPHI / MAX_DTH of the file-name angle and the ring's nominal tilt"""
    kind = c.get('kind', 'main')
    ph0, th0 = nominal(name, kind)
    dphi = (c['phi'] - ph0 + 180) % 360 - 180
    tilt_limit = 0.0 if kind in FIXED_ELEVATION_RINGS else MAX_DTH
    return abs(dphi) <= MAX_DPHI and abs(c['th'] - th0) <= tilt_limit and c['th'] <= 90.0
