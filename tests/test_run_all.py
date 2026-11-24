"""run_all.py 的流程控制；完整端到端測試需要 --photos（或環境變數 BODY3D_PHOTOS）"""
import os
import numpy as np
import pytest
import verify_glb as vg
from conftest import run_py


def test_version():
    rc, out = run_py('run_all.py', '--version')
    assert rc == 0 and 'body3d 2.' in out


def test_stops_when_photos_fail_check(synth_set, tmp_path):
    import shutil
    d = tmp_path / 'photos'; shutil.copytree(synth_set, d); (d / 'top.jpg').unlink()
    rc, out = run_py('run_all.py', d, tmp_path / 'out', '--only', 'check')
    assert rc == 1 and '--force' in out


def test_front_part_on_synthetic(synth_set, tmp_path):
    """合成照片跑前半段（檢查 → 相機 → 外殼 → 網格），網格高度要接近 1.65 m"""
    import trimesh
    out = tmp_path / 'out'
    for step in ('check', 'cams', 'refine', 'arms', 'round', 'legs', 'mesh'):
        rc, log = run_py('run_all.py', synth_set, out, '--only', step, timeout=3600)
        assert rc == 0, log[-2000:]
    m = trimesh.load(out / 'work' / 'body33s.ply')
    lo, hi = m.bounds
    assert abs((hi[1] - lo[1]) - 1.65) < 0.05
    assert hi[0] > 0.6 and lo[0] < -0.6          # T-pose 手臂完整
    assert m.is_watertight


@pytest.mark.slow
def test_end_to_end(request, tmp_path):
    photos = request.config.getoption('--photos')
    if not photos:
        pytest.skip('沒有給 --photos（33 張照片資料夾）')
    out = tmp_path / 'e2e'
    rc, log = run_py('run_all.py', photos, out, '--force', '--name', 'body', timeout=7200)
    assert rc == 0, log[-3000:]
    import fit_report
    rows = [r for r in fit_report.fit(str(out / 'work')) if r['kind'] == 'main']
    assert np.mean([r['extra'] for r in rows]) < 600, '腿部超出照片剪影（兩腿之間的外殼殘留）'
    for f in ('body_rigged.glb', 'body_rigged_lit.glb'):
        assert vg.verify(str(out / f), expect_unlit=f == 'body_rigged.glb', validator=False).count('FAIL') == 0


def test_legs_strict_carving_removes_gap_strip(synth_set, tmp_path):
    """兩腿之間的外殼殘留：legs 步驟之後，主環視角的腿部不能超出照片剪影"""
    import fit_report
    out = tmp_path / 'out'
    for step in ('cams', 'refine', 'arms', 'round', 'legs', 'mesh'):
        rc, log = run_py('run_all.py', synth_set, out, '--only', step, timeout=3600)
        assert rc == 0, log[-2000:]
    rows = [r for r in fit_report.fit(str(out / 'work')) if r['kind'] == 'main']
    assert np.mean([r['extra'] for r in rows]) < 600
    assert max(r['xor'] for r in rows) < 0.10


def _cams(photos, out):
    import json
    for step in ('cams', 'refine'):
        rc, log = run_py('run_all.py', photos, out, '--only', step, timeout=3600)
        assert rc == 0, log[-2000:]
    return json.load(open(out / 'work' / 'cams33.json'))


def test_perspective_distance_estimated(persp_set, tmp_path):
    """相機在 4 m 的透視照片：俯角環 8 張裡至少 6 張估出 D 在 2.5–6.5 m"""
    c = _cams(persp_set, tmp_path / 'p')
    ds = [v.get('D') for v in c.values() if v['kind'] == 'el30']
    assert sum(1 for d in ds if d and 2.5 <= d <= 6.5) >= 6, ds


def test_orthographic_set_mostly_no_perspective(synth_set, tmp_path):
    """正交照片：俯角 + 仰角 16 張最多 3 張被誤判成透視"""
    c = _cams(synth_set, tmp_path / 'o')
    assert sum(1 for v in c.values() if v['kind'] in ('el30', 'low20') and v.get('D')) <= 3
