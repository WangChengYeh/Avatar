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
    assert camera.within_limits('el30_045deg', dict(phi=45, th=30, kind='el30'))
    assert not camera.within_limits('el30_045deg', dict(phi=70, th=30, kind='el30'))
    assert not camera.within_limits('low20_000deg', dict(phi=0, th=0, kind='low20'))


def test_elevated_and_low_rings_keep_input_elevation(monkeypatch):
    monkeypatch.setattr(camera, 'MAX_DTH', 16.0)
    for kind, elevation in (('el30', 30.0), ('low20', -20.0)):
        for yaw in range(0, 360, 45):
            name = f'{kind}_{yaw:03d}deg'
            calibrated = dict(phi=yaw, th=elevation, kind=kind)
            assert camera.nominal(name, kind) == (yaw, elevation)
            assert camera.within_limits(name, calibrated)
            assert not camera.within_limits(name, dict(calibrated, th=elevation - 0.5))
            assert not camera.within_limits(name, dict(calibrated, th=elevation + 0.5))
    assert camera.within_limits('head_045deg', dict(phi=45, th=1, kind='head'))


def _ring(th, s=950.0, U=1020.0, V=1010.0, q=(0.02, 0.85, -0.05), kind='el30'):
    ring = dict(s=s, U=U, V=V, qx=q[0], qy=q[1], qz=q[2], D=None)
    return {f'{kind}_{a:03d}deg': camera.ring_apply(dict(phi=float(a), th=th, kind=kind), ring) for a in range(0, 360, 45)}, ring


def test_ring_model_recovers_fixed_distance_and_centre():
    """a camera orbiting at a fixed distance, aimed at one point: same scale, the aim point on the same pixel"""
    for th, kind in ((0.0, 'main'), (30.0, 'el30'), (-20.0, 'low20')):
        cams, truth = _ring(th, kind=kind)
        fit = camera.ring_fit(cams, kind)
        for k in ('s', 'U', 'V', 'qx', 'qz'):
            assert abs(fit[k] - truth[k]) < 1e-6 * max(1, abs(truth[k])), (kind, k)
        Q = np.array([truth['qx'], truth['qy'], truth['qz']])[None]
        pix = {n: np.c_[camera.project(Q, c)][0] for n, c in cams.items()}
        assert all(np.allclose(p, (truth['U'], truth['V'])) for p in pix.values())
        dev = camera.ring_deviation(cams, kind, fit)
        assert max(abs(d['scale_pct']) for d in dev.values()) < 1e-6
        assert max(d['centre_mm'] for d in dev.values()) < 1e-6


def test_ring_deviation_flags_a_view_drawn_bigger_and_shifted():
    cams, _ = _ring(30.0)
    bad = 'el30_135deg'
    cams[bad] = dict(cams[bad], s=cams[bad]['s'] * 1.08, cu=cams[bad]['cu'] + 40)
    fit = camera.ring_fit(cams, 'el30')
    dev = camera.ring_deviation(cams, 'el30', fit)
    worst = max(dev, key=lambda n: abs(dev[n]['scale_pct']))
    assert worst == bad and dev[bad]['scale_pct'] > 7
    assert max(dev, key=lambda n: dev[n]['centre_mm']) == bad
    locked = camera.ring_apply(cams[bad], fit)
    assert abs(locked['s'] - fit['s']) < 1e-9


def test_ring_lock_follows_check_and_env(monkeypatch):
    monkeypatch.setattr(camera, 'CHECK_PASSED', True)
    monkeypatch.delenv('BODY3D_RING_LOCK', raising=False)
    assert camera.ring_lock_enabled()
    monkeypatch.setenv('BODY3D_RING_LOCK', '0')
    assert not camera.ring_lock_enabled()
    monkeypatch.setattr(camera, 'CHECK_PASSED', False)
    monkeypatch.delenv('BODY3D_RING_LOCK')
    assert not camera.ring_lock_enabled()


def test_fixed_distance_spec_matches_checker():
    import check_turnaround as ct
    assert (camera.BODY_FRAME, camera.HEAD_ZOOM) == (ct.BODY_FRAME, ct.HEAD_ZOOM) == (1.95, 4.0)
    cams = {'01_000deg': dict(kind='main', s=1000.0), '02_045deg': dict(kind='main', s=1010.0), 'el30_000deg': dict(kind='el30', s=900.0)}
    assert camera.body_scale(cams) == 1005.0


def test_full_body_views_share_body_centre_and_scale():
    source = {'01': dict(kind='main', s=1000.0), '02': dict(kind='main', s=1010.0)}
    rig = camera.body_center_rig(source, 2048, 2048)
    centre = np.array([[0.0, 0.825, 0.0]])
    for kind in ('main', 'el30', 'low20', 'top'):
        yaw, elevation = camera.nominal('el30_225deg' if kind != 'top' else 'top', kind)
        view = camera.ring_apply(dict(phi=yaw, th=elevation, s=950.0, D=4.0), rig)
        assert view['s'] == 1005.0 and 'D' not in view
        np.testing.assert_allclose(np.c_[camera.project(centre, view)], [[1024, 1024]])
