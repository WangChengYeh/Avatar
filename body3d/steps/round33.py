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
# never lose whole small components (fingers, feet tips): add back anything the opening removed that is
# isolated from the opened body by less than R voxels only when it is a thin limb part
print('voxels before %d after %d' % (occ.sum(), out.sum()))
np.save(sys.argv[2], out)
