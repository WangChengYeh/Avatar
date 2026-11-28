"""run_all.py 的流程控制；完整端到端測試需要 --photos（或環境變數 BODY3D_PHOTOS）"""
import os
import sys
import numpy as np
import pytest
import verify_glb as vg
from conftest import PKG, run_py


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
    rc, log = run_py('run_all.py', photos, out, '--force', '--name', 'body', '--template', 'hull', timeout=7200)
    assert rc == 0, log[-3000:]
    import fit_report
    rows = [r for r in fit_report.fit(str(out / 'work')) if r['kind'] == 'main']
    assert np.mean([r['extra'] for r in rows]) < 600, '腿部超出照片剪影（兩腿之間的外殼殘留）'
    # 審查第 2 項：預設 4K 烘焙的峰值記憶體要記錄下來，而且在 9.7 GiB 的環境也跑得完
    import re
    peaks = [float(x) for x in re.findall(r'STEP bake33\.py \(.*?peak memory ([\d.]+) GiB', open(out / 'run_all.log').read())]
    assert peaks and max(peaks) < 5.0, peaks
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


def _bench(photos, out, *extra):
    import json
    rc, log = run_py('camera_benchmark.py', photos, out, *extra, timeout=3600)
    assert rc == 0, log[-2000:]
    return json.load(open(out / 'camera_benchmark.json'))


def test_camera_benchmark_orthographic(synth_set, tmp_path):
    """審查第 4 項：已知相機（正交、俯角 30°、仰角 −20°）的合成照片。照片檢查通過時角度鎖在 ±3°；
    16 張俯角 / 仰角圖最多 1 張被誤判成透視"""
    r = _bench(synth_set, tmp_path / 'o')
    assert r['check_passed']
    for ring in ('el30', 'low20'):
        assert r['rings'][ring]['dphi_max'] <= 3.01 and r['rings'][ring]['dth_max'] <= 3.01, r
    assert r['rings']['el30']['n_perspective'] + r['rings']['low20']['n_perspective'] <= 1, r


def test_camera_benchmark_perspective(persp_set, tmp_path):
    """審查第 4 項：相機在 4 m 的透視照片，俯角環 8 張至少 7 張判成透視，距離誤差平均 ≤ 1 m"""
    r = _bench(persp_set, tmp_path / 'p', '--true-distance', '4.0')
    e = r['rings']['el30']
    assert e['n_perspective'] >= 7 and e['dist_err_mean'] is not None and e['dist_err_mean'] <= 1.0, r


def test_blender_script_error_fails_the_step(synth_set, tmp_path):
    """審查第 1 項：全新輸出資料夾只跑 uv（沒有網格）→ Blender 腳本出錯，CLI 要回傳非零並指出步驟"""
    rc, out = run_py('run_all.py', synth_set, tmp_path / 'fresh', '--only', 'uv', '--template', 'hull')
    assert rc != 0 and '停在步驟 uv' in out


def test_face_step_aligns_closeups(synth_set, tmp_path):
    """face33：用臉部特徵點對齊 3/4 頭部特寫；對齊後特徵點誤差中位數 < 2 mm，且不比對齊前差"""
    import re
    out = tmp_path / 'f'
    for step in ('cams', 'refine', 'arms', 'round', 'legs', 'mesh', 'headreg', 'face', 'face3d'):
        rc, log = run_py('run_all.py', synth_set, out, '--only', step, timeout=3600)
        assert rc == 0, log[-2000:]
    txt = open(out / 'run_all.log').read()
    m = re.search(r'landmark misalignment median ([\d.]+) mm -> ([\d.]+) mm', txt)
    assert m, txt[-1500:]
    before, after = float(m.group(1)), float(m.group(2))
    assert after < 2.0 and after <= before + 0.1
    # running the face step again must not apply the correction twice
    import trimesh
    v1 = trimesh.load(out / 'work' / 'body33s.ply', process=False).vertices
    rc, log = run_py('run_all.py', synth_set, out, '--only', 'face3d')
    v2 = trimesh.load(out / 'work' / 'body33s.ply', process=False).vertices
    assert rc == 0 and np.abs(v1 - v2).max() < 2e-3


