"""rerun from the first step whose code changed (run_all.step_fingerprints / --reuse, next_step; docs/SOP.md):
which change moves which step's fingerprint, where a run is taken up again, and when nothing is rerun at all"""
import json
import os
import shutil

import next_step as ns
import run_all

OPTS = dict(name='body', pose='tpose', template='makehuman', force=False, no_autofix=False)


def setup_module():
    os.environ['NEXT_STEP_OFFLINE'] = '1'
    ns.orders = lambda: {}


def code_copy(tmp):
    """the code tree alone, to change files in"""
    dst = tmp / 'body3d'
    for rel, p in run_all._code_files().items():
        os.makedirs(os.path.dirname(dst / rel), exist_ok=True)
        shutil.copyfile(p, dst / rel)
    return str(dst)


def some_photos(tmp):
    d = tmp / 'photos'; d.mkdir()
    (d / '01_000deg_front.jpg').write_bytes(b'a')
    return str(d)


def first_diff(a, b):
    return next((s for s in run_all.STEPS if a[s] != b[s]), None)


def record(out, fps, done, failed=None):
    os.makedirs(os.path.join(out, 'work'), exist_ok=True)
    steps = {s: dict(fp=fps[s], status='done', files=[], log_end=0, state={}) for s in done}
    if failed:
        steps[failed] = dict(fp=fps[failed], status='failed', files=[], log_end=0, state={})
    json.dump(dict(opts=OPTS, steps=steps), open(os.path.join(out, 'work', 'checkpoint.json'), 'w'))


def test_every_step_has_its_scripts():
    files = run_all._code_files()
    assert set(run_all.STEP_SCRIPTS) == set(run_all.STEPS)
    for s in run_all.STEPS:
        assert run_all.STEP_SCRIPTS[s] and all(x in files for x in run_all.STEP_SCRIPTS[s]), s
    assert run_all.SAFE_FROM[0] == 'check' and set(run_all.SAFE_FROM) <= set(run_all.STEPS)


def test_a_change_moves_the_fingerprints_from_its_own_step_on(tmp_path):
    root, ph = code_copy(tmp_path), some_photos(tmp_path)
    base = run_all.step_fingerprints(ph, OPTS, root)

    def after(rel):
        p = os.path.join(root, rel); old = open(p, encoding='utf-8').read()
        open(p, 'a', encoding='utf-8').write('\n# changed\n')
        fp = run_all.step_fingerprints(ph, OPTS, root)
        open(p, 'w', encoding='utf-8').write(old)
        return first_diff(base, fp)

    assert after('fit_report.py') == 'fit' and after('part_compare.py') == 'fit'     # the last step only (2.35.0)
    assert after('steps/bake33.py') == 'bake' and after('steps/whopaints.py') == 'bake'
    assert after('steps/silfit.py') == 'uv'               # mh33.py starts mh_fit.py, which imports it (2.37.0)
    assert after('steps/headsil33.py') == 'headreg'
    assert after('steps/facemask.py') == 'headreg'        # the head trim and the bake use it: the earlier one
    assert after('steps/camera.py') == 'cams'
    assert after('check_turnaround.py') == 'check'
    assert after('deliver.py') == 'check' and after('diagnose.py') == 'check'       # no step owns them: everything
    assert after('next_step.py') is None and after('guides.py') is None             # they make no result
    # the version line of run_all.py alone is no change; another line of it is
    p = os.path.join(root, 'run_all.py'); src = open(p, encoding='utf-8').read()
    open(p, 'w', encoding='utf-8').write(src.replace(f"__version__ = '{run_all.__version__}'", "__version__ = '9.9.9'"))
    assert first_diff(base, run_all.step_fingerprints(ph, OPTS, root)) is None
    open(p, 'w', encoding='utf-8').write(src)
    assert after('run_all.py') == 'check'
    # other photos, other options: everything
    assert first_diff(base, run_all.step_fingerprints(ph, dict(OPTS, template='hull'), root)) == 'check'
    open(os.path.join(ph, '01_000deg_front.jpg'), 'wb').write(b'b')
    assert first_diff(base, run_all.step_fingerprints(ph, OPTS, root)) == 'check'


