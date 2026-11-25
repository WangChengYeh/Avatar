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
    """曝光粗篩與同一表面的亮差都會標記偏暗的視角。"""
    f = broken / 'el30_090deg.jpg'
    im = cv2.imread(str(f)).astype(np.float32)
    m = im.min(2) < 235
    im[m] *= 0.6
    cv2.imwrite(str(f), im.clip(0, 255).astype(np.uint8), [cv2.IMWRITE_JPEG_QUALITY, 95])
    rc, out = check(broken)
    assert any('90' in l and '曝光' in l for l in lines(out, 'WARN'))
    assert any('el30 90° / 主環 90° 表面亮度' in l for l in lines(out, 'WARN'))


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
    """第 10c 項：完美照片全部 PASS；4 m 透視照片的俯角環寬度比在 AI 模式 FAIL（#23），photo 模式只提示複核"""
    rc, out = run_py('check_turnaround.py', synth_set, '--out', tmp_path / 'a.png')
    assert len([l for l in lines(out, 'PASS') if '寬度比:' in l]) == 12
    rc, out = run_py('check_turnaround.py', persp_set, '--out', tmp_path / 'b.png')
    assert any('透視:' in l for l in lines(out, 'FAIL'))
    assert sum('el30' in l and '寬度比:' in l for l in lines(out, 'FAIL')) >= 4
    rc, out = run_py('check_turnaround.py', persp_set, '--mode', 'photo', '--out', tmp_path / 'c.png')
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
    """嚴格模式的門檻是「完美照片 + 小餘裕」：完美照片連 WARN 都不能有（曝光與臉頰粗篩 1.23.0 依完美照片重新校準）"""
    rc, out = run_py('check_turnaround.py', synth_set, '--out', tmp_path / 'r.png')
    lighting = ()
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


@pytest.mark.parametrize(('ai', 'fail_limit', 'status'), [(True, 4, 'FAIL'), (False, 8, 'WARN')])
def test_face_report_uses_mode_thresholds(monkeypatch, ai, fail_limit, status):
    import check_turnaround as checker

    monkeypatch.setitem(checker.MODE, 'ai', ai)
    monkeypatch.setattr(checker, 'face_measures',
                        lambda angle, _: (0.3 * (1 if angle == 0 else 1.024),
                                          0.4 * (1 if angle == 0 else 1.055 * 1.06), 140))
    heads = {angle: {'im': angle, 'm': object()} for angle in (0, 45, 315)}
    report = checker.face_check({'head': heads})
    hair = [(level, message) for level, label, message in report if '髮高比' in label]
    assert len(hair) == 2
    assert all(level == status and f'> {fail_limit}% 判 FAIL' in message for level, message in hair)


def _zoom(path, k):
    """redraw one photo with the camera moved closer (k > 1) or farther (k < 1), same centre, white background"""
    im = cv2.imread(str(path)); h, w = im.shape[:2]
    M = np.float32([[k, 0, (1 - k) * w / 2], [0, k, (1 - k) * h / 2]])
    cv2.imwrite(str(path), cv2.warpAffine(im, M, (w, h), borderValue=(255, 255, 255)), [cv2.IMWRITE_JPEG_QUALITY, 95])


def test_fixed_camera_distance(broken):
    """10d: same framing in every full-body ring, a fixed zoom for the close-ups. The clean set passes; one el30
    view drawn 4 % bigger, one close-up drawn 8 % smaller and a side close-up 8 % bigger fail at their own angle only"""
    rc, out = check(broken)
    d = [l for l in out.splitlines() if '距離:' in l or '放大倍率' in l]
    assert len(d) == 25 and all('[PASS]' in l for l in d), d      # 16 full-body widths, top, 8 close-ups
    _zoom(broken / 'el30_135deg.jpg', 1.04)
    _zoom(broken / 'head_045deg.jpg', 0.92)
    _zoom(broken / 'head_270deg.jpg', 1.08)          # side close-ups are checked too
    rc, out = check(broken)
    fails = [l for l in lines(out, 'FAIL') if '距離' in l or '放大倍率' in l]
    assert any('el30 135° 距離' in l and '畫大了' in l for l in fails), fails
    assert any('head 45° 放大倍率' in l and '畫小了' in l for l in fails), fails
    assert any('head 270° 放大倍率' in l and '畫大了' in l for l in fails), fails
    assert len(fails) == 3, fails


def _shift(path, dx=0, dy=0, sy=1.0):
    """move one photo's camera aim (dx, dy px) or stretch the figure vertically about its feet (sy)"""
    im = cv2.imread(str(path)); h, w = im.shape[:2]
    m = im.min(2) < 235; feet = np.nonzero(m)[0].max()
    M = np.float32([[1, 0, dx], [0, sy, dy + (1 - sy) * feet]])
    cv2.imwrite(str(path), cv2.warpAffine(im, M, (w, h), borderValue=(255, 255, 255)), [cv2.IMWRITE_JPEG_QUALITY, 95])


