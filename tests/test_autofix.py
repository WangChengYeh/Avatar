"""autofix (docs/SOP.md): fix a FAIL only when it is measurable and the fix is verified; otherwise stop"""
import cv2
import numpy as np

import shutil

import pytest

import autofix


@pytest.fixture
def broken(synth_set, tmp_path):
    d = tmp_path / 'set'
    shutil.copytree(synth_set, d)
    return d


def test_classify():
    assert autofix.classify('head 45° 臉部位置: 特寫的臉 8.9 mm') == ('facepos', 45)
    assert autofix.classify('head 315° 臉部位置: 7.8 mm') == ('facepos', 315)
    assert autofix.classify('head 45° 頭部朝向: 臉的轉向約 28°')[0] is None
    assert autofix.classify(' 45°: 推算約 41.8°')[0] is None


def test_needs_regeneration_stops(tmp_path):
    p = autofix.plan(str(tmp_path), ['head 45° 頭部朝向: 臉的轉向約 28°'])
    assert not p['ok'] and not p['items'] and '要重新生成' in p['reasons'][0]


def test_shifted_closeup_is_fixed_back(broken, tmp_path):
    """the perfect 45° close-up drawn 40 px lower fails 11c; autofix moves it back up and the face is within 3 mm"""
    f = broken / 'head_045deg.jpg'
    im = cv2.imread(str(f)); h, w = im.shape[:2]
    cv2.imwrite(str(f), cv2.warpAffine(im, np.float32([[1, 0, 0], [0, 1, 40]]), (w, h), borderValue=(255, 255, 255)),
                [cv2.IMWRITE_JPEG_QUALITY, 95])
    p = autofix.plan(str(broken), ['head 45° 臉部位置: 特寫的臉放回全身圖'])
    assert p['ok'], p['reasons']
    it = p['items'][0]
    assert it['photo'] == 'head_045deg.jpg' and it['dy_px'] < -25 and it['after_mm'] <= 3.0
    rec = autofix.apply(str(broken), str(tmp_path / 'fixed'), p, 1)
    assert rec[0]['round'] == 1 and 'image' not in rec[0] and len(list((tmp_path / 'fixed').glob('*.jpg'))) == 33
