"""stage 1 (docs/SOP.md): the 33 photos are always zipped; only a check without FAIL makes it the deliverable"""
import json
import zipfile

import deliver


def photos(tmp_path):
    d = tmp_path / 'photos'
    d.mkdir()
    for i, p in enumerate(deliver.PHOTOS):
        (d / p).write_bytes(b'jpeg %d' % i)
    return d


def manifest(z):
    with zipfile.ZipFile(z) as f:
        return f.namelist(), json.loads(f.read('manifest.json'))


def test_stage1_zip_has_the_33_photos_and_a_manifest(tmp_path):
    d = photos(tmp_path)
    z, ok = deliver.stage1(str(d), str(tmp_path / 'out'), 'body', (0, 5, 300), '1.39.0')
    names, m = manifest(z)
    assert ok and z.endswith('body_stage1_photos.zip') and len(deliver.PHOTOS) == 33
    assert sorted(n for n in names if n.startswith('photos/')) == sorted('photos/' + p for p in deliver.PHOTOS)
    assert m['deliverable'] and m['gates'] == {'1 照片檢查': dict(FAIL=0, WARN=5, PASS=300)}
    assert m['photo_check_version'] == '1.39.0'
    assert len(m['sha256']) == 33 and m['failures'] == [] and m['missing'] == []


def test_failing_check_is_zipped_as_FAIL_and_replaces_the_delivery(tmp_path):
    d, out = photos(tmp_path), str(tmp_path / 'out')
    good, _ = deliver.stage1(str(d), out, 'body', (0, 0, 300), '1.39.0')
    bad, ok = deliver.stage1(str(d), out, 'body', (2, 0, 300), '1.39.0', failures=['head 45° 臉部位置: 8.9 mm'])
    names, m = manifest(bad)
    assert not ok and bad.endswith('body_stage1_photos_FAIL.zip') and len(names) == 34
    assert not m['deliverable'] and m['failures'] == ['head 45° 臉部位置: 8.9 mm']
    assert not (tmp_path / 'out' / 'deliver' / 'body_stage1_photos.zip').exists()   # the old delivery is gone
    (d / 'top.jpg').unlink()
    bad, ok = deliver.stage1(str(d), out, 'body', (0, 0, 300), '1.39.0')
    assert not ok and manifest(bad)[1]['missing'] == ['top.jpg']


def test_fail_lines():
    assert deliver.fail_lines('  [PASS] a\n  [FAIL] b: 1\n[WARN] c\n  [FAIL] d') == ['b: 1', 'd']


def test_later_stage_is_FAIL_when_an_earlier_gate_failed(tmp_path):
    f = tmp_path / 'a.glb'; f.write_bytes(b'glb')
    z, ok = deliver.pack(str(tmp_path / 'out'), 'body', 3, {'a.glb': str(f)},
                         {'1 照片檢查': (2, 0, 300), '2 烘焙前檢查': (0, 1, 30), '3 GLB 驗證（unlit）': (0, 0, 21)},
                         ['head 45° 臉部位置'])
    names, m = manifest(z)
    assert not ok and z.endswith('body_stage3_models_FAIL.zip') and 'a.glb' in names
    assert m['gates']['1 照片檢查']['FAIL'] == 2 and m['failures'] == ['head 45° 臉部位置']
    z, ok = deliver.pack(str(tmp_path / 'out'), 'body', 3, {'a.glb': str(f)}, {'1 照片檢查': (0, 0, 300)})
    assert ok and z.endswith('body_stage3_models.zip') and not (tmp_path / 'out' / 'deliver' / 'body_stage3_models_FAIL.zip').exists()


def test_stopped_stage_packs_what_exists_as_FAIL(tmp_path):
    f = tmp_path / 'cams33.json'; f.write_text('{}')
    z, ok = deliver.pack(str(tmp_path / 'out'), 'body', 2, {'cams33.json': str(f), 'body33s.ply': str(tmp_path / 'no.ply')},
                         {'1 照片檢查': (0, 0, 300)}, stopped=('mesh', '步驟失敗（exit 1）'))
    names, m = manifest(z)
    assert not ok and z.endswith('body_stage2_reconstruction_FAIL.zip') and 'cams33.json' in names
    assert m['stopped'] == dict(step='mesh', reason='步驟失敗（exit 1）') and m['missing'] == ['body33s.ply']
