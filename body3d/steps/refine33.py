"""Joint refinement: carve with all registered body views (voting), re-register each extra view against the
leave-one-out hull, repeat. Then carve the final hull at 4 mm."""
import numpy as np, cv2, json, sys
from scipy import ndimage as ndi
H = W = 2048
cams = json.load(open('cams33.json'))
body = [n for n in cams if cams[n]['kind'] in ('main', 'el30', 'low20', 'top')]
MS = {n: cv2.imread(f'mask_{n}.png', 0) > 0 for n in body}


def axes(phi, th):
    p, t = np.radians(phi), np.radians(th)
    return np.array([np.cos(p), 0, -np.sin(p)]), np.array([-np.sin(t) * np.sin(p), np.cos(t), -np.sin(t) * np.cos(p)])


def project(P, c):
    r, u = axes(c['phi'], c['th'])
    return c['cu'] + c['s'] * (P @ r), c['cv'] - c['s'] * (P @ u)


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
for it in range(3):
    allv = votes_for(P6, body)
    for n in body:
        if cams[n]['kind'] == 'main' and abs(cams[n]['phi']) < 1e-6 and it == 0 and n.startswith('01'):
            continue                                   # the front view anchors the frame
        if cams[n]['kind'] == 'main' and n.startswith('01'):
            continue
        mine = votes_for(P6, [n])
        loo = (allv - mine) >= (len(body) - 1) - 3          # leave-one-out hull, tolerate 3 disagreeing views
        occ = loo.reshape(shp)
        surf = occ & ~ndi.binary_erosion(occ)
        i, j, k = np.nonzero(surf)
        Ps = np.stack([g6[0][i], g6[1][j], g6[2][k]], 1)
        c = dict(cams[n]); sc = iou(Ps, c, MSS[n])
        steps = [('phi', 2), ('th', 2), ('cu', 6), ('cv', 6), ('s', c['s'] * 0.015)] if it == 0 else \
                [('phi', 1), ('th', 1), ('cu', 3), ('cv', 3), ('s', c['s'] * 0.007)]
        if cams[n]['kind'] == 'main':                  # level ring: keep it level and the scale from the height
            steps = [st for st in steps if st[0] in ('phi', 'cu')]
        improved = True
        while improved:
            improved = False
            for key, dv in steps:
                for sg in (1, -1):
                    c2 = dict(c); c2[key] += sg * dv
                    if key == 'th': c2['th'] = min(90.0, c2['th'])
                    s2 = iou(Ps, c2, MSS[n])
                    if s2 > sc + 1e-4:
                        sc, c, improved = s2, c2, True
        cams[n] = c
        print('iter %d %-14s IoU %.3f  phi %6.1f th %5.1f s %7.1f' % (it, n, sc, c['phi'], c['th'], c['s']), flush=True)
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