def test_aim_point_and_tilt(broken):
    """10e: the clean set passes; a low20 view shifted sideways, or an el30 pair framed off the image centre, fails centring, an el30 view moved up fails the aim
    height, and a low20 view drawn without the −20° foreshortening (4 % taller) fails the tilt"""
    rc, out = check(broken)
    e = [l for l in out.splitlines() if '置中:' in l or '俯仰角:' in l or '對準高度:' in l]
    assert len(e) >= 40 and all('[PASS]' in l for l in e), [l for l in e if '[PASS]' not in l]
    _shift(broken / 'low20_045deg.jpg', dx=40)
    for g in ('el30_000deg.jpg', 'el30_180deg.jpg'):     # a whole pair framed off-centre: invisible to a ring median
        _shift(broken / g, dx=20)
    _shift(broken / 'el30_090deg.jpg', dy=-40)
    _shift(broken / 'low20_000deg.jpg', sy=1.04)
    rc, out = check(broken)
    fails = lines(out, 'FAIL')
    assert any('仰角環 45° / 225° 置中' in l for l in fails), fails
    assert any('俯角環 0° / 180° 置中' in l for l in fails), fails
    assert any('el30 90° 對準高度' in l for l in fails), fails
    assert any('low20 0° 俯仰角' in l and '沒有依投影縮短' in l for l in fails), fails


@pytest.mark.parametrize('angle,elevation', [(0, 0), (45, 30), (225, -20), (0, 90)])
def test_absolute_aim_recovers_frame_shift_for_asymmetric_silhouette(angle, elevation):
    from body3d.check_turnaround import absolute_aim_offset

    hull = np.array([[-.7, 1.2, .03], [.8, 1.25, .04], [-.08, 0, .12],
                     [.09, .02, -.07], [.01, 1.65, -.18]])
    p, t = np.radians([angle, elevation])
    centered = hull - [0, .825, 0]
    scale = 100
    columns = np.rint(102 + scale * (centered @ [np.cos(p), 0, -np.sin(p)])).astype(int)
    rows = np.rint(96 - scale * (centered @ [-np.sin(t)*np.sin(p), np.cos(t), -np.sin(t)*np.cos(p)])).astype(int)
    mask = np.zeros((200, 200), dtype=bool)
    mask[rows, columns] = True
    np.testing.assert_allclose(absolute_aim_offset(hull, mask, scale, angle, elevation),
                               (.02, -.04), atol=.005)


def test_lighting_fixed_to_the_person(broken):
    """A flat-lit set passes; camera-following light is flagged by the coarse direction check."""
    rc, out = check(broken)
    light = [l for l in out.splitlines() if '明暗方向:' in l or '表面亮度:' in l]
    assert len(light) >= 30 and all('[PASS]' in l for l in light), [l for l in light if '[PASS]' not in l]
    f = broken / '03_090deg_left.jpg'
    im = cv2.imread(str(f)).astype(np.float32)
    m = im.min(2) < 235
    im[m] = np.clip(im[m] * 1.12, 0, 255)
    cv2.imwrite(str(f), im.astype(np.uint8), [cv2.IMWRITE_JPEG_QUALITY, 95])
    for g in broken.glob('0[1-8]_*.jpg'):
        # side light following the camera: every body part (each run of a row) darker on its image-left side
        im = cv2.imread(str(g)).astype(np.float32)
        m = im.min(2) < 235
        for y in np.flatnonzero(m.any(1)):
            x = np.flatnonzero(m[y])
            for run in np.split(x, np.flatnonzero(np.diff(x) > 1) + 1):
                if len(run) > 4:
                    im[y, run] *= np.linspace(0.70, 1.0, len(run), dtype=np.float32)[:, None]
        cv2.imwrite(str(g), np.clip(im, 0, 255).astype(np.uint8), [cv2.IMWRITE_JPEG_QUALITY, 95])
    rc, out = check(broken)
    fails = lines(out, 'FAIL')
    warnings = lines(out, 'WARN')
    assert sum('明暗方向' in l and '右側較亮' in l for l in warnings) >= 6, warnings
    assert not any('明暗方向' in l or ' 曝光:' in l or '表面亮度' in l for l in fails), fails
    assert any('主環 90°' in l and '表面亮度' in l for l in warnings), warnings


