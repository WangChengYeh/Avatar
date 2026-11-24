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
    assert (tmp_path / 'r_head_review.png').exists()


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


def test_flipped_copy_fails_in_ai_mode_warns_in_photo_mode(broken):
    """把右側圖左右翻轉當成左側：第 6b 項指出翻轉複製；AI 模式（預設）FAIL，photo 模式 WARN"""
    im = cv2.imread(str(broken / '07_270deg_right.jpg'))
    cv2.imwrite(str(broken / '03_090deg_left.jpg'), cv2.flip(im, 1), [cv2.IMWRITE_JPEG_QUALITY, 95])
    rc, out = check(broken)
    assert any('翻轉複製' in l and '90°' in l for l in lines(out, 'FAIL'))
    rc, out = run_py('check_turnaround.py', broken, '--mode', 'photo', '--out', broken.parent / 'p.png')
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


def test_silhouette_sheet_and_perspective_pass_on_orthographic(synth_set, tmp_path):
    """第 10 / 10b 項：正交的合成照片要全部通過，並輸出紅藍對照圖"""
    rc, out = run_py('check_turnaround.py', synth_set, '--out', tmp_path / 'r.png')
    bad = [l for l in lines(out, 'FAIL') + lines(out, 'WARN') if '剪影:' in l or '透視:' in l]
    assert not bad, '\n'.join(bad)
    assert (tmp_path / 'r_silhouette_check.png').exists()
    assert len([l for l in lines(out, 'PASS') if '剪影' in l]) == 24
    assert len([l for l in lines(out, 'PASS') if '透視:' in l]) == 3


def test_perspective_set_fails(persp_set, tmp_path):
    """相機在 4 m 的透視照片：三個環的透視都要 FAIL，估計距離要接近 4 m；剪影藍色在手上"""
    import re
    rc, out = run_py('check_turnaround.py', persp_set, '--out', tmp_path / 'r.png')
    assert rc == 1
    fails = [l for l in lines(out, 'FAIL') if '透視:' in l]
    assert len(fails) == 3
    for l in fails:
        d = float(re.search(r'約 ([\d.]+) m', l).group(1))
        assert 3.0 < d < 6.5, l
    sil = [l for l in lines(out, 'FAIL') + lines(out, 'WARN') if '剪影' in l]
    assert len(sil) >= 8 and all('手' in l for l in sil)


def test_widened_view_fails_silhouette(broken):
    """把一張俯角圖左右拉寬 15%（手臂比主環長）：第 10 項這張要 FAIL，藍色在手上"""
    f = broken / 'el30_000deg.jpg'
    im = cv2.imread(str(f)); h, w = im.shape[:2]
    m = im.min(2) < 235; cx = np.nonzero(m)[1].mean()
    M = np.float32([[1.15, 0, cx * (1 - 1.15)], [0, 1, 0]])
    im = cv2.warpAffine(im, M, (w, h), borderValue=(255, 255, 255))
    cv2.imwrite(str(f), im, [cv2.IMWRITE_JPEG_QUALITY, 95])
    rc, out = check(broken)
    hit = [l for l in lines(out, 'FAIL') + lines(out, 'WARN') if 'el30 0° 剪影' in l]
    assert hit and '手' in hit[0]


def test_ring_width_ratios(synth_set, persp_set, tmp_path):
    """第 10c 項提示寬度比差異，第 10b 項仍能攔下 4 m 透視照片"""
    rc, out = run_py('check_turnaround.py', synth_set, '--out', tmp_path / 'a.png')
    assert len([l for l in lines(out, 'PASS') if '寬度比:' in l]) == 12
    rc, out = run_py('check_turnaround.py', persp_set, '--out', tmp_path / 'b.png')
    assert any('透視:' in l for l in lines(out, 'FAIL'))
    assert not any('寬度比:' in l for l in lines(out, 'FAIL'))
    assert sum('el30' in l and '寬度比:' in l and '優先複核' in l for l in lines(out, 'WARN')) >= 4


