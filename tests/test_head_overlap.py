"""The pre-bake checker reports pose-aligned brightness and allows review warnings."""

import json

import cv2
import numpy as np
import pytest

import check_turnaround as checker

from conftest import lines, run_py


@pytest.mark.parametrize(("delta", "level"), [(12, "PASS"), (26, "WARN"), (60, "WARN")])   # cheek P90 target 20 (perfect photos 13–16)
def test_head_overlap_compares_each_cheek(tmp_path, delta, level, monkeypatch):
    work = tmp_path / 'work'
    work.mkdir()
    cameras = {}
    for name, angle, luma in [('head_000deg', 0, 140), ('head_045deg', 45, 140), ('head_315deg', 315, 140 + delta)]:
        image = np.full((512, 512), luma, dtype=np.uint8)
        assert cv2.imwrite(str(tmp_path / f'{name}.jpg'), image)
        assert cv2.imwrite(str(work / f'mask_{name}.png'), np.full_like(image, 255))
        cameras[name] = dict(phi=angle, th=0, s=1600, cu=256, cv=2700)
    (work / 'cams33.json').write_text(json.dumps(cameras), encoding='utf-8')
    np.save(work / 'face_lm33.npy', [[90, 66, 0], [422, 66, 0], [422, 420, 0], [90, 420, 0]])
    x, y = np.meshgrid(np.linspace(-0.12, 0.12, 120), np.linspace(1.40, 1.66, 120))
    points = np.column_stack((x.ravel(), y.ravel(), np.zeros(x.size)))
    normals = np.tile([0, 0, 1], (len(points), 1))
    np.savez(work / 'uvmesh.npz', pos=points, nrm=normals)

    rc, output = run_py('check_turnaround.py', tmp_path, '--head-overlap-work', work)
    assert rc == 0, output
    assert any('head_045deg' in line and '0.0 / 255' in line for line in lines(output, 'PASS')), output
    assert any('head_315deg' in line and f'{delta:.1f} / 255' in line for line in lines(output, level)), output
    if level == checker.PASS:
        monkeypatch.setattr(checker, 'report_landmark_alignment', lambda *args: True)
        assert checker.report_head_overlap(tmp_path, work) == 1


def test_missing_landmarks_reports_incomplete_check(tmp_path):
    (tmp_path / 'cams33.json').write_text('{}', encoding='utf-8')
    rc, output = run_py('check_turnaround.py', tmp_path, '--head-overlap-work', tmp_path)
    assert rc == 0, output
    assert any('未完成檢查' in line for line in lines(output, 'WARN')), output


def test_head_yaw_limit_checks_before_and_after_face_alignment(capsys):
    assert checker.report_head_yaws({
        'head_000deg': {'phi': 359},
        'head_045deg': {'phi': 56, 'pre_face': {'phi': 50}},
        'head_090deg': {'phi': 107},
    })
    output = capsys.readouterr().out
    assert any('head_000deg' in line and '-1.0°' in line for line in lines(output, 'PASS'))
    assert any('head_045deg 最終相機' in line for line in lines(output, 'FAIL'))
    assert any('head_090deg 最終相機' in line and '+17.0°' in line for line in lines(output, 'FAIL'))


