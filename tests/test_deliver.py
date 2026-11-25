"""stage 1 delivery (docs/SOP.md): the 33 photos are zipped only when the photo check has no FAIL"""
import json
import zipfile

import pytest

import deliver


def photos(tmp_path):
    d = tmp_path / 'photos'
    d.mkdir()
    for i, p in enumerate(deliver.PHOTOS):
        (d / p).write_bytes(b'jpeg %d' % i)
    return d


def test_stage1_zip_has_the_33_photos_and_a_manifest(tmp_path):
    d = photos(tmp_path)
    z = deliver.stage1(str(d), str(tmp_path / 'out'), 'body', (0, 5, 300), '1.39.0')
    with zipfile.ZipFile(z) as f:
        names = f.namelist()
        m = json.loads(f.read('manifest.json'))
    assert len(deliver.PHOTOS) == 33 and sorted(n for n in names if n.startswith('photos/')) == sorted(
        'photos/' + p for p in deliver.PHOTOS)
    assert m['photo_check'] == dict(version='1.39.0', FAIL=0, WARN=5, PASS=300) and len(m['sha256']) == 33


def test_stage1_refuses_a_failing_check_or_missing_photos(tmp_path):
    d = photos(tmp_path)
    with pytest.raises(ValueError, match='未通過'):
        deliver.stage1(str(d), str(tmp_path / 'out'), 'body', (2, 0, 300), '1.39.0')
    (d / 'top.jpg').unlink()
    with pytest.raises(ValueError, match='top.jpg'):
        deliver.stage1(str(d), str(tmp_path / 'out'), 'body', (0, 0, 300), '1.39.0')
    assert not (tmp_path / 'out' / 'deliver' / 'body_stage1_photos.zip').exists()