def test_preflight_reports_incompatible_and_duplicate_photos(tmp_path):
    photos = tmp_path / 'photos'
    photos.mkdir()
    blank = np.full((2048, 2048, 3), 255, np.uint8)
    frontal = photos / 'head_000deg.jpg'
    assert cv2.imwrite(str(frontal), blank)
    shutil.copyfile(frontal, photos / 'head_045deg.jpg')
    shutil.copyfile(frontal, photos / 'head_045deg_copy.jpg')
    shutil.copyfile(frontal, photos / 'head_090deg.jpeg')
    assert cv2.imwrite(str(photos / 'head_135deg.jpg'), blank[:, :1920])

    rc, out = check(photos)
    failed = lines(out, 'FAIL')
    assert rc == 1
    assert any('head_045deg.jpg' in l and '像素完全相同' in l for l in failed)
    assert any('head_045deg_copy.jpg' in l and '同一個' in l for l in failed)
    assert any('head_090deg.jpeg' in l and '小寫 .jpg' in l for l in failed)
    assert any('head_135deg.jpg' in l and '1920 × 2048' in l for l in failed)
    assert 'Traceback' not in out



def test_clean_set_has_no_warnings_in_ai_mode(synth_set, tmp_path):
    """嚴格模式的門檻是「完美照片 + 小餘裕」：完美照片的幾何 / 一致性項目連 WARN 都不能有。
    曝光與臉頰亮度（1.15–1.18 收緊到 ±3%、5 / 255）量的是光線：合成照片取自 v9 模型的烘焙貼圖，亮度本身不均，
    不列入這個測試"""
    rc, out = run_py('check_turnaround.py', synth_set, '--out', tmp_path / 'r.png')
    lighting = ('曝光', '亮度')
    other = [l for l in lines(out, 'FAIL') + lines(out, 'WARN') if not any(k in l for k in lighting)]
    assert not other, '\n'.join(other)
    assert any('head 45° vs 0° 髮高比' in l for l in lines(out, 'PASS'))


def test_flat_hair_in_three_quarter_closeup_fails(broken):
    """第 11 項：45° 頭部特寫的頭髮壓扁 15%（臉相對變大）→ 髮高比 FAIL（兩層臉的原因）"""
    f = broken / 'head_045deg.jpg'
    im = cv2.imread(str(f)); h, w = im.shape[:2]
    m = im.min(2) < 235; top = int(np.nonzero(m.any(1))[0].min()); y0 = int(0.36 * h)
    yo = np.arange(h, dtype=np.float32)[:, None].repeat(w, 1)
    src = np.where(yo < y0, y0 - (y0 - yo) / 0.85, yo).astype(np.float32)
    src[src < top - 5] = 0                                   # above the squeezed hair: white background row 0
    xo = np.arange(w, dtype=np.float32)[None, :].repeat(h, 0)
    im2 = cv2.remap(im, xo, src, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    cv2.imwrite(str(f), im2, [cv2.IMWRITE_JPEG_QUALITY, 95])
    rc, out = check(broken)
    assert any('head 45° vs 0° 髮高比' in l for l in lines(out, 'FAIL'))


def test_closeup_without_face_fails(broken):
    """第 11 項：3/4 頭部特寫看不到臉（換成後腦勺）→ FAIL"""
    im = cv2.imread(str(broken / 'head_135deg.jpg')).astype(np.int16)
    im = np.clip(im + 2, 0, 255).astype(np.uint8)        # not pixel-identical (the input pre-check stops on exact copies)
    cv2.imwrite(str(broken / 'head_045deg.jpg'), im, [cv2.IMWRITE_JPEG_QUALITY, 95])
    rc, out = check(broken)
    assert any('head 45° 臉部' in l and '找不到臉' in l for l in lines(out, 'FAIL'))