@pytest.mark.parametrize('right_shift, expected', [(0, checker.PASS), (50, checker.FAIL)])   # FAIL > 2 % of 2048 px
def test_face_audit_checks_each_oblique_view_against_frontal_mesh(tmp_path, right_shift, expected, capsys):
    base = np.array([[-.2, 1.38, .1], [.2, 1.38, .1], [.2, 1.69, .1], [-.2, 1.69, .1]], dtype='<f4')
    raised = base + np.array([0, 0, .008], dtype='<f4')
    header = (b'ply\nformat binary_little_endian 1.0\nelement vertex 4\n'
              b'property float x\nproperty float y\nproperty float z\nelement face 2\n'
              b'property list uchar int vertex_indices\nend_header\n')
    faces = np.array([(3, (0, 1, 2)), (3, (0, 2, 3))],
                     dtype=[('count', 'u1'), ('vertices', '<i4', (3,))])
    for name, vertices in [('body33s_noface.ply', base), ('body33s.ply', raised)]:
        (tmp_path / name).write_bytes(header + vertices.tobytes() + faces.tobytes())

    x, y = np.meshgrid(np.linspace(-.10, .10, 26), np.linspace(1.46, 1.62, 18))
    points = np.column_stack((x.ravel(), y.ravel(), np.full(x.size, .108)))
    front = dict(phi=0, th=0, s=3000, cu=1024, cv=5600)
    frontal = np.column_stack(checker.camera_project(points, front))
    cameras = {'head_000deg': front}
    for angle, dx in [(45, 0), (315, right_shift)]:
        camera = dict(front, phi=angle)
        cameras[f'head_{angle:03d}deg'] = dict(camera, pre_face=dict(camera, cu=984))
        photo = np.column_stack(checker.camera_project(points, camera)) + [dx, 0]
        np.save(tmp_path / f'face_lm33_{angle:03d}.npy', photo)
    assert checker.report_face_reconstruction(tmp_path, cameras, frontal, 2048) is (expected == checker.FAIL)
    output = capsys.readouterr().out
    assert any('head_045deg' in line and '→ 0.0 mm' in line for line in lines(output, 'PASS'))
    assert any('head_315deg' in line for line in lines(output, expected))
    assert '鼻尖：朝正面為正，修正量中位數 +8.0 mm' in output


@pytest.mark.parametrize('delta, same_mask, level', [(0, True, 'PASS'), (45, True, 'WARN'), (0, False, 'FAIL')])   # P90 target 35
def test_body_head_pair_reprojects_same_nominal_angle(tmp_path, delta, same_mask, level, capsys):
    body, head = '05_180deg_back', 'head_180deg'
    work = tmp_path / 'work'
    work.mkdir()
    mask = np.zeros((512, 512), np.uint8)
    mask[60:280, 156:356] = 255
    for name, shade in [(body, 145), (head, 145 + delta)]:
        assert cv2.imwrite(str(tmp_path / f'{name}.jpg'), np.full((512, 512), shade, np.uint8))
        image_mask = mask if same_mask or name == head else np.roll(mask, 220, axis=1)
        assert cv2.imwrite(str(work / f'mask_{name}.png'), image_mask)
    cam = dict(phi=180, th=0, s=1000, cu=256, cv=1700)
    np.savez(work / 'uvmesh.npz',
             pos=[[-.1, 1.42, 0], [.1, 1.42, 0], [.1, 1.64, 0], [-.1, 1.64, 0]],
             tri=[[0, 1, 2], [0, 2, 3]])
    out = tmp_path / 'overlays'
    assert checker.report_body_head_pairs(tmp_path, work, {body: cam, head: cam}, out) is (level == 'FAIL')
    output = capsys.readouterr().out
    assert any(f'{body} → {head}' in line for line in lines(output, level))
    assert (out / 'body_head_overlap.png').is_file()
    row = (out / 'body_head_overlap.csv').read_text().splitlines()[1]
    assert row.startswith(f'180,{body},{head},') and row.endswith(f',{level}')
    if not same_mask:
        assert '亮度差取樣不足' in output


def test_photo_cheek_brightness_uses_local_samples(monkeypatch):
    monkeypatch.setattr(checker, 'results', [])
    mask = np.ones((512, 512), bool)
    front = np.full((512, 512, 3), 140, np.uint8)
    oblique = front.copy()
    oblique[210:270, 220:310] = 166
    checker.check_photo_cheek_brightness({
        0: {'im': front, 'm': mask},
        45: {'im': front, 'm': mask},
        315: {'im': oblique, 'm': mask},
    })
    assert [result[0] for result in checker.results] == [checker.PASS, checker.WARN]


