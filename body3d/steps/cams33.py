"""Orthographic camera model for all 33 views.
  view direction from the camera toward the body:  d = -(sinφ cosθ, sinθ, cosφ cosθ)   (θ>0: camera above)
  image right r = (cosφ, 0, -sinφ);  image up u' = (-sinθ sinφ, cosθ, -sinθ cosφ)
  pixel:  col = cu + s * (P·r),   row = cv - s * (P·u')
Main ring: φ,cu from the 8-view fit (v9), s = px/m, cv from feet row.  Other views: registered against the
main-ring hull by silhouette IoU (φ, θ, s, cu, cv)."""
import numpy as np, cv2, json, glob, os, re, sys, importlib.util
spec = importlib.util.spec_from_file_location('ct', os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'check_turnaround.py'))
ct = importlib.util.module_from_spec(spec); spec.loader.exec_module(ct)
SRC = sys.argv[1]
H = W = 2048


sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import camera
project = camera.project


# ---- views and masks
views = {}
for f in sorted(glob.glob(os.path.join(SRC, '*.jpg'))):
    n = os.path.basename(f)[:-4]
    m = ct.segment(cv2.imread(f))[0]
    cv2.imwrite(f'mask_{n}.png', m.astype(np.uint8) * 255)
    mm = re.search(r'(\d{3})deg', n)
    ang = int(mm.group(1)) if mm else 0
    kind = 'top' if n.startswith('top') else 'el30' if n.startswith('el30') else 'low20' if n.startswith('low20') \
        else 'head' if n.startswith('head') else 'main'
    views[n] = dict(file=f, kind=kind, ang=ang)
print('views', len(views), ' angle limits ±%.0f° / ±%.0f°%s' % (camera.MAX_DPHI, camera.MAX_DTH, '（照片檢查通過）' if camera.CHECK_PASSED else ''))

# ---- main ring: orthographic cameras straight from the silhouettes (height 1.65 m, feet at y = 0,
# rotation axis = centre between the calves, angle from the file name); refine33.py fine-tunes them
HEIGHT = 1.65
cams = {}
for n, v in views.items():
    if v['kind'] == 'main':
        m = cv2.imread(f'mask_{n}.png', 0) > 0
        ys, xs = np.nonzero(m); t, b_ = ys.min(), ys.max()
        s = (b_ - t) / HEIGHT
        rr = int(t + 0.75 * (b_ - t)); xr = np.nonzero(m[rr])[0]
        cams[n] = dict(phi=float(v['ang']), th=0.0, s=float(s), cu=float((xr.min() + xr.max()) / 2), cv=float(b_), kind='main')


# ---- hull from the main ring (7-of-8 vote)
def carve(cam_list, vs=0.006, K=None, dil=2):
    xs = np.arange(-0.90, 0.90, vs) + vs / 2; ys = np.arange(0.0, 1.72, vs) + vs / 2; zs = np.arange(-0.38, 0.38, vs) + vs / 2
    X, Y, Z = np.meshgrid(xs, ys, zs, indexing='ij')
    P = np.stack([X.ravel(), Y.ravel(), Z.ravel()], 1)
    votes = np.zeros(len(P), np.uint8)
    for n in cam_list:
        m = cv2.dilate((cv2.imread(f'mask_{n}.png', 0) > 0).astype(np.uint8), np.ones((2 * dil + 1,) * 2, np.uint8))
        c_, r_ = project(P, cams[n])
        ci, ri = np.round(c_).astype(int), np.round(r_).astype(int)
        ok = (ci >= 0) & (ci < W) & (ri >= 0) & (ri < H)
        votes += ok & (m[np.clip(ri, 0, H - 1), np.clip(ci, 0, W - 1)] > 0)
    K = len(cam_list) if K is None else K
    occ = (votes >= K).reshape(X.shape)
    return occ, (xs, ys, zs)


def surface_points(occ, g):
    from scipy import ndimage as ndi
    sh = occ & ~ndi.binary_erosion(occ)
    i, j, k = np.nonzero(sh)
    return np.stack([g[0][i], g[1][j], g[2][k]], 1)


