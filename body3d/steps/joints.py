"""Estimate humanoid joint positions (glTF frame: X = her left, Y up, Z forward) from the T-pose mesh."""
import numpy as np, trimesh, json, sys
from scipy import ndimage as ndi
m = trimesh.load(sys.argv[1]); v = m.vertices
H = v[:, 1].max(); xmax = v[:, 0].max(); xmin = v[:, 0].min()
print('height %.3f  span %.3f..%.3f' % (H, xmin, xmax))


def slab(axis, lo, hi):
    return v[(v[:, axis] >= lo) & (v[:, axis] < hi)]


# --- crotch: highest y where a horizontal slice near the centre line is empty (gap between legs)
crotch = None
for y in np.arange(0.5, 1.0, 0.005):
    s = slab(1, y, y + 0.005)
    c = s[np.abs(s[:, 0]) < 0.12]
    if len(c) and np.abs(c[:, 0]).min() > 0.012:
        crotch = y
print('crotch %.3f' % crotch)


def leg_centre(y, side):
    s = slab(1, y - 0.01, y + 0.01); s = s[np.sign(s[:, 0]) == side]; s = s[np.abs(s[:, 0]) < 0.25]
    return np.array([s[:, 0].mean(), y, (s[:, 2].min() + s[:, 2].max()) / 2])


# --- arm centre line at several x (T-pose arms along X)
def arm_centre(x):
    s = slab(0, x - 0.01, x + 0.01) if x > 0 else slab(0, x - 0.01, x + 0.01)
    s = s[s[:, 1] > 1.0]
    return np.array([x, (s[:, 1].min() + s[:, 1].max()) / 2, (s[:, 2].min() + s[:, 2].max()) / 2]), s[:, 1].max() - s[:, 1].min()


J = {}
# hip joints sit at the widest part of the hips (greater trochanter); thighs touch here so the leg gap is useless
ys_ = np.arange(0.40 * H, 0.62 * H, 0.005)
wid = []
for y in ys_:
    s = slab(1, y, y + 0.005); s = s[np.abs(s[:, 0]) < 0.30]
    wid.append(s[:, 0].max() - s[:, 0].min() if len(s) else 0)
y_hipw = ys_[int(np.argmax(wid))]
crotch = y_hipw - 0.06
print('widest hips at %.3f m (%.2f H)' % (y_hipw, y_hipw / H))
hips_y = 0.55 * H          # anthropometric: hip joint 0.53 H (knee 0.285 H / ankle 0.039 H measured here match the tables)
torso = slab(1, hips_y - 0.01, hips_y + 0.01); torso = torso[np.abs(torso[:, 0]) < 0.2]
zc_h = (torso[:, 2].min() + torso[:, 2].max()) / 2
J['Hips'] = [0.0, hips_y, zc_h]
# spine up to the neck base (shoulder line) — shoulder line = y of the arm centre near the torso
arm_y = arm_centre(0.30)[0][1]
neck_base = arm_y + 0.05
chest = slab(1, arm_y - 0.06, arm_y - 0.04); chest = chest[np.abs(chest[:, 0]) < 0.12]
zc_c = (chest[:, 2].min() + chest[:, 2].max()) / 2
for k, f in (('Spine', 0.22), ('Spine1', 0.48), ('Spine2', 0.74)):
    y = hips_y + f * (neck_base - hips_y)
    J[k] = [0.0, y, zc_h + f * (zc_c - zc_h)]
nk = slab(1, neck_base, neck_base + 0.02); nk = nk[np.abs(nk[:, 0]) < 0.06]
J['Neck'] = [0.0, neck_base, (nk[:, 2].min() + nk[:, 2].max()) / 2 - 0.005]
J['Head'] = [0.0, neck_base + 0.10, J['Neck'][2] + 0.005]
J['HeadTop_End'] = [0.0, H, J['Neck'][2]]
# arms: wrist = narrowest arm thickness between 64% and 84% of the half span; shoulder joint at ~22%
for side, name in ((1, 'Left'), (-1, 'Right')):
    tip = xmax if side > 0 else xmin
    span = abs(tip)
    xs = np.linspace(0.62, 0.86, 25) * span
    th = [arm_centre(side * x)[1] for x in xs]
    xw = xs[int(np.argmin(th))]
    xs_sh = 0.20 * span / 0.78 * 0.78 if False else 0.17
    c_sh = arm_centre(side * 0.19)[0]
    c_wr = arm_centre(side * xw)[0]
    x_el = 0.19 + 0.53 * (xw - 0.19)
    c_el = arm_centre(side * x_el)[0]
    J[name + 'Shoulder'] = [side * 0.035, arm_y + 0.02, c_sh[2] - 0.01]
    J[name + 'Arm'] = [side * 0.19, c_sh[1], c_sh[2]]
    J[name + 'ForeArm'] = list(c_el)
    J[name + 'Hand'] = list(c_wr)
    J[name + 'HandEnd'] = [side * (span - 0.01), c_wr[1], c_wr[2]]
    # legs
    hipj = leg_centre(y_hipw - 0.10, side); hipj[1] = 0.53 * H; hipj[0] = side * max(abs(hipj[0]), 0.085)
    kn = leg_centre(0.28 * H, side)
    an = leg_centre(0.065, side)
    J[name + 'UpLeg'] = list(hipj)
    J[name + 'Leg'] = list(kn)
    J[name + 'Foot'] = list(an)
    ft = slab(1, 0.0, 0.04); ft = ft[np.sign(ft[:, 0]) == side]; ft = ft[np.abs(ft[:, 0]) < 0.25]
    toe_z = ft[:, 2].max()
    J[name + 'ToeBase'] = [an[0], 0.02, an[2] + 0.65 * (toe_z - an[2])]
    J[name + 'ToeEnd'] = [an[0], 0.015, toe_z]
# symmetric feet (front-back) and legs
for a_, b_ in (('LeftFoot', 'RightFoot'), ('LeftToeBase', 'RightToeBase'), ('LeftToeEnd', 'RightToeEnd'), ('LeftLeg', 'RightLeg'), ('LeftUpLeg', 'RightUpLeg')):
    zz = (J[a_][2] + J[b_][2]) / 2; J[a_][2] = J[b_][2] = zz
    yy = (J[a_][1] + J[b_][1]) / 2; J[a_][1] = J[b_][1] = yy
for k, p in J.items():
    print('%-15s %s' % (k, np.round(p, 3)))
json.dump({k: [float(a) for a in p] for k, p in J.items()}, open('joints.json', 'w'), indent=1)
