"""check_turnaround.py：乾淨的合成照片要通過；故意弄壞的照片要被抓出來"""
import re
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


def test_flipped_copy_fails(broken):
    """把右側圖左右翻轉當成左側：第 6b 項指出翻轉複製，判 FAIL"""
    im = cv2.imread(str(broken / '07_270deg_right.jpg'))
    cv2.imwrite(str(broken / '03_090deg_left.jpg'), cv2.flip(im, 1), [cv2.IMWRITE_JPEG_QUALITY, 95])
    rc, out = check(broken)
    assert any('翻轉複製' in l and '90°' in l for l in lines(out, 'FAIL'))


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
    """曝光粗篩標記偏暗的視角（WARN）；同一表面亮差 > 6/255 判 FAIL。"""
    f = broken / 'el30_090deg.jpg'
    im = cv2.imread(str(f)).astype(np.float32)
    m = im.min(2) < 235
    im[m] *= 0.6
    cv2.imwrite(str(f), im.clip(0, 255).astype(np.uint8), [cv2.IMWRITE_JPEG_QUALITY, 95])
    rc, out = check(broken)
    assert any('90' in l and '曝光' in l for l in lines(out, 'WARN'))
    assert any('el30 90° / 主環 90° 表面亮度' in l for l in lines(out, 'FAIL'))   # 1.37.0: median > 6/255 is FAIL


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
    assert len(sil) >= 8 and sum('手' in l for l in sil) >= len(sil) // 2


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
    """第 10c 項只提醒複核（髮髻讓頭寬隨俯仰角改變，完美照片頭寬比差到 10%）：完美照片全部 PASS，透視照片由
    第 10b 項 FAIL，10c 不判 FAIL"""
    rc, out = run_py('check_turnaround.py', synth_set, '--out', tmp_path / 'a.png')
    assert len([l for l in lines(out, 'PASS') if '寬度比:' in l]) == 12
    rc, out = run_py('check_turnaround.py', persp_set, '--out', tmp_path / 'b.png')
    assert any('透視:' in l for l in lines(out, 'FAIL'))
    assert not any('寬度比:' in l for l in lines(out, 'FAIL'))


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



def test_clean_set_has_no_warnings(synth_set, tmp_path):
    """門檻是「完美照片 + 小餘裕」：完美照片連 WARN 都不能有（曝光與臉頰粗篩 1.23.0 依完美照片重新校準）"""
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


def test_face_report_fail_threshold(monkeypatch):
    import check_turnaround as checker

    monkeypatch.setattr(checker, 'face_measures',
                        lambda angle, _: (0.3 * (1 if angle == 0 else checker.FACE_BIAS['prop']),
                                          0.4 * (1 if angle == 0 else checker.FACE_BIAS['hair'] * 1.075), 140))
    heads = {angle: {'im': angle, 'm': object()} for angle in (0, 45, 315)}
    report = checker.face_check({'head': heads})
    hair = [(level, message) for level, label, message in report if '髮高比' in label]
    assert len(hair) == 2
    assert all(level == 'FAIL' and '> 7% 判 FAIL' in message for level, message in hair)


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
    assert len(e) >= 34 and all('[PASS]' in l for l in e), [l for l in e if '[PASS]' not in l]   # side views: no aim row
    _shift(broken / 'low20_045deg.jpg', dx=40)
    for g in ('el30_000deg.jpg', 'el30_180deg.jpg'):     # a whole pair framed off-centre: invisible to a ring median
        _shift(broken / g, dx=20)
    _shift(broken / 'el30_090deg.jpg', dy=-40)
    _shift(broken / 'low20_000deg.jpg', sy=1.04)
    rc, out = check(broken)
    fails = lines(out, 'FAIL')
    assert any('仰角環 45° / 225° 置中' in l for l in fails), fails
    assert any('俯角環 0° / 180° 置中' in l for l in fails), fails
    # side views have no ring aim row (1.34.0); the per-view vertical aim against the image centre catches it
    assert any('俯角環 90° 上下對準' in l for l in fails), fails
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
    assert not any('明暗方向' in l or ' 曝光:' in l for l in fails), fails
    # light following the camera: the same surface differs in brightness between views (10f, FAIL when large)
    assert any('主環 90°' in l and '表面亮度' in l for l in warnings + fails), warnings + fails