def test_region_luma_only_warns_and_compares_like_with_like(monkeypatch, tmp_path):
    """9b is a coarse screen: never FAIL. A +30° / −20° view is compared with the level view at the same azimuth,
    close-ups with the other close-ups (they show only the collar of the top), the top view only on hair and skin."""
    import csv
    from body3d import check_turnaround as checker

    def photo(name, top, hair):
        return {'name': name, 'im': {'top': top, 'hair': hair}, 'm': True}

    main = {
        0: photo('main0.jpg', (100, 500), (100, 500)),
        45: photo('main45.jpg', (100, 500), (100, 500)),
        90: photo('main90.jpg', (100, 500), (100, 499)),
        135: photo('main135.jpg', (130, 499), (100, 499)),
    }
    extras = {'el30': {
        0: photo('large.jpg', (130, 500), (65, 600)),
        45: photo('small.jpg', (135, 499), (100, 600)),
        135: photo('same_as_level.jpg', (131, 600), (100, 600)),
    }, 'head': {a: photo(f'head{a}.jpg', (150, 900), (100, 900)) for a in (0, 45, 90, 135)},
       'top': {0: photo('top.jpg', (160, 900), (101, 900))}}
    image = np.zeros((1, 1, 3), np.uint8)
    labels = np.zeros((1, 1), np.uint8)
    monkeypatch.setattr(checker, 'photo_region_lightness', lambda stats, mask, category: (image, labels, stats))
    statuses = {}
    monkeypatch.setattr(checker, 'report', lambda level, label, message: statuses.update({label: level}))
    checker.report_region_lightness(main, extras, tmp_path)
    with (tmp_path / 'region_brightness.csv').open(encoding='utf-8-sig') as file:
        rows = {(row['image'], row['region']): row for row in csv.DictReader(file)}

    assert 'FAIL' not in statuses.values() and all(r['status'] != 'FAIL' for r in rows.values())
    assert rows['large.jpg', 'top']['status'] == 'WARN' and float(rows['large.jpg', 'top']['delta_l']) == 30
    assert rows['large.jpg', 'hair']['status'] == 'WARN'
    assert rows['small.jpg', 'top']['status'] == 'WARN'
    assert rows['same_as_level.jpg', 'top']['status'] == 'PASS'            # vs level 135°, not the ring median
    assert all(rows[f'head{a}.jpg', 'top']['status'] == 'PASS' for a in (0, 45, 90, 135))
    assert rows['top.jpg', 'top']['status'] == 'NO_REFERENCE' and rows['top.jpg', 'hair']['status'] == 'PASS'
    assert statuses['large.jpg 分區亮度'] == 'WARN' and statuses['top.jpg 分區亮度'] == 'PASS'


def test_surface_luma_reports_coverage_and_boundary_sensitivity():
    from body3d.check_turnaround import SURF_P90_PASS, compare_surface_luma, surface_luma

    x, y = np.meshgrid(np.arange(32, 224, 4), np.arange(32, 224, 4))
    points = np.column_stack([x.ravel(), -y.ravel(), np.zeros(x.size)])
    normals = np.tile([0., 0., 1.], (len(points), 1))
    mask = np.zeros((256, 256), bool)
    mask[16:240, 16:240] = True
    image = np.full((256, 256, 3), 200, np.uint8)
    image[:, 128:] = 55
    base = surface_luma(points, normals, image, mask, (1, 0, 0, 0, 0))

    smaller_view = mask.copy()
    smaller_view[:, 185:] = False
    partial = surface_luma(points, normals, image, smaller_view, (1, 0, 0, 0, 0))
    raw, interior = compare_surface_luma(base, partial)
    assert raw[:2] == interior[:2] == (0.0, 0.0)

    shifted = surface_luma(points, normals, image, mask, (1, 20, 0, 0, 0))
    raw, interior = compare_surface_luma(base, shifted)
    assert raw[1] > SURF_P90_PASS and interior[1] <= SURF_P90_PASS

    darker = surface_luma(points, normals, (image * 0.8).astype(np.uint8), mask, (1, 0, 0, 0, 0))
    raw, interior = compare_surface_luma(base, darker)
    assert raw[1] > SURF_P90_PASS and interior[1] > SURF_P90_PASS

    no_samples = (base[0], np.zeros_like(base[1]), base[2])
    assert compare_surface_luma(base, no_samples) == ((None, None, 0), (None, None, 0))


def test_head_closeup_lighting_and_ears(broken):
    """10g / 10h: the clean set passes; a close-up drawn 10 % brighter warns on its lighting, and a close-up whose ear
    band is drawn 12 mm further back than in the full-body view fails the ear position"""
    rc, out = check(broken)
    e = [l for l in out.splitlines() if '特寫亮度:' in l or '耳朵位置:' in l]
    assert len(e) == 14 and all('[PASS]' in l for l in e), e
    f = broken / 'head_135deg.jpg'
    im = cv2.imread(str(f)).astype(np.float32)
    m = im.min(2) < 235
    im[m] = np.clip(im[m] * 1.10, 0, 255)
    cv2.imwrite(str(f), im.astype(np.uint8), [cv2.IMWRITE_JPEG_QUALITY, 95])
    f = broken / 'head_090deg.jpg'
    im = cv2.imread(str(f)); m = im.min(2) < 235
    top = int(np.flatnonzero(m.any(1))[0])
    from body3d.check_turnaround import HEAD_ZOOM
    s = 2048 / 1.95 * HEAD_ZOOM                         # px per metre of the close-up (spec framing)
    band = slice(top + int(0.07 * s), top + int(0.13 * s))
    im[band] = np.roll(im[band], int(0.012 * s), axis=1)
    cv2.imwrite(str(f), im, [cv2.IMWRITE_JPEG_QUALITY, 95])
    rc, out = check(broken)
    assert any('head 135° 特寫亮度' in l and '特寫比全身圖亮' in l for l in lines(out, 'WARN')), out
    assert any('head 90° 耳朵位置' in l for l in lines(out, 'FAIL')), [l for l in out.splitlines() if '耳朵' in l]
