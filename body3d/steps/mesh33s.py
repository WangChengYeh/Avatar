import numpy as np, json, trimesh, sys
from skimage import measure
from scipy.ndimage import gaussian_filter
occ = np.load(sys.argv[1]).astype(np.float32)
g = json.load(open('grid33.json')); VS = g["vs"]
vol = gaussian_filter(np.pad(occ, 4), 2.0)   # stronger: removes the hull ripples
verts, faces, _, _ = measure.marching_cubes(vol, 0.5)
verts -= 4
X = g['x0'] + verts[:, 0] * VS; Y = g['y0'] + verts[:, 1] * VS; Z = g['z0'] + verts[:, 2] * VS   # occ is (x, y, z)
m = trimesh.Trimesh(np.c_[X, Y, Z], faces, process=True)
m = max(m.split(only_watertight=False), key=lambda q: len(q.faces))
if m.volume < 0: m.invert()
trimesh.smoothing.filter_taubin(m, iterations=60)
m = m.simplify_quadric_decimation(face_count=200000)
m = max(m.split(only_watertight=False), key=lambda q: len(q.faces))
print('faces', len(m.faces), 'watertight', m.is_watertight, 'bounds', m.bounds.round(3).tolist())
m.export(sys.argv[2])
