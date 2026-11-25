"""Joint refinement: carve with all registered body views (voting), re-register each extra view against the
leave-one-out hull, repeat. Then carve the final hull at 4 mm."""
import numpy as np, cv2, json, sys
from scipy import ndimage as ndi
H = W = 2048
cams = json.load(open('cams33.json'))
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import camera
project = camera.project
body = [n for n in cams if cams[n]['kind'] in camera.BODY_VIEWS]
MS = {n: cv2.imread(f'mask_{n}.png', 0) > 0 for n in body}


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

# Compare free fits to the locked body-centre camera or to their diagnostic ring fits.
RINGS = ('main', 'el30', 'low20', 'top')
LOCK = camera.ring_lock_enabled()
rings, consistency = {}, {}
body_rig = camera.body_center_rig(cams, W, H)
for kind in RINGS:
    views = camera.ring_views(cams, kind)
    if views and LOCK:
        rings[kind] = body_rig
    elif len(views) >= 3:
        rings[kind] = camera.ring_fit(cams, kind)
    if kind in rings:
        consistency[kind] = camera.ring_report(cams, kind, rings[kind], 'free fit vs ring model')
json.dump(dict(locked=LOCK, rings=rings, free_fit_deviation=consistency), open('ring_consistency.json', 'w'), indent=1)
print('ring lock', 'ON: one body centre and scale for all full-body views' if LOCK else 'off: free per-view fit', flush=True)
if LOCK:
    for n in body:
        if cams[n]['kind'] == 'top':
            phi, th = camera.nominal(n, 'top')
            cams[n] = dict(cams[n], phi=phi, th=th)
        cams[n] = camera.ring_apply(cams[n], body_rig)


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
        for n in body:
            if anchored(n) or cams[n]['kind'] == 'top':
                continue
            points = loo_surface(n, allv)
            c = cams[n]
            score = iou(points, c, MSS[n])
            step = 2 if it == 0 else 1
            while True:
                best = c
                for offset in (-step, step):
                    candidate = camera.ring_apply(dict(c, phi=c['phi'] + offset), body_rig)
                    if camera.within_limits(n, candidate):
                        candidate_score = iou(points, candidate, MSS[n])
                        if candidate_score > score + 1e-4:
                            best, score = candidate, candidate_score
                if best is c:
                    break
                c = best
            cams[n] = c
            print('iter %d %-14s IoU %.3f  phi %6.1f th %5.1f s %7.1f' %
                  (it, n, score, c['phi'], c['th'], c['s']), flush=True)
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
