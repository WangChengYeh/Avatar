"""Joint refinement: carve with all registered body views (voting), re-register each extra view against the
leave-one-out hull, repeat. Then carve the final hull at 4 mm."""
import numpy as np, cv2, json, sys
from scipy import ndimage as ndi
H = W = 2048
cams = json.load(open('cams33.json'))
body = [n for n in cams if cams[n]['kind'] in ('main', 'el30', 'low20', 'top')]
MS = {n: cv2.imread(f'mask_{n}.png', 0) > 0 for n in body}


import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import camera
project = camera.project


def grid(vs):
    xs = np.arange(-0.90, 0.90, vs) + vs / 2; ys = np.arange(0.0, 1.72, vs) + vs / 2; zs = np.arange(-0.38, 0.38, vs) + vs / 2
    X, Y, Z = np.meshgrid(xs, ys, zs, indexing='ij')
    return np.stack([X.ravel(), Y.ravel(), Z.ravel()], 1), X.shape, (xs, ys, zs)


def votes_for(P, names, dil=3):
    vt = np.zeros(len(P), np.uint8)
    for n in names:
        m = cv2.dilate(MS[n].astype(np.uint8), np.ones((2 * dil + 1,) * 2, np.uint8))
        c_, r_ = project(P, cams[n])
        ci, ri = np.round(c_).astype(int), np.round(r_).astype(int)
        ok = (ci >= 0) & (ci < W) & (ri >= 0) & (ri < H)
        vt += ok & (m[np.clip(ri, 0, H - 1), np.clip(ci, 0, W - 1)] > 0)
    return vt


def iou(Psurf, c, ms, ds=4):
    cc, rr = project(Psurf, c)
    img = np.zeros(ms.shape, np.uint8)
    ci, ri = (cc / ds).astype(int), (rr / ds).astype(int)
    ok = (ci >= 0) & (ci < img.shape[1]) & (ri >= 0) & (ri < img.shape[0])
    img[ri[ok], ci[ok]] = 1
    img = ndi.binary_fill_holes(cv2.morphologyEx(img, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8)))
    return (img & ms).sum() / max(1, (img | ms).sum())


