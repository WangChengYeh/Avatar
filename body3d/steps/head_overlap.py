"""Advisory brightness check on overlapping frontal and oblique head projections."""

import json
from pathlib import Path

import cv2
import numpy as np

from . import camera


FRONT = 'head_000deg'
CHEEKS = (('左臉頰', 'head_045deg', 1), ('右臉頰', 'head_315deg', -1))
MIN_SAMPLES = 60
# Provisional review threshold on the 0–255 luma scale.
LUMA_REVIEW = 40.0


def projected_samples(points, normals, cam, image, mask):
    """Sample luma on surface points visible in this source photo."""
    col, row = camera.project(points, cam)
    height, width = image.shape
    in_frame = (col >= 1) & (row >= 1) & (col < width - 2) & (row < height - 2)
    col = np.clip(col, 0, width - 1)
    row = np.clip(row, 0, height - 1)
    incidence = np.einsum('ij,ij->i', normals, camera.toward(points, cam))

    cell = 4
    grid_width, grid_height = width // cell + 1, height // cell + 1
    x, y = (col / cell).astype(int), (row / cell).astype(int)
    depth = camera.depth(points, cam)
    depth_grid = np.full((grid_height, grid_width), -1e9, dtype=np.float32)
    np.maximum.at(depth_grid, (y[in_frame], x[in_frame]), depth[in_frame])
    visible = depth >= cv2.dilate(depth_grid, np.ones((3, 3), np.uint8))[y, x] - 0.012
    col_index, row_index = np.rint(col).astype(int), np.rint(row).astype(int)
    valid = in_frame & visible & (incidence > 0.2) & (mask[row_index, col_index] > 0)
    return col_index, row_index, image[row_index, col_index].astype(float), valid


def read_view(folder, work, stem):
    image = cv2.imread(str(folder / f'{stem}.jpg'), cv2.IMREAD_GRAYSCALE)
    mask = cv2.imread(str(work / f'mask_{stem}.png'), cv2.IMREAD_GRAYSCALE)
    if image is None or mask is None or image.shape != mask.shape:
        raise ValueError(f'{stem} 缺少可配對的照片或遮罩')
    mask = cv2.erode(mask, np.ones((9, 9), np.uint8))
    return image, mask


def cheek_band(landmarks, shape, col, row):
    """Locate the transition around the eroded landmark outline used for the frontal bake."""
    face = np.zeros(shape, np.uint8)
    hull = cv2.convexHull(np.rint(landmarks).astype(np.int32))
    cv2.fillConvexPoly(face, hull, 1)
    face = cv2.erode(face, np.ones((61, 61), np.uint8))
    inside = cv2.distanceTransform(face, cv2.DIST_L2, 3)
    outside = cv2.distanceTransform(1 - face, cv2.DIST_L2, 3)

    top, bottom = landmarks[:, 1].min(), landmarks[:, 1].max()
    face_height = bottom - top
    cheek_rows = (row >= top + 0.45 * face_height) & (row <= top + 0.90 * face_height)
    return cheek_rows & (inside[row, col] <= 32) & (outside[row, col] <= 32)


def report(folder, work):
    folder, work = Path(folder), Path(work)
    try:
        cameras = json.loads((work / 'cams33.json').read_text(encoding='utf-8'))
        landmarks = np.load(work / 'face_lm33.npy')
        if (landmarks.ndim != 2 or landmarks.shape[0] < 3 or landmarks.shape[1] < 2
                or not np.isfinite(landmarks[:, :2]).all()):
            raise ValueError('正面臉部特徵點無效')
        landmarks = landmarks[:, :2]
        with np.load(work / 'uvmesh.npz') as mesh:
            vertices = mesh['pos']
            head = vertices[:, 1] >= 1.40
            points, normals = vertices[head], mesh['nrm'][head]
        frontal_image, frontal_mask = read_view(folder, work, FRONT)
        col, row, frontal_luma, frontal_valid = projected_samples(
            points, normals, cameras[FRONT], frontal_image, frontal_mask)
    except (OSError, KeyError, IndexError, ValueError) as error:
        print(f'[WARN] 頭部投影重疊：未完成檢查（{error}）')
        return

    band = cheek_band(landmarks, frontal_image.shape, col, row)
    face_midline = np.median(landmarks[:, 0])
    for cheek, side, direction in CHEEKS:
        label = f'{cheek} {FRONT} / {side}'
        try:
            image, mask = read_view(folder, work, side)
            _, _, side_luma, side_valid = projected_samples(points, normals, cameras[side], image, mask)
        except (ValueError, KeyError) as error:
            print(f'[WARN] {label}：未完成檢查（{error}）')
            continue

        common = band & frontal_valid & side_valid & (direction * (col - face_midline) > 0)
        count = np.count_nonzero(common)
        if count < MIN_SAMPLES:
            print(f'[WARN] {label}：共同可見取樣不足（{count} 點）')
            continue

        delta = np.abs(frontal_luma[common] - side_luma[common])
        median = float(np.median(delta))
        p90 = float(np.percentile(delta, 90))
        status = 'WARN' if p90 >= LUMA_REVIEW else 'PASS'
        guidance = '，接合處可能出現色帶，請複核照片的亮度及對位' if status == 'WARN' else ''
        print(f'[{status}] {label}：亮度絕對差中位數 {median:.1f}，第 90 百分位 {p90:.1f} / 255'
              f'（{count} 點）{guidance}')