def test_landmark_alignment_reserves_mouth_as_validation(tmp_path, capsys):
    vertices = np.array([
        [-0.2, 1.39, 0.1], [0.2, 1.39, 0.1], [0.2, 1.68, 0.1], [-0.2, 1.68, 0.1],
    ])
    np.savez(tmp_path / 'uvmesh.npz', tri=[[0, 1, 2], [0, 2, 3]])
    front_cam = dict(phi=0, th=0, s=3000, cu=1024, cv=5600)
    side_cam = dict(front_cam, phi=45)
    frontal = np.zeros((468, 2))
    oblique = np.zeros((468, 2))
    for group, indices in checker.FEATURE_POINTS:
        for i, index in enumerate(indices):
            point = np.array([-0.09 + 0.02 * i, {'眼部': 1.60, '鼻部': 1.55, '嘴部': 1.48}[group], 0.1])
            frontal[index] = checker.camera_project(point, front_cam)
            oblique[index] = np.array(checker.camera_project(point, side_cam)) * 1.10 + [15, 5]
            if group == '嘴部':
                oblique[index, 1] += 50
    np.save(tmp_path / 'face_lm33_045.npy', oblique)
    kpis = {}
    assert checker.report_landmark_alignment(
        tmp_path, {'head_000deg': front_cam, 'head_045deg': side_cam}, frontal, vertices, 2048, kpis)
    error, level = kpis['head_045deg']['嘴部']
    assert error == pytest.approx(50)
    assert level == checker.FAIL
    output = capsys.readouterr().out
    assert '1.100×' in output
    assert '嘴部用於驗證' in output
    mouth = next(line for line in lines(output, 'FAIL') if 'head_045deg 嘴部' in line)
    assert '→ 50.0 px' in mouth and '局部對位' in mouth
    assert 'head_315deg：缺少斜面特徵點' in output


def test_mesh_projection_uses_foremost_triangle():
    xy = np.array([[0.0, 0.0], [1.0, 0.0], [0.0, 1.0]])
    back = np.column_stack((xy, np.zeros(3)))
    front = np.column_stack((xy, np.ones(3)))
    triangles = np.stack((back, front))
    point, normal = checker.mesh_point_at(np.array([0.25, 0.25]), triangles, triangles[:, :, :2],
                                          triangles[:, :, 2])
    np.testing.assert_allclose(point, [0.25, 0.25, 1.0])
    np.testing.assert_allclose(normal, [0, 0, 1])


def test_face_dimensions_compare_proportions_after_scale(capsys):
    samples = {
        checker.RIGHT_EYE_CENTER: (np.array([10, 0]), np.array([25, 0])),
        checker.LEFT_EYE_CENTER: (np.array([110, 0]), np.array([145, 0])),
        (98,): (np.array([20, 40]), np.array([40, 50])),
        (327,): (np.array([60, 40]), np.array([100, 50])),
    }
    # feature sizes are diagnostic only (#28: perfect photos differ by up to 29 %): never a failure
    assert not checker.report_face_dimensions('head_045deg', samples, scale=1.2)
    output = capsys.readouterr().out
    eyes = next(line for line in lines(output, 'INFO') if '眼距（眼角中點）' in line)
    assert '原始投影 100.0' in eyes and '照片 120.0' in eyes and '縮放後差 +0.0' in eyes
    nose = next(line for line in lines(output, 'INFO') if '鼻翼寬' in line)
    assert '縮放後差 +12.0 px（+25.0%）' in nose
    assert '嘴寬：共同可見點不足' in output