def test_where_a_run_is_taken_up_again(tmp_path, monkeypatch):
    root, ph = code_copy(tmp_path), some_photos(tmp_path)
    fps = run_all.step_fingerprints(ph, OPTS, root); out = str(tmp_path / 'out')
    S = run_all.STEPS
    record(out, fps, S)                                   # a finished run, nothing changed
    assert run_all.still_valid(out, ph, root) and run_all.resume_point(out, ph, root) is None
    open(os.path.join(root, 'steps', 'bake33.py'), 'a').write('\n# changed\n')
    assert run_all.first_changed(out, ph, root) == ('bake', S[:S.index('bake')]) and not run_all.still_valid(out, ph, root)
    monkeypatch.setattr(run_all, 'SAFE_FROM', ('check',))
    assert run_all.resume_point(out, ph, root) == 'check'                          # only where it was measured safe
    monkeypatch.setattr(run_all, 'SAFE_FROM', ('check', 'headreg', 'bake', 'fit'))
    assert run_all.resume_point(out, ph, root) == 'bake'
    monkeypatch.setattr(run_all, 'SAFE_FROM', ('check', 'headreg', 'fit'))
    assert run_all.resume_point(out, ph, root) == 'headreg'                        # the last safe step before the change
    # a run that stopped at gate 1: a change in the bake changes nothing for it
    record(out, fps, [], failed='check')
    assert run_all.still_valid(out, ph, root)
    # ... and one stopped at the pre-bake check (inside 'bake') is touched by it
    record(out, fps, S[:S.index('bake')], failed='bake')
    assert not run_all.still_valid(out, ph, root) and run_all.resume_point(out, ph, root) == 'headreg'
    # a run killed after 'mesh', nothing changed since: go on from the last safe step, not from the start
    fps2 = run_all.step_fingerprints(ph, OPTS, root)
    record(out, fps2, S[:S.index('mesh') + 1])
    assert run_all.resume_point(out, ph, root) == 'headreg'
    # the hull flow was not measured: from the start
    json.dump(dict(opts=dict(OPTS, template='hull'), steps={s: dict(fp='x', status='done') for s in S}),
              open(os.path.join(out, 'work', 'checkpoint.json'), 'w'))
    assert run_all.resume_point(out, ph, root) == 'check'
    # no record (a version made before this): from the start
    os.remove(os.path.join(out, 'work', 'checkpoint.json'))
    assert run_all.resume_point(out, ph, root) == 'check' and not run_all.still_valid(out, ph, root)


def old_version(ws, fail=True):
    v = ws / 'v001'; (v / 'photos').mkdir(parents=True); (v / 'output' / 'work').mkdir(parents=True)
    for n in ns.ALL33:
        (v / 'photos' / f'{n}.jpg').write_bytes(b'x')
    json.dump(dict(gates={'1 照片檢查': dict(FAIL=int(fail), WARN=0, PASS=9)}, deliverable=False,
                   code=dict(commit='abc1234', hash='made-by-older-code')), open(v / 'output' / 'gates.json', 'w'))
    (v / 'output' / 'run_all.log').write_text('  [FAIL] 45° 全視角外殼覆蓋: x\n' if fail else '', encoding='utf-8')
    (v / 'output' / 'work' / 'checkpoint.json').write_text('{}')
    return v


def test_next_step_reruns_with_reuse_only_when_the_change_touches_the_run(tmp_path, monkeypatch):
    ws = tmp_path / 'avatar' / 'chatgpt' / 'avatar_001'; v = old_version(ws)
    go = lambda: ns.decide(str(ws), 'avatar_001', 'ChatGPT', 'avatar_001', None, {})
    monkeypatch.setattr(run_all, 'still_valid', lambda out, photos, root=None: False)
    r = go()
    assert r['state'] == 'RUN' and '沿用' in r['why']
    assert f'--reuse {v / "output"}' in r['steps'][1] and 'v002/output' in r['steps'][1]
    # stopped at gate 1 and the change is in a later step: the result stands, no rerun
    monkeypatch.setattr(run_all, 'still_valid', lambda out, photos, root=None: True)
    assert go()['state'] != 'RUN'
