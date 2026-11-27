"""Round the visual hull's facet edges (octagon corners, flat shoulder tops) with a 3-D morphological opening;
keep thin parts (forearms / hands, |x| > 0.40 m) as they are so they are not eroded away."""
import numpy as np, json, sys
from scipy import ndimage as ndi
occ = np.load(sys.argv[1]); g = json.load(open('grid33.json')); vs = g['vs']
R = int(sys.argv[3]) if len(sys.argv) > 3 else 4
r = np.arange(-R, R + 1)
ball = (r[:, None, None] ** 2 + r[None, :, None] ** 2 + r[None, None, :] ** 2) <= R * R
op = ndi.binary_opening(occ, structure=ball)
xs = g['x0'] + np.arange(occ.shape[0]) * vs
keep_thin = np.abs(xs) > 0.40
out = np.where(keep_thin[:, None, None], occ, op)
# the feet: the forefoot is about 2 cm thick, thinner than the opening ball (2R + 1 voxels = 28 mm at 4 mm), so
# wherever the photos left it a little thin the opening removed it whole. Gemini avatar_001 v010 (the feet stand
# differently in every view, the hull keeps 790 cm3 of them; perfect photos about 2050): 21.6 cm long before, 12.8 cm
# after, and the model stood on ankle stubs. Below FOOT_Y a 1-voxel ball only removes specks: 21.2 cm (perfect
# photos 24.0 / 23.6 cm with either ball).
FOOT_Y, FOOT_R = 0.10, 1
ys = g['y0'] + np.arange(occ.shape[1]) * vs
rf = np.arange(-FOOT_R, FOOT_R + 1)
small = (rf[:, None, None] ** 2 + rf[None, :, None] ** 2 + rf[None, None, :] ** 2) <= FOOT_R * FOOT_R
foot = ys < FOOT_Y
if R > FOOT_R and foot.any():
    out[:, foot, :] = np.where(keep_thin[:, None, None], occ, ndi.binary_opening(occ, structure=small))[:, foot, :]
# never lose whole small components (fingers, feet tips): add back anything the opening removed that is
# isolated from the opened body by less than R voxels only when it is a thin limb part
print('voxels before %d after %d' % (occ.sum(), out.sum()))
np.save(sys.argv[2], out)
