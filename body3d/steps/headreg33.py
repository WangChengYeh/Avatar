"""Register the 8 head close-ups (orthographic, level camera) against the head of the mesh:
scale / offsets from the head top and head width, then refine by IoU on the head (above the chin)."""
import numpy as np, cv2, json, trimesh, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import camera       # angle limits shared with the other cameras (±10° around the file-name angle)
from scipy import ndimage as ndi
cams = json.load(open('cams33.json'))
v = trimesh.load('body33s.ply').vertices
head = v[v[:, 1] > 1.36]                       # head + upper neck
H = W = 2048


def proj(P, c):
    p, t = np.radians(c['phi']), np.radians(c['th'])
    r = np.array([np.cos(p), 0, -np.sin(p)]); u = np.array([-np.sin(t) * np.sin(p), np.cos(t), -np.sin(t) * np.cos(p)])
    return c['cu'] + c['s'] * (P @ r), c['cv'] - c['s'] * (P @ u)


def iou(c, m, ytop_cut):
    cc, rr = proj(head, c)
    img = np.zeros((H // 4, W // 4), np.uint8)
    ci, ri = (cc / 4).astype(int), (rr / 4).astype(int)
    ok = (ci >= 0) & (ci < W // 4) & (ri >= 0) & (ri < H // 4)
    img[ri[ok], ci[ok]] = 1
    img = ndi.binary_fill_holes(cv2.morphologyEx(img, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8)))
    ms = cv2.resize(m.astype(np.uint8), (W // 4, H // 4), interpolation=cv2.INTER_AREA) > 0
    lim = int(ytop_cut / 4)
    img[lim:] = False; ms = ms.copy(); ms[lim:] = False
    return (img & ms).sum() / max(1, (img | ms).sum())


for a in range(0, 360, 45):
    n = f'head_{a:03d}deg'
    m = cv2.imread(f'mask_{n}.png', 0) > 0
    ys, xs = np.nonzero(m)
    c = dict(phi=float(a), th=0.0, s=1.0, cu=0.0, cv=0.0, kind='head')
    # head top in mesh / image; chin height in mesh ~ y where the head is narrowest above the shoulders
    cc, rr = proj(head, c)
    ytop_m = rr.min()                                  # = -max(y)
    # use the head height from the top to y=1.42 (chin / jaw) to set the scale
    hm = head[head[:, 1] > 1.42]
    cch, rrh = proj(hm, c)
    # image: head top row and width of the head at 25% of its height
    top_i = ys.min()
    # mesh head width at 1.52 m and image width at the same fractional height of the head top..1.42
    best = None
    for s in np.linspace(3000, 9000, 61):
        c2 = dict(c, s=s)
        cc, rr = proj(head, c2)
        c2['cv'] = top_i - rr.min()                    # align head tops
        hc = proj(hm, c2)[0]
        c2['cu'] = (np.nonzero(m[int(top_i + 0.1 * s * 0.23)])[0].mean() if m[int(top_i + 0.1 * s * 0.23)].any() else W / 2) \
            - (hc.min() + hc.max()) / 2
        chin_row = c2['cv'] - s * 1.42
        sc = iou(c2, m, min(H - 1, chin_row))
        if best is None or sc > best[0]:
            best = (sc, c2)
    sc, c = best
    chin_row = c['cv'] - c['s'] * 1.42
    for step in (16, 6, 2):
        improved = True
        while improved:
            improved = False
            for key, dv in (('cu', step), ('cv', step), ('s', c['s'] * 0.004 * step), ('phi', step / 4)):
                for sg in (1, -1):
                    c2 = dict(c); c2[key] += sg * dv
                    if not camera.within_limits(n, c2):
                        continue                       # a silhouette of hair alone cannot fix the angle
                    s2 = iou(c2, m, min(H - 1, c2['cv'] - c2['s'] * 1.42))
                    if s2 > sc + 1e-4:
                        sc, c, improved = s2, c2, True
    cams[n] = c
    print('%s IoU %.3f phi %.1f s %.0f cu %.0f cv %.0f' % (n, sc, c['phi'], c['s'], c['cu'], c['cv']), flush=True)

# fixed distance and centre within the close-up ring: one scale and one aim point for all 8 close-ups. The free fit
# above is kept as a measurement (a close-up drawn bigger / shifted shows up as a deviation); with the ring lock
# on, every close-up is put on the shared ring and only its angle stays free.
names = camera.ring_views(cams, 'head')
masks = {n: cv2.imread(f'mask_{n}.png', 0) > 0 for n in names}
LOCK = camera.ring_lock_enabled()
# fixed distance: the close-ups are HEAD_ZOOM times the full-body scale (spec, checked in section 10d)
ring = camera.ring_fit(cams, 'head', qy=1.52, s=camera.body_scale(cams) * camera.HEAD_ZOOM if LOCK else None)
dev = camera.ring_report(cams, 'head', ring, 'free fit vs ring model')
if LOCK and len(names) >= 3:
    def score(c, n):
        return iou(c, masks[n], min(H - 1, c['cv'] - c['s'] * 1.42))

    def total(rg):
        return sum(score(camera.ring_apply(cams[n], rg), n) for n in names) / len(names)
    for n in names:
        cams[n] = camera.ring_apply(cams[n], ring)
    for step in (16, 6, 2):
        for _ in range(2):
            # shared aim point against all close-ups
            sc = total(ring)
            improved = True
            while improved:
                improved = False
                for key, dv in (('U', step), ('V', step), ('qx', 0.0005 * step), ('qz', 0.0005 * step)):   # scale: HEAD_ZOOM x full-body scale (spec)
                    for sg in (1, -1):
                        r2 = dict(ring); r2[key] += sg * dv
                        s2 = total(r2)
                        if s2 > sc + 1e-5:
                            sc, ring, improved = s2, r2, True
            # per close-up: the angle only
            for n in names:
                c = camera.ring_apply(cams[n], ring); sc = score(c, n)
                for sg in (1, -1):
                    while True:
                        c2 = camera.ring_apply(dict(c, phi=c['phi'] + sg * step / 4), ring)
                        if not camera.within_limits(n, c2) or score(c2, n) <= sc + 1e-4:
                            break
                        c, sc = c2, score(c2, n)
                cams[n] = c
    for n in names:
        c = cams[n]
        print('ring %s IoU %.3f phi %.1f s %.0f cu %.0f cv %.0f' % (n, score(c, n), c['phi'], c['s'], c['cu'], c['cv']), flush=True)
    print('head ring: scale %.0f px/m, aim (%+.3f, %.2f, %+.3f) m at (%.0f, %.0f)' %
          (ring['s'], ring['qx'], ring['qy'], ring['qz'], ring['U'], ring['V']), flush=True)
rc = json.load(open('ring_consistency.json')) if os.path.exists('ring_consistency.json') else dict(rings={}, free_fit_deviation={})
rc['rings']['head'] = ring; rc['free_fit_deviation']['head'] = dev; rc['head_locked'] = LOCK
json.dump(rc, open('ring_consistency.json', 'w'), indent=1)
json.dump(cams, open('cams33.json', 'w'), indent=1)