@pytest.mark.parametrize(('rc', 'passed'), [(0, True), (1, False)])
def test_camera_lock_follows_check_result(monkeypatch, tmp_path, rc, passed):
    """0 FAIL locks the angles (warnings included); a FAIL run with --force uses the wide search"""
    import json
    import run_all

    def checker_run(command, cwd, log, ok_codes):
        assert '--camera-check' not in command and 3 not in ok_codes
        return rc

    status_path = tmp_path / 'out' / 'work' / 'check_status.json'
    status_path.parent.mkdir(parents=True)
    status_path.write_text('{"passed": true}')
    monkeypatch.setattr(run_all, 'run', checker_run)
    assert run_all.main([str(tmp_path), str(tmp_path / 'out'), '--only', 'check', '--force']) == 0
    assert json.loads(status_path.read_text()) == {'passed': passed}


def test_final_acceptance_thresholds():
    """#26: run_all step 18 (fit) compares the finished mesh with every full-body photo"""
    import fit_report
    rows = [dict(view=f'v{i}', xor=0.056) for i in range(24)]
    assert fit_report.acceptance(rows)[0] == 'PASS'
    rows[3]['xor'] = 0.20                                  # one view off: listed, mean still fine
    level, mean, worst = fit_report.acceptance(rows)
    assert level == 'WARN' and [v for v, _ in worst] == ['v3']
    assert fit_report.acceptance([dict(view='v', xor=0.155)] * 24)[0] == 'FAIL'     # v1220 level


def test_fit_step_is_last():
    import run_all
    assert run_all.STEPS[-2:] == ['verify', 'fit']


@pytest.mark.slow
def test_synthetic_end_to_end_needs_no_force(synth_set, tmp_path):
    """#28: perfect photos run through all 18 steps without --force: the photo check, the pre-bake head check
    (spec angles, thresholds calibrated on perfect photos) and the final fit all pass"""
    out = tmp_path / 'e2e'
    rc, log = run_py('run_all.py', synth_set, out, '--name', 'body', '--template', 'hull', timeout=7200)
    assert rc == 0, log[-3000:]
    text = open(out / 'run_all.log', errors='replace').read()
    prebake = text.split('--head-overlap-work', 1)[1].split('bake33.py', 1)[0]
    assert '[FAIL]' not in prebake, [l for l in prebake.splitlines() if '[FAIL]' in l]


def test_makehuman_template_option():
    rc, out = run_py('run_all.py', '--help')
    assert rc == 0 and '--template' in out and 'makehuman' in out and 'auto' in out


def test_template_auto_is_makehuman_when_blender_has_the_extension(tmp_path):
    """2.34.0: the MakeHuman template is the default where it can run (Blender with MPFB); without MPFB the run
    still works with the hull and says so. A resumed run keeps the template its folder was built with"""
    sys.path.insert(0, PKG)
    import run_all
    work = tmp_path / 'work'; work.mkdir()
    yes, no = (lambda blender: True), (lambda blender: False)
    assert run_all.pick_template('auto', 'blender', str(work), False, probe=yes)[0] == 'makehuman'
    t, why = run_all.pick_template('auto', 'blender', str(work), False, probe=no)
    assert t == 'hull' and 'MPFB' in why
    assert run_all.pick_template('hull', 'blender', str(work), False, probe=yes) == ('hull', '')
    assert run_all.pick_template('makehuman', 'blender', str(work), False, probe=no) == ('makehuman', '')
    (work / 'template.txt').write_text('hull\n')
    assert run_all.pick_template('auto', 'blender', str(work), True, probe=yes)[0] == 'hull'        # resuming
    assert run_all.pick_template('auto', 'blender', str(work), False, probe=yes)[0] == 'makehuman'  # from the start
    assert run_all.has_mpfb(None) is False and run_all.has_mpfb(str(tmp_path / 'no-such-blender')) is False


@pytest.mark.slow
def test_makehuman_template_on_perfect_photos(request, synth_set, tmp_path):
    """--template makehuman on perfect photos: GLB checks pass and the final fit passes without --force
    (7.3 % measured; the hull pipeline 5.0 %). Needs the MPFB extension in Blender: runs with --e2e-makehuman"""
    if not request.config.getoption('--e2e-makehuman'):
        pytest.skip('加 --e2e-makehuman 才跑（需在 Blender 安裝 MPFB，約 25 分鐘）')
    out = tmp_path / 'mh'
    rc, log = run_py('run_all.py', synth_set, out, '--name', 'body', '--template', 'makehuman', timeout=7200)
    assert rc == 0, log[-3000:]
    import json
    rep = json.load(open(out / 'fit_report.json'))
    assert rep['level'] == 'PASS' and rep['mean'] < 0.08