def test_region_luma_only_warns_and_compares_like_with_like(monkeypatch, tmp_path):
    """9b is a coarse screen: never FAIL. A +30° / −20° view is compared with the level view at the same azimuth,
    close-ups and the top view only on hair and skin (they show only a sliver of the top)."""
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
    assert all(rows[f'head{a}.jpg', 'top']['status'] == 'NO_REFERENCE' for a in (0, 45, 90, 135))   # only a sliver
    assert all(rows[f'head{a}.jpg', 'hair']['status'] == 'PASS' for a in (0, 45, 90, 135))
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


def test_framing_head_top_and_outline_sharpness(broken):
    """section 2 / 8b: the clean set passes; all level views drawn 8 % bigger warn on the framing fill, close-ups
    moved up warn on the head-top position, and a blurred photo warns on outline sharpness"""
    rc, out = check(broken)
    e = [l for l in out.splitlines() if '構圖佔比:' in l or '特寫頭頂位置:' in l or '輪廓清晰度:' in l]
    assert len(e) == 3 and all('[PASS]' in l for l in e), e
    for g in broken.glob('0[1-8]_*.jpg'):
        _zoom(g, 1.08)
    for g in broken.glob('head_*.jpg'):
        _shift(g, dy=-200)
    f = broken / 'el30_090deg.jpg'
    cv2.imwrite(str(f), cv2.GaussianBlur(cv2.imread(str(f)), (0, 0), 4), [cv2.IMWRITE_JPEG_QUALITY, 95])
    rc, out = check(broken)
    warns = lines(out, 'WARN') + lines(out, 'FAIL')
    assert any('構圖佔比' in l and '太緊' in l for l in warns), [l for l in out.splitlines() if '構圖佔比' in l]
    assert any('特寫頭頂位置' in l for l in warns), [l for l in out.splitlines() if '特寫頭頂' in l]
    assert any('輪廓清晰度' in l and 'el30_090deg' in l for l in warns), [l for l in out.splitlines() if '輪廓' in l]


def test_head_yaw_check(monkeypatch):
    """11b: the face must be turned by the file angle, in the close-up and the full-body view alike"""
    from body3d import check_turnaround as checker
    m = np.zeros((100, 100), bool); m[10:90, 40:60] = True
    views = {a: {'im': ('body', a), 'm': m} for a in (0, 45, 315)}
    extra = {'head': {a: {'im': ('head', a)} for a in (0, 45, 315)}}
    yaw = {('head', 0): 0, ('body', 0): 1, ('head', 45): 30, ('body', 45): 44, ('head', 315): 44, ('body', 315): 42}
    monkeypatch.setattr(checker, 'body_head_crop', lambda im, mask: im)
    monkeypatch.setattr(checker, 'face_yaw', lambda im: yaw[im])
    res = {lab: lvl for lvl, lab, _ in checker.head_yaw_check(views, extra)}
    assert res['head 45° 頭部朝向'] == 'FAIL' and res['全身 45° 頭部朝向'] == 'PASS'
    assert res['head 45° 特寫對全身朝向'] == 'FAIL'
    assert res['head 315° 頭部朝向'] == 'PASS' and res['head 315° 特寫對全身朝向'] == 'PASS'
    assert res['head 0° 頭部朝向'] == 'PASS'


def test_closeup_face_position(broken):
    """11c: the perfect set passes; the 45° close-up redrawn 40 px lower (about 10 mm at body scale) fails at 45°
    only — the camera fit cannot take a shift that only one close-up has"""
    rc, out = check(broken)
    assert len([l for l in lines(out, 'PASS') if '臉部位置' in l]) == 2
    f = broken / 'head_045deg.jpg'
    im = cv2.imread(str(f)); h, w = im.shape[:2]
    cv2.imwrite(str(f), cv2.warpAffine(im, np.float32([[1, 0, 0], [0, 1, 40]]), (w, h), borderValue=(255, 255, 255)),
                [cv2.IMWRITE_JPEG_QUALITY, 95])
    rc, out = check(broken)
    fails = [l for l in lines(out, 'FAIL') if '臉部位置' in l]
    assert len(fails) == 1 and 'head 45°' in fails[0], fails