def iou_view(P, c, m_small, ds):
    cc, rr = project(P, c)
    img = np.zeros(m_small.shape, np.uint8)
    ci, ri = (cc / ds).astype(int), (rr / ds).astype(int)
    ok = (ci >= 0) & (ci < img.shape[1]) & (ri >= 0) & (ri < img.shape[0])
    img[ri[ok], ci[ok]] = 1
    img = cv2.morphologyEx(img, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    img = ndi_fill(img) > 0
    return (img & m_small).sum() / max(1, (img | m_small).sum())


def ndi_fill(img):
    from scipy import ndimage as ndi
    return ndi.binary_fill_holes(img).astype(np.uint8)


main = [n for n in views if views[n]['kind'] == 'main']
occ, g = carve(main, K=7)
P = surface_points(occ, g)
print('main hull surface points', len(P))

NOM = {'el30': 30.0, 'low20': -20.0, 'top': 90.0}
PERSPECTIVE = os.environ.get('BODY3D_PERSPECTIVE', '1') != '0'
PERSP_MIN_GAIN = 0.01             # IoU gain a camera distance must bring (0.005 gave false perspective on orthographic photos)
DS = 4
for n, v in sorted(views.items()):
    if v['kind'] not in NOM:
        continue
    m = cv2.imread(f'mask_{n}.png', 0) > 0
    ms = cv2.resize(m.astype(np.uint8), (W // DS, H // DS), interpolation=cv2.INTER_AREA) > 0
    ys_, xs_ = np.nonzero(m)
    base = dict(phi=float(v['ang']), th=NOM[v['kind']], s=1.0, cu=0.0, cv=0.0)

    def fit_bbox(c):
        cc, rr = project(P, dict(c, s=1.0, cu=0.0, cv=0.0))
        # scale from the larger of width / height extents, offsets from bbox centres
        sw = (xs_.max() - xs_.min()) / (cc.max() - cc.min()); sh = (ys_.max() - ys_.min()) / (rr.max() - rr.min())
        s = sh if v['kind'] != 'top' else sw
        cu = (xs_.max() + xs_.min()) / 2 - s * (cc.max() + cc.min()) / 2
        cv_ = (ys_.max() + ys_.min()) / 2 - s * (rr.max() + rr.min()) / 2
        return dict(c, s=s, cu=cu, cv=cv_)
    best = None
    for dphi in (-6, -3, 0, 3, 6):
        for dth in (-8, -4, 0, 4, 8):
            if not camera.within_limits(n, dict(base, phi=base['phi'] + dphi, th=base['th'] + dth, kind=v['kind'])):
                continue
            c = fit_bbox(dict(base, phi=base['phi'] + dphi, th=min(90.0, base['th'] + dth)))
            sc = iou_view(P, c, ms, DS)
            if best is None or sc > best[0]:
                best = (sc, c)
    # local refinement of offsets and scale
    def local(sc, c):
        for step in (8, 4, 2):
            improved = True
            while improved:
                improved = False
                for key, dv in (('cu', step), ('cu', -step), ('cv', step), ('cv', -step), ('s', c['s'] * 0.01 * step / 4), ('s', -c['s'] * 0.01 * step / 4),
                                ('phi', step / 4), ('phi', -step / 4), ('th', step / 4), ('th', -step / 4)):
                    c2 = dict(c); c2[key] += dv
                    if not camera.within_limits(n, dict(c2, kind=v['kind'])):
                        continue
                    s2 = iou_view(P, c2, ms, DS)
                    if s2 > sc + 1e-4:
                        sc, c, improved = s2, c2, True
        return sc, c
    sc, c = local(*best)
    # perspective: AI images of the elevated / low rings are usually drawn with a close camera. Try camera
    # distances; keep one only when it clearly fits better than orthographic.
    if v['kind'] in ('el30', 'low20') and PERSPECTIVE:
        bestp = (sc, c)
        for Dm in (12.0, 8.0, 6.0, 5.0, 4.0, 3.0):
            sp, cp = local(iou_view(P, dict(c, D=Dm), ms, DS), dict(c, D=Dm))
            if sp > bestp[0]:
                bestp = (sp, cp)
        if bestp[0] > sc + PERSP_MIN_GAIN:
            print('%-14s perspective D %.1f m: IoU %.3f -> %.3f' % (n, bestp[1]['D'], sc, bestp[0]))
            sc, c = bestp
    c['kind'] = v['kind']
    cams[n] = c
    print('%-14s IoU %.3f  phi %6.1f th %5.1f s %7.1f cu %7.1f cv %7.1f D %s' % (n, sc, c['phi'], c['th'], c['s'], c['cu'], c['cv'], c.get('D')), flush=True)
json.dump(cams, open('cams33.json', 'w'), indent=1)