P6, shp, g6 = grid(0.008)
DS = 4
MSS = {n: cv2.resize(MS[n].astype(np.uint8), (W // DS, H // DS), interpolation=cv2.INTER_AREA) > 0 for n in body}

# fixed distance and centre within a ring: report how far the free per-view fit (cams33) is from one shared
# scale / aim point per ring, and (photos passed the check) put every view on that ring
RINGS = ('main', 'el30', 'low20')
LOCK = camera.ring_lock_enabled()
rings, consistency = {}, {}
S_BODY = camera.body_scale(cams)     # fixed distance: every full-body ring has the level ring's scale
for kind in RINGS:
    if len(camera.ring_views(cams, kind)) >= 3:
        rings[kind] = camera.ring_fit(cams, kind, s=S_BODY if LOCK else None)
        consistency[kind] = camera.ring_report(cams, kind, rings[kind], 'free fit vs ring model')
json.dump(dict(locked=LOCK, rings=rings, free_fit_deviation=consistency), open('ring_consistency.json', 'w'), indent=1)
print('ring lock', 'ON: shared scale / aim point per ring, only the angle per view' if LOCK else 'off: free per-view fit', flush=True)
if LOCK:
    for kind, ring in rings.items():
        for n in camera.ring_views(cams, kind):
            cams[n] = camera.ring_apply(cams[n], ring)


def loo_surface(n, allv):
    mine = votes_for(P6, [n])
    loo = (allv - mine) >= (len(body) - 1) - 3          # leave-one-out hull, tolerate 3 disagreeing views
    occ = loo.reshape(shp)
    surf = occ & ~ndi.binary_erosion(occ)
    i, j, k = np.nonzero(surf)
    return np.stack([g6[0][i], g6[1][j], g6[2][k]], 1)


def anchored(n):
    return cams[n]['kind'] == 'main' and n.startswith('01')     # the front view anchors the frame


for it in range(3):
    allv = votes_for(P6, body)
    if LOCK:
        Ps = {n: loo_surface(n, allv) for n in body if not anchored(n)}
        # 1. per view: only the angle; scale and aim point come from the ring
        for n in Ps:
            c = dict(cams[n]); sc = iou(Ps[n], c, MSS[n])
            ring = rings.get(c['kind'])
            # views outside a ring (top): offsets only, the scale is the full-body scale
            keys = [('phi', 2 if it == 0 else 1)] + ([] if ring else [('th', 2 if it == 0 else 1), ('cu', 6 if it == 0 else 3),
                                                                       ('cv', 6 if it == 0 else 3)])
            if not ring:
                c['s'] = S_BODY
            improved = True
            while improved:
                improved = False
                for key, dv in keys:
                    for sg in (1, -1):
                        c2 = dict(c); c2[key] += sg * dv
                        if key == 'th': c2['th'] = min(90.0, c2['th'])
                        if ring: c2 = camera.ring_apply(c2, ring)
                        if not camera.within_limits(n, c2): continue
                        s2 = iou(Ps[n], c2, MSS[n])
                        if s2 > sc + 1e-4:
                            sc, c, improved = s2, c2, True
            cams[n] = c
        # 2. per tilted ring: the shared aim point (and camera distance) against all of its views at once.
        # The main ring defines the frame (scale from the height), so it is not moved here.
        for kind in ('el30', 'low20'):
            if kind not in rings:
                continue
            ring = rings[kind]; names = [n for n in camera.ring_views(cams, kind) if n in Ps]

            def total(rg):
                return sum(iou(Ps[n], camera.ring_apply(cams[n], rg), MSS[n]) for n in names) / len(names)
            sc = total(ring)
            # the scale is the full-body scale (spec), never fitted: IoU against the voting hull (a little fatter than
            # the figure) pulls a shared scale low (measured on perfect photos: 961 -> 947 px/m, true 975)
            steps = [('U', 6 if it == 0 else 3), ('V', 6 if it == 0 else 3),
                     ('qx', 0.01 if it == 0 else 0.005), ('qz', 0.01 if it == 0 else 0.005)]
            if ring.get('D'):
                steps.append(('D', 0.5 if it == 0 else 0.25))
            improved = True
            while improved:
                improved = False
                for key, dv in steps:
                    for sg in (1, -1):
                        r2 = dict(ring); r2[key] += sg * dv
                        if key == 'D' and r2['D'] < 2.0: continue
                        s2 = total(r2)
                        if s2 > sc + 1e-5:
                            sc, ring, improved = s2, r2, True
            rings[kind] = ring
            for n in camera.ring_views(cams, kind):
                cams[n] = camera.ring_apply(cams[n], ring)
            print('iter %d %-6s ring IoU %.3f  s %7.1f  aim (%+.3f, %+.3f) m at (%.0f, %.0f)  D %s' %
                  (it, kind, sc, ring['s'], ring['qx'], ring['qz'], ring['U'], ring['V'], ring.get('D')), flush=True)
        for n in Ps:
            c = cams[n]
            print('iter %d %-14s IoU %.3f  phi %6.1f th %5.1f s %7.1f D %s' % (it, n, iou(Ps[n], c, MSS[n]), c['phi'], c['th'], c['s'], c.get('D')), flush=True)
        continue
    for n in body:
        if anchored(n):
            continue
        Ps = loo_surface(n, allv)
        c = dict(cams[n]); sc = iou(Ps, c, MSS[n])
        steps = [('phi', 2), ('th', 2), ('cu', 6), ('cv', 6), ('s', c['s'] * 0.015)] if it == 0 else \
                [('phi', 1), ('th', 1), ('cu', 3), ('cv', 3), ('s', c['s'] * 0.007)]
        if cams[n]['kind'] == 'main':                  # level ring: keep it level and the scale from the height
            steps = [st for st in steps if st[0] in ('phi', 'cu')]
        if c.get('D'):                                 # perspective view: also refine the camera distance
            steps = steps + [('D', 0.5 if it == 0 else 0.25)]
        improved = True
        while improved:
            improved = False
            for key, dv in steps:
                for sg in (1, -1):
                    c2 = dict(c); c2[key] += sg * dv
                    if key == 'th': c2['th'] = min(90.0, c2['th'])
                    if key == 'D' and c2['D'] < 2.0: continue
                    if not camera.within_limits(n, c2): continue
                    s2 = iou(Ps, c2, MSS[n])
                    if s2 > sc + 1e-4:
                        sc, c, improved = s2, c2, True
        cams[n] = c
        print('iter %d %-14s IoU %.3f  phi %6.1f th %5.1f s %7.1f D %s' % (it, n, sc, c['phi'], c['th'], c['s'], c.get('D')), flush=True)
if LOCK:
    json.dump(dict(locked=True, rings=rings, free_fit_deviation=consistency), open('ring_consistency.json', 'w'), indent=1)
json.dump(cams, open('cams33.json', 'w'), indent=1)

# final hull at 4 mm, tolerate up to 3 disagreeing views out of 25
P4, shp4, g4 = grid(0.004)
vt = np.zeros(len(P4), np.uint8)
for a in range(0, len(P4), 8_000_000):
    vt[a:a + 8_000_000] = votes_for(P4[a:a + 8_000_000], body)
for K in (len(body), len(body) - 2, len(body) - 3):
    print('K=%d voxels %d' % (K, (vt >= K).sum()))
occ = (vt >= len(body) - 3).reshape(shp4)
np.save('occ33.npy', occ)
json.dump(dict(vs=0.004, x0=float(g4[0][0]), y0=float(g4[1][0]), z0=float(g4[2][0])), open('grid33.json', 'w'))
