"""check_turnaround.py：乾淨的合成照片要通過；故意弄壞的照片要被抓出來"""
import shutil
import cv2
import numpy as np
import pytest
from conftest import run_py, lines


@pytest.fixture
def broken(synth_set, tmp_path):
    d = tmp_path / 'set'
    shutil.copytree(synth_set, d)
    return d


def check(folder):
    return run_py('check_turnaround.py', folder, '--out', folder.parent / 'report.png')


def test_version():
    rc, out = run_py('check_turnaround.py', '--version')
    assert rc == 0 and 'check_turnaround 1.' in out


def test_clean_set_passes(synth_set, tmp_path):
    rc, out = run_py('check_turnaround.py', synth_set, '--out', tmp_path / 'r.png')
    assert rc == 0, '\n'.join(lines(out, 'FAIL'))
    assert not lines(out, 'FAIL')
    assert (tmp_path / 'r.png').exists()


def test_missing_top_fails(broken):
    (broken / 'top.jpg').unlink()
    rc, out = check(broken)
    assert rc == 1
    assert any('top.jpg' in l for l in lines(out, 'FAIL'))


def test_missing_ring_image_fails(broken):
    (broken / 'low20_135deg.jpg').unlink()
    rc, out = check(broken)
    assert rc == 1
    assert any('135' in l for l in lines(out, 'FAIL'))


def test_wrong_angle_fails(broken):
    """45° 和 90° 的檔名對調：角度推算、真側面、鏡像對都要 FAIL"""
    a, b, t = broken / '02_045deg_front_left.jpg', broken / '03_090deg_left.jpg', broken / 'tmp.jpg'
    a.rename(t); b.rename(a); t.rename(b)
    rc, out = check(broken)
    fails = lines(out, 'FAIL')
    assert rc == 1
    assert any('45°' in l and '推算' in l for l in fails)
    assert any('90°' in l for l in fails)


def test_flipped_copy_warns(broken):
    """把右側圖左右翻轉當成左側：第 6b 項要指出翻轉複製"""
    im = cv2.imread(str(broken / '07_270deg_right.jpg'))
    cv2.imwrite(str(broken / '03_090deg_left.jpg'), cv2.flip(im, 1), [cv2.IMWRITE_JPEG_QUALITY, 95])
    rc, out = check(broken)
    assert any('翻轉複製' in l and '90°' in l for l in lines(out, 'WARN'))


def test_grey_smudge_fails(broken):
    """在身體輪廓（腰側）貼一塊灰白色塊：第 1b 項要 FAIL"""
    f = broken / '01_000deg_front.jpg'
    im = cv2.imread(str(f))
    m = im.min(2) < 235
    ys, xs = np.nonzero(m)
    row = int(ys.min() + 0.55 * (ys.max() - ys.min()))
    right = int(np.nonzero(m[row])[0].max())
    cv2.ellipse(im, (right, row), (110, 150), 0, 0, 360, (205, 205, 205), -1)
    cv2.imwrite(str(f), im, [cv2.IMWRITE_JPEG_QUALITY, 95])
    rc, out = check(broken)
    assert rc == 1
    assert any('灰白雜點' in l for l in lines(out, 'FAIL'))


def test_dark_image_flagged(broken):
    """其中一張曝光不足：第 9 項要抓出來（WARN 或 FAIL）"""
    f = broken / 'el30_090deg.jpg'
    im = cv2.imread(str(f)).astype(np.float32)
    m = im.min(2) < 235
    im[m] *= 0.6
    cv2.imwrite(str(f), im.clip(0, 255).astype(np.uint8), [cv2.IMWRITE_JPEG_QUALITY, 95])
    rc, out = check(broken)
    assert any('90' in l and ('曝光' in l or '亮度' in l) for l in lines(out, 'WARN') + lines(out, 'FAIL'))
