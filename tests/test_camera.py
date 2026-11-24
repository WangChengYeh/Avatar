"""steps/camera.py：正交 / 透視投影的基本性質"""
import os, sys
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'body3d', 'steps'))
import camera

C = dict(phi=45.0, th=30.0, s=1000.0, cu=1024.0, cv=1900.0)
P = np.random.default_rng(0).uniform([-0.8, 0, -0.2], [0.8, 1.7, 0.2], (500, 3))


def test_far_perspective_equals_orthographic():
    a = np.c_[camera.project(P, C)]; b = np.c_[camera.project(P, dict(C, D=1e6))]
    assert np.abs(a - b).max() < 1e-2


def test_centre_plane_unchanged_and_near_points_magnified():
    r, u, f = camera.axes(C['phi'], C['th'])
    on_plane = camera.C0 + 0.3 * r                     # on the plane through C0 facing the camera
    near = camera.C0 + 0.3 * r + 0.5 * f               # same offset, 0.5 m closer to the camera
    o = np.c_[camera.project(on_plane[None], C)][0]
    p0 = np.c_[camera.project(on_plane[None], dict(C, D=4.0))][0]
    p1 = np.c_[camera.project(near[None], dict(C, D=4.0))][0]
    assert np.allclose(o, p0)
    c0 = np.c_[camera.project(camera.C0[None], C)][0]
    assert np.linalg.norm(p1 - c0) > np.linalg.norm(p0 - c0) * 1.1     # 4 / 3.5 = 1.14x


def test_toward_and_depth():
    t = camera.toward(P, dict(C, D=4.0))
    assert np.allclose(np.linalg.norm(t, axis=1), 1)
    _, _, f = camera.axes(C['phi'], C['th'])
    assert np.argmax(camera.depth(P, dict(C, D=4.0))) == np.argmax(P @ f)


def test_angle_limits():
    assert camera.within_limits('el30_045deg', dict(phi=50, th=25, kind='el30'))
    assert not camera.within_limits('el30_045deg', dict(phi=60, th=30, kind='el30'))
    assert not camera.within_limits('low20_000deg', dict(phi=0, th=0, kind='low20'))