def test_all_view_hull_coverage(broken):
    """10i: the perfect set passes; the +30° side views drawn 60 px forward (each still within its own checks:
    the 90° / 270° mirror pair keeps the axis centred) carve the body thin, and the culprits are named"""
    rc, out = check(broken)
    assert len([l for l in lines(out, 'PASS') if '全視角外殼覆蓋' in l]) == 8
    assert len([l for l in lines(out, 'PASS') if '外殼切割' in l]) == 16
    assert len([l for l in lines(out, 'PASS') if '頭部特寫鏡像' in l]) == 4              # 11e on the clean set
    for name, dx in (('el30_090deg.jpg', -60), ('el30_270deg.jpg', 60)):     # toward the face in both views
        f = broken / name
        im = cv2.imread(str(f)); h, w = im.shape[:2]
        cv2.imwrite(str(f), cv2.warpAffine(im, np.float32([[1, 0, dx], [0, 1, 0]]), (w, h), borderValue=(255, 255, 255)),
                    [cv2.IMWRITE_JPEG_QUALITY, 95])
    rc, out = check(broken)
    cut = [l for l in lines(out, 'FAIL') if '外殼切割' in l]
    assert sorted(l.split()[1] for l in cut) == ['el30_090deg', 'el30_270deg'], cut
    # 1.46: a short coverage at 90° names the tilted views at 90° and 270° (Gemini v009: its worst final views).
    # The all-view hull tolerates two misses: a third side view off lowers it
    f = broken / 'low20_090deg.jpg'
    im = cv2.imread(str(f)); h, w = im.shape[:2]
    cv2.imwrite(str(f), cv2.warpAffine(im, np.float32([[1, 0, -60], [0, 1, 0]]), (w, h), borderValue=(255, 255, 255)),
                [cv2.IMWRITE_JPEG_QUALITY, 95])
    rc, out = check(broken)
    side = [l for l in lines(out, 'FAIL') + lines(out, 'WARN') if '全視角外殼覆蓋' in l and l.split()[1] == '90°']
    assert side and 'el30_090deg' in side[0] and 'low20_270deg' in side[0], side


def _hull_render(folder, ring, a, vs=0.01):
    """what R31 sent: the level-ring hull seen by the spec camera of a tilted view, filled with a skin colour"""
    import ai_request as ar
    import check_turnaround as ct
    masks = {ang: ct.segment(cv2.imread(str(folder / (f + '.jpg'))))[0] for ang, f in ar.FULL.items()}
    s = float(np.median([np.ptp(np.flatnonzero(m.any(1))) for m in masks.values()])) / ct.SPEC_HEIGHT
    xs = np.arange(-0.95, 0.95, vs) + vs / 2; ys = np.arange(0, 1.72, vs) + vs / 2; zs = np.arange(-0.42, 0.42, vs) + vs / 2
    X, Y, Z = np.meshgrid(xs, ys, zs, indexing='ij')
    Q = np.stack([X.ravel(), Y.ravel() - ct.SPEC_HEIGHT / 2, Z.ravel()], 1)
    votes = np.zeros(len(Q), np.uint8)
    for ang, m in masks.items():
        H, W = m.shape; r, u = ct._spec_axes(ang, 0.0)
        c = np.round(W / 2 + s * (Q @ r)).astype(int); w = np.round(H / 2 - s * (Q @ u)).astype(int)
        ok = (c >= 0) & (c < W) & (w >= 0) & (w < H)
        votes += ok & (m[np.clip(w, 0, H - 1), np.clip(c, 0, W - 1)] > 0)
    P = Q[votes >= len(masks) - 1]
    H, W = masks[0].shape; r, u = ct._spec_axes(a, ct.RING_TILT[ring])
    c = np.round(W / 2 + s * (P @ r)).astype(int); w = np.round(H / 2 - s * (P @ u)).astype(int)
    ok = (c >= 0) & (c < W) & (w >= 0) & (w < H)
    sil = np.zeros((H, W), np.uint8); sil[w[ok], c[ok]] = 255
    k = 2 * int(np.ceil(s * vs)) + 1
    sil = cv2.morphologyEx(sil, cv2.MORPH_CLOSE, np.ones((k, k), np.uint8))
    im = np.full((H, W, 3), 255, np.uint8); im[sil > 0] = (150, 180, 215)
    return im


