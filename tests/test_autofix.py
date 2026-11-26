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


def test_classify(monkeypatch):
    assert autofix.classify('head 45° 臉部位置: 特寫的臉 8.9 mm')[0] is None        # not proven downstream: regenerate
    monkeypatch.setattr(autofix, 'PROVEN', {'facepos'})
    assert autofix.classify('head 45° 臉部位置: 特寫的臉 8.9 mm') == ('facepos', 45)
    assert autofix.classify('head 315° 臉部位置: 7.8 mm') == ('facepos', 315)
    assert autofix.classify('head 45° 頭部朝向: 臉的轉向約 28°')[0] is None
    assert autofix.classify(' 45°: 推算約 41.8°')[0] is None


def test_needs_regeneration_stops(tmp_path):
    p = autofix.plan(str(tmp_path), ['head 45° 頭部朝向: 臉的轉向約 28°'])
    assert not p['ok'] and not p['items'] and '要重新生成' in p['reasons'][0]


def test_shifted_closeup_is_fixed_back(broken, tmp_path, monkeypatch):
    """(fixer kept, not enabled) the perfect 45° close-up drawn 40 px lower fails 11c; the fix moves it back up"""
    monkeypatch.setattr(autofix, 'PROVEN', {'facepos'})
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


def test_diagnosis_rules():
    import diagnose
    d = diagnose.diagnose_photo_fails(['head 45° 頭部朝向: 臉的轉向約 28°', 'head 315° 臉部位置: 7.8 mm', '新項目: x'])
    assert [x['owner'] for x in d] == ['照片', '照片', '照片']
    assert d[0]['confidence'] == '高' and '正前方' in d[0]['action']
    assert d[2]['confidence'] == '低'


def test_head_ring_aim_check():
    """stage 2 item: the close-up ring aimed 21 mm in front of the axis FAILs, on the axis PASSes"""
    import numpy as np
    import check_turnaround as ct

    def cams(qx, qz, s=4200.0, U=1024.0):
        out = {}
        for a in range(0, 360, 45):
            p = np.radians(a)
            out[f'head_{a:03d}deg'] = dict(phi=float(a), th=0.0, s=s, cu=U - s * (qx * np.cos(p) - qz * np.sin(p)), cv=7200.0)
        return out
    qx, qz = ct.head_ring_aim(cams(-0.0008, 0.0214))
    assert abs(qz - 0.0214) < 1e-6 and abs(qx + 0.0008) < 1e-6
    assert ct.report_head_ring_aim(cams(0.0, 0.0214)) is True        # failed
    assert ct.report_head_ring_aim(cams(0.0006, 0.0003)) is False


def test_ai_request(tmp_path):
    import ai_request
    leaves = [dict(item='全身／頭部一致性 45° 上下', owner='照片', confidence='高', cause='上下位置不同',
                   action='重畫 head_045deg', evidence=dict(dy_relative_mm=-13.8)),
              dict(item='全身／頭部一致性 45° / 315° 左右', owner='程式', confidence='高', cause='x', action='y', evidence={})]
    photos = tmp_path / 'p'; photos.mkdir()
    (photos / 'head_045deg.jpg').write_bytes(b'x')
    r = ai_request.make(str(photos), str(tmp_path / 'out'), leaves)
    text = (tmp_path / 'out' / 'ai_fix_request' / 'AI修圖單.md').read_text(encoding='utf-8')
    assert r and '## head_045deg.jpg' in text and '-13.8' in text and '程式' not in text.split('## ')[1]
    assert (tmp_path / 'out' / 'ai_fix_request' / 'photos' / 'head_045deg.jpg').exists()
    assert ai_request.make(str(photos), str(tmp_path / 'o2'), leaves[1:]) is None      # program only: no request
