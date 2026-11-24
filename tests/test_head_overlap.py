"""The pre-bake checker reports pose-aligned brightness and allows review warnings."""

import json

import cv2
import numpy as np
import pytest

import check_turnaround as checker

from conftest import lines, run_py


@pytest.mark.parametrize(("delta", "level", "exit_code"), [(15, "PASS", 0), (25, "WARN", 0), (26, "FAIL", 1)])
def test_head_overlap_compares_each_cheek(tmp_path, delta, level, exit_code):
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
    assert rc == exit_code, output
    assert any('head_045deg' in line and '0.0 / 255' in line for line in lines(output, 'PASS')), output
    assert any('head_315deg' in line and f'{delta:.1f} / 255' in line for line in lines(output, level)), output


def test_missing_landmarks_reports_incomplete_check(tmp_path):
    (tmp_path / 'cams33.json').write_text('{}', encoding='utf-8')
    rc, output = run_py('check_turnaround.py', tmp_path, '--head-overlap-work', tmp_path)
    assert rc == 0, output
    assert any('未完成檢查' in line for line in lines(output, 'WARN')), output


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
                oblique[index, 1] += 32
    np.save(tmp_path / 'face_lm33_045.npy', oblique)
    checker.report_landmark_alignment(
        tmp_path, {'head_000deg': front_cam, 'head_045deg': side_cam}, frontal, vertices, 2048)
    output = capsys.readouterr().out
    assert '1.100×' in output
    assert '嘴部用於驗證' in output
    mouth = next(line for line in lines(output, 'WARN') if 'head_045deg 嘴部' in line)
    assert '→ 32.0 px' in mouth and '局部對位' in mouth
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