def test_tilted_view_drawn_from_hull(broken):
    """10i floor: a tilted view that is the level-ring hull itself (R31: the green outline filled in) cuts nothing;
    the perfect set cuts >= 2.2 % in every tilted view and passes"""
    rc, out = check(broken)
    assert not [l for l in lines(out, 'FAIL') + lines(out, 'WARN') if '斜角照是外殼形狀' in l]
    for name in ('el30_000deg', 'low20_135deg'):
        ring, a = name.split('_')[0], int(name.split('_')[1][:3])
        cv2.imwrite(str(broken / (name + '.jpg')), _hull_render(broken, ring, a), [cv2.IMWRITE_JPEG_QUALITY, 95])
    rc, out = check(broken)
    fails = [l for l in lines(out, 'FAIL') if '斜角照是外殼形狀' in l]
    assert sorted(l.split()[1] for l in fails) == ['el30_000deg', 'low20_135deg'], fails


def test_head_samples_do_not_depend_on_mesh_density():
    """the cheek comparison samples the head surface, not the vertices: a coarse mesh (the MakeHuman template's
    cheek) and a fine one of the same surface give about the same number of samples"""
    import check_turnaround as ct
    def plane(n):                                   # a 10 x 10 cm patch at head height, n x n vertices
        g = np.linspace(0, 0.1, n)
        X, Y = np.meshgrid(g, g)
        V = np.c_[X.ravel(), 1.45 + Y.ravel(), np.zeros(n * n)]
        N = np.tile([0.0, 0.0, 1.0], (n * n, 1))
        i = np.arange(n - 1)
        a = (i[:, None] * n + i[None, :]).ravel()
        T = np.r_[np.c_[a, a + 1, a + n], np.c_[a + 1, a + n + 1, a + n]]
        return V, N, T
    coarse = ct.head_surface_samples(*plane(4))[0]
    fine = ct.head_surface_samples(*plane(60))[0]
    assert abs(len(coarse) - len(fine)) < 0.1 * len(fine) and len(fine) > 2000