def test_bilateral_spans_use_one_visible_eye_from_each_side(capsys):
    frontal = np.zeros((468, 2))
    frontal[list(checker.RIGHT_EYE_CENTER), 0] = 100
    frontal[list(checker.LEFT_EYE_CENTER), 0] = 300
    kpis = {}
    assert not checker.report_bilateral_dimensions(frontal, {
        'head_315deg': {checker.RIGHT_EYE_CENTER: np.array([90, 0])},
        'head_045deg': {checker.LEFT_EYE_CENTER: np.array([320, 0])},
    }, kpis)
    assert kpis['bilateral_eye_span'] == (15.0, 'INFO')
    output = capsys.readouterr().out
    eye_distance = next(line for line in lines(output, 'INFO') if '眼距（眼角中點）' in line)
    assert '正面照片 200.0 px' in eye_distance and '左右斜面回投 230.0 px' in eye_distance
    assert '差 +30.0 px（+15.0%）' in eye_distance


@pytest.mark.parametrize(('label', 'pixels', 'fraction', 'calibrated'), [
    ('鼻翼寬', 6.0, 0.09, True), ('顴部寬', 150.0, 0.24, True), ('嘴寬', 2.0, 0.11, False),
])
def test_dimension_sizes_are_diagnostic_only(label, pixels, fraction, calibrated):
    """#28: MediaPipe on 3/4 close-ups against the silhouette-built face differs by up to 29 % on perfect photos"""
    assert checker.dimension_status(label, pixels, fraction, calibrated) == 'INFO'


def _head_ring(tmp_path, odd=None):
    """a 9 cm cylinder 'head' seen by the 8 close-ups; skin luma 170 everywhere, the `odd` close-up drawn with stripes"""
    work = tmp_path / 'work'
    work.mkdir()
    a, y = np.meshgrid(np.linspace(0, 2 * np.pi, 97)[:-1], np.linspace(1.40, 1.66, 40))
    pos = np.column_stack((0.09 * np.sin(a).ravel(), y.ravel(), 0.09 * np.cos(a).ravel()))
    nrm = np.column_stack((np.sin(a).ravel(), np.zeros(a.size), np.cos(a).ravel()))
    i = np.arange(96)[None, :] + 96 * np.arange(39)[:, None]
    j = (i % 96 + 1) % 96 + i // 96 * 96
    tri = np.concatenate([np.stack([i, j, i + 96], -1).reshape(-1, 3), np.stack([j, j + 96, i + 96], -1).reshape(-1, 3)])
    np.savez(work / 'uvmesh.npz', pos=pos, nrm=nrm, tri=tri)
    cameras = {}
    for angle in range(0, 360, 45):
        name = f'head_{angle:03d}deg'
        image = np.full((512, 512), 170, np.uint8)
        if angle == odd:
            image[(np.arange(512) // 20) % 2 == 1] = 120
        assert cv2.imwrite(str(tmp_path / f'{name}.jpg'), image)
        assert cv2.imwrite(str(work / f'mask_{name}.png'), np.full_like(image, 255))
        cameras[name] = dict(phi=angle, th=0, s=1600, cu=256, cv=2700, kind='head')
    return work, cameras


def test_head_pairs_pass_when_the_close_ups_agree(tmp_path, capsys):
    work, cameras = _head_ring(tmp_path)
    assert not checker.report_head_pairs(tmp_path, work, cameras)
    out = capsys.readouterr().out
    assert len(lines(out, 'PASS')) == 8 and not lines(out, 'FAIL'), out


def test_head_pairs_name_the_close_up_that_disagrees(tmp_path, capsys):
    work, cameras = _head_ring(tmp_path, odd=90)
    assert checker.report_head_pairs(tmp_path, work, cameras)
    out = capsys.readouterr().out
    failed = lines(out, 'FAIL')
    assert len(failed) == 2 and all('head_090deg' in line for line in failed), out
    assert '要重畫的頭部特寫：head_090deg。' in out, out
    import diagnose
    leaf, = diagnose.head_pair_leaves(failed)
    assert leaf['owner'] == '照片' and leaf['action'].startswith('重畫：head_090deg。'), leaf
