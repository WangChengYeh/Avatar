"""Front/back overlays compare shared visible surfaces without filling occlusions."""

import csv
import json

import cv2
import numpy as np

import check_turnaround as checker
from conftest import run_py


def square(z):
    return np.array([[-0.75, -0.75, z], [0.75, -0.75, z],
                     [0.75, 0.75, z], [-0.75, 0.75, z]])


def test_reprojection_rejects_back_camera_occlusion():
    vertices = np.vstack((square(0.2), square(-0.2)))
    faces = np.array([[0, 1, 2], [0, 2, 3], [4, 5, 6], [4, 6, 7]])
    front = dict(phi=0, th=0, s=16, cu=16, cv=16)
    back = dict(front, phi=180)
    depth, points = checker.rasterize_surface(vertices, faces, front, 32, 32, with_points=True)
    back_depth, _ = checker.rasterize_surface(vertices, faces, back, 32, 32)
    foreground = np.ones((32, 32), np.uint8)
    image = np.full((32, 32, 3), 100, np.uint8)
    warped, shared, denominator = checker.reproject_photo(points, foreground > 0, front, depth, image, foreground)
    assert denominator == 32 * 32
    assert shared.any() and np.all(warped[shared] == 100)
    assert np.all(warped[~shared] == 216)
    _, hidden, _ = checker.reproject_photo(points, foreground > 0, back, back_depth, image, foreground)
    assert not hidden.any()


def test_perspective_raster_interpolation_preserves_pixel_positions():
    vertices = np.array([[-0.55, 0.52, 0.08], [0.54, 0.50, 0.6], [-0.22, 1.2, 0.3]])
    faces = np.array([[0, 1, 2]])
    cam = dict(phi=0, th=0, s=20, cu=16, cv=33, D=3.0)
    _, positions = checker.rasterize_surface(vertices, faces, cam, 64, 64, with_points=True)
    rows, cols = np.where(np.isfinite(positions[..., 0]))
    assert len(rows) > 100
    actual_cols, actual_rows = checker.camera_project(positions[rows, cols], cam)
    np.testing.assert_allclose(actual_cols, cols, atol=1e-5)
    np.testing.assert_allclose(actual_rows, rows, atol=1e-5)


def test_overlay_cli_writes_front_back_sheets_and_csv(tmp_path):
    photos, work, out = (tmp_path / directory for directory in ('photos', 'work', 'report'))
    photos.mkdir()
    work.mkdir()
    cameras = {}
    for kind, name, angle in (
        ('main', '01_000deg_front', 0),
        ('main', '05_180deg_back', 180),
        ('head', 'head_000deg', 0),
        ('head', 'head_180deg', 180),
        ('head', 'head_045deg', 45),
    ):
        mask = np.full((128, 128), 255, np.uint8)
        image = np.full((128, 128, 3), 100, np.uint8)
        assert cv2.imwrite(str(photos / f'{name}.jpg'), image)
        assert cv2.imwrite(str(work / f'mask_{name}.png'), mask)
        cameras[name] = dict(kind=kind, phi=angle, th=0, s=64, cu=64, cv=64)
    (work / 'cams33.json').write_text(json.dumps(cameras), encoding='utf-8')
    np.savez(work / 'uvmesh.npz', pos=np.vstack((square(0.2), square(-0.2))),
             tri=[[0, 1, 2], [0, 2, 3], [4, 5, 6], [4, 6, 7]])

    rc, output = run_py('check_turnaround.py', photos, '--head-overlap-work', work, '--view-overlay-dir', out)
    assert rc == 0, output
    assert {p.name for p in out.glob('*.png')} == {'main_front.png', 'main_back.png', 'head_front.png', 'head_back.png'}
    with (out / 'view_overlap.csv').open(encoding='utf-8') as report:
        rows = list(csv.DictReader(report))
    assert len(rows) == 6
    assert any(row['reference'] == 'head_000deg' and row['source'] == 'head_045deg' and
               row['luma_p90'] == '0.0' and float(row['coverage_percent']) > 5 for row in rows)
    assert any(row['reference'] == 'head_000deg' and row['source'] == 'head_180deg' and
               row['status'] == 'LOW_COVERAGE' for row in rows)