def test_tilted_arms_drawn_off(broken):
    """10i arms: a diagonal tilted view whose arms are drawn 6 cm higher than the level ring's (R33-R41: a few
    diagonal views, every other check WARN at most) FAILs as 斜角照手臂 for that view only; its body still passes"""
    rc, out = check(broken)
    assert not [l for l in lines(out, 'FAIL') + lines(out, 'WARN') if '斜角照手臂' in l]
    f = broken / 'el30_315deg.jpg'
    im = cv2.imread(str(f)); h, w = im.shape[:2]
    band = int(0.25 * w / 1.95)                           # 25 cm either side of the axis: the body stays put
    up = np.float32([[1, 0, 0], [0, 1, -int(0.06 * w / 1.95)]])
    moved = cv2.warpAffine(im, up, (w, h), borderValue=(255, 255, 255))
    out_im = moved.copy(); out_im[:, w // 2 - band:w // 2 + band] = im[:, w // 2 - band:w // 2 + band]
    cv2.imwrite(str(f), out_im, [cv2.IMWRITE_JPEG_QUALITY, 95])
    rc, out = check(broken)
    arms = [l for l in lines(out, 'FAIL') if '斜角照手臂' in l]
    assert [l.split()[1] for l in arms] == ['el30_315deg'], arms


def test_arm_reference_shows_where_the_arms_belong(broken):
    """AI 修圖單 for 斜角照手臂: the arm model (front + top views, as arms33 builds it) lies on the arms of a perfect
    tilted view, and off them once the arms are drawn 6 cm too high (R47 el30_315deg)"""
    import ai_request
    def covered(folder):
        m = ai_request.arm_mask(str(folder), 'el30_315deg')
        import check_turnaround as ct
        photo = ct.segment(cv2.imread(str(folder / 'el30_315deg.jpg')))[0] > 0
        photo = cv2.dilate(photo.astype(np.uint8), np.ones((9, 9), np.uint8)) > 0
        return (m & photo).sum() / m.sum()
    before = covered(broken)
    f = broken / 'el30_315deg.jpg'
    im = cv2.imread(str(f)); h, w = im.shape[:2]
    band = int(0.25 * w / 1.95)
    moved = cv2.warpAffine(im, np.float32([[1, 0, 0], [0, 1, -int(0.06 * w / 1.95)]]), (w, h), borderValue=(255, 255, 255))
    moved[:, w // 2 - band:w // 2 + band] = im[:, w // 2 - band:w // 2 + band]
    cv2.imwrite(str(f), moved, [cv2.IMWRITE_JPEG_QUALITY, 95])
    after = covered(broken)
    assert before > 0.7 and after < before - 0.2, (before, after)
    assert ai_request.arm_reference(str(broken), 'el30_315deg') is not None


def test_head_profile_mirror(synth_set):
    """11e: two close-ups 180° apart are one outline, mirrored (orthographic). Gemini avatar_001 v010 90/270:
    0.891, each drawn on its own; the side of the face baked in the wrong place. R54 135/315: 0.893"""
    import check_turnaround as ct
    m90 = ct.segment(cv2.imread(str(synth_set / 'head_090deg.jpg')))[0]
    m270 = ct.segment(cv2.imread(str(synth_set / 'head_270deg.jpg')))[0]
    iou, area = ct.head_profile_mirror(m90, m270)
    assert iou > 0.99 and abs(area) < 0.01, (iou, area)
    for a in (0, 45, 135):                                                          # every opposite pair
        ma, mb = (ct.segment(cv2.imread(str(synth_set / f'head_{x:03d}deg.jpg')))[0] for x in (a, a + 180))
        assert ct.head_profile_mirror(ma, mb)[0] > 0.99, a
    h, w = m270.shape
    top = int(np.flatnonzero(m270.any(1))[0])
    cx = float(np.flatnonzero(m270[top:top + 400].any(0)).mean())
    big = cv2.warpAffine(m270.astype(np.uint8), np.float32([[1.12, 0, -0.12 * cx], [0, 1.0, 0]]), (w, h))   # 12 % deeper
    iou2, _ = ct.head_profile_mirror(m90, big)
    assert iou2 < ct.PROFILE_MIRROR_FAIL, iou2
    moved = cv2.warpAffine(m270.astype(np.uint8), np.float32([[1, 0, 20], [0, 1, 0]]), (w, h))               # framing only
    assert ct.head_profile_mirror(m90, moved)[0] > 0.98


def test_feet_position_and_where_the_hull_falls_short(broken):
    """10j: the feet of every full-body photo lie inside the feet the level front, back and side photos agree on.
    10i says where the all-view hull falls short. ChatGPT avatar_001 R63-R72: ten rounds at 94 % coverage redrawing
    the tilted views' framing as the message said; the feet were off (low20_270: the sole 2 cm below the floor line)"""
    import check_turnaround as ct
    rc, out = check(broken)
    assert len([l for l in lines(out, 'PASS') if '腳的位置' in l]) == 24, [l for l in lines(out, 'WARN') if '腳的位置' in l]
    low = ('low20_000deg', 'low20_090deg', 'low20_270deg')
    for name in low:                                                     # the feet drawn 4.5 cm lower in three low views
        f = broken / (name + '.jpg')
        im = cv2.imread(str(f)); m = ct.segment(im)[0]
        bottom = int(np.flatnonzero(m.any(1))[-1]); top = bottom - 110; d = 48
        im[top + d:bottom + d + 1] = im[top:bottom + 1].copy()
        cv2.imwrite(str(f), im, [cv2.IMWRITE_JPEG_QUALITY, 95])
    rc, out = check(broken)
    warned = sorted(l.split()[1] for l in lines(out, 'WARN') if '腳的位置' in l)
    assert warned == sorted(low), warned


def _erase_toes(folder, name, ct, cm=5):
    """paint out the front `cm` of both feet in a side view (the far foot stands higher in a tilted view)"""
    f = folder / (name + '.jpg')
    im = cv2.imread(str(f)); m = ct.segment(im)[0]
    rows = np.flatnonzero(m.any(1)); bottom = int(rows[-1]); scale = (bottom - rows[0]) / ct.SPEC_HEIGHT
    top = bottom - int(0.24 * scale)
    cols = np.flatnonzero(m[top:bottom + 1].any(0)); cut = int(cm / 100 * scale)
    # seen from her left (90 deg) the toes point to the image's left, from her right to the image's right
    x0, x1 = (max(cols[0] - 4, 0), cols[0] + cut) if '_090deg' in name else (cols[-1] - cut, cols[-1] + 5)
    im[top:bottom + 8, x0:x1] = 255
    cv2.imwrite(str(f), im, [cv2.IMWRITE_JPEG_QUALITY, 95])


def test_feet_drawn_short_are_named_although_nothing_lies_outside(broken):
    """10j, 1.51.0: a foot drawn shorter than the others' lies inside the reference (nothing "outside"), and still
    carves the feet away. ChatGPT R77 (#117): el30_090deg 1.5 % outside, a PASS, while it removed 5.0 % of the feet.
    Each photo is given its share of the level ring's feet the all-view hull loses"""
    import check_turnaround as ct
    short = ('el30_090deg', 'low20_090deg', 'el30_270deg')   # three photos: the hull forgives two that disagree
    for name in short:
        _erase_toes(broken, name, ct)
    rc, out = check(broken)
    warned = {l.split()[1]: l for l in lines(out, 'WARN') if '腳的位置' in l}
    assert set(short) <= set(warned), sorted(warned)
    for name in short:
        cut_, over = (float(v) for v in re.search(r'缺 ([\d.]+)%.*?超出 ([\d.]+)%', warned[name]).groups())
        assert cut_ > 100 * ct.FOOT_CUT_WARN and over < 100 * ct.FOOT_OUT_WARN, warned[name]     # only the new number sees it
        assert '藍色的地方補上' in warned[name]


def test_feet_reference_picture_marks_what_is_missing(broken):
    """the retouch sheet's picture: blue where the other photos have a foot and this one has none"""
    import ai_request as ar, check_turnaround as ct
    ar._FEET_CUT.clear()
    before = ar.feet_cut(str(broken)).get(('el30', 90), (0, None))[0]
    assert before < ct.FOOT_CUT_WARN
    for name in ('el30_090deg', 'low20_090deg', 'el30_270deg'):
        _erase_toes(broken, name, ct)
    ar._FEET_CUT.clear()
    share, miss = ar.feet_cut(str(broken))[('el30', 90)]
    assert share > ct.FOOT_CUT_WARN and miss.any()
    pic = ar.feet_reference(str(broken), 'el30_090deg')
    blue = (pic[..., 0] > 180) & (pic[..., 2] < 110) & (pic[..., 1] > 100) & (pic[..., 1] < 200)
    assert blue.sum() > 500, 'no blue in the reference picture'
    ar._FEET_CUT.clear()


def test_where_the_hull_falls_short_decides_what_to_redraw():
    """10i: the feet alone (ChatGPT R72, 90°) -> the feet of the photos named, framing left alone; the whole figure
    (a tilted view drawn 6 cm off) -> the tilted views' framing; the arms' edges alone -> the arms"""
    import check_turnaround as ct
    bad = [('low20_270deg', 0.036, 0.09), ('el30_315deg', 0.033, 0.062)]      # (photo, feet it removes, feet outside)
    r72 = dict(zip(('頭', '手臂的高度', '軀幹', '腿', '腳'), (1.2, 0.2, 0.5, 0.5, 3.8)))
    t = ct.hull_short_advice(r72, bad, 'el30_090deg（切掉 2.0%）', '')
    assert '腳 3.8' in t and '少掉的主要是腳' in t and '相機距離與構圖不要動' in t
    assert 'low20_270deg（缺 3.6%、超出 9%）' in t and '藍色補上、紅色收掉' in t
    assert re.findall(r'(?:el30|low20)_\d{3}deg', t) == ['low20_270deg', 'el30_315deg']       # not the tilted views at 90°
    both = dict(r72, **{'手臂的高度': 2.1, '腳': 1.9})                                          # R72 at 45°: the arms too
    assert '少掉的主要是腳' in ct.hull_short_advice(both, bad) and '手臂的上下緣也少了 2.1%' in ct.hull_short_advice(both, bad)
    off = dict(zip(('頭', '手臂的高度', '軀幹', '腿', '腳'), (3.7, 0.8, 4.9, 8.0, 2.4)))       # everything short
    t = ct.hull_short_advice(off, bad, 'el30_090deg（切掉 9.0%）', 'el30_090deg（切掉 9.0%）')
    assert '少掉的主要是腳' not in t and '俯角／仰角的照片和水平環對不上' in t and 'el30_090deg' in t
    arms = dict(zip(('頭', '手臂的高度', '軀幹', '腿', '腳'), (0.4, 3.0, 0.2, 0.5, 0.3)))
    t = ct.hull_short_advice(arms, [])
    assert '少掉的主要在手臂的上下緣' in t and 'el30' not in t
    assert '俯角／仰角的照片和水平環對不上' in ct.hull_short_advice(r72, [])                    # feet short, no photo to name
