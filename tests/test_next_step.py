"""next_step.py (docs/Agent-Runbook.md): one next action, so the executor never has to stop and ask"""
import json

import next_step as ns


def setup_module():
    import os
    os.environ['NEXT_STEP_OFFLINE'] = '1'          # these tests do not ask GitHub
    ns.code_changed_since = lambda commit: False   # the outputs here were made by this code


def out(ws, n, gates, fails=(), deliverable=False):
    d = ws / f'out_v{n}'; d.mkdir()
    json.dump(dict(gates=gates, deliverable=deliverable, code=dict(commit='abc1234')), open(d / 'gates.json', 'w'))
    (d / 'run_all.log').write_text(''.join(f'  [FAIL] {f}: x\n' for f in fails), encoding='utf-8')
    return d


def test_states(tmp_path):
    ws = tmp_path / 'ws'; ws.mkdir()
    state = {}
    assert ns.decide(str(ws), 'A', 'ChatGPT', 'body', 'hull', state)['state'] == 'START'
    (ws / 'photos_v1').mkdir()
    assert ns.decide(str(ws), 'A', 'ChatGPT', 'body', 'hull', state)['state'] == 'RUN'
    out(ws, 1, {'1 照片檢查': dict(FAIL=0, WARN=0, PASS=9)}, deliverable=True)
    assert ns.decide(str(ws), 'A', 'ChatGPT', 'body', 'hull', state)['state'] == 'DONE'


def test_same_fail_twice_escalates(tmp_path):
    ws = tmp_path / 'ws'; ws.mkdir(); state = {}
    g = {'1 照片檢查': dict(FAIL=1, WARN=0, PASS=9)}
    (ws / 'photos_v1').mkdir(); out(ws, 1, g, ['head 45° 臉部位置'])
    r1 = ns.decide(str(ws), 'A', 'ChatGPT', 'body', 'hull', state)
    assert r1['state'] == 'ESCALATE' and '診斷' in r1['why']                # round 1: a FAIL with no diagnosis
    (ws / 'photos_v2').mkdir(); out(ws, 2, g, ['head 45° 臉部位置'])
    r2 = ns.decide(str(ws), 'A', 'ChatGPT', 'body', 'hull', state)
    assert r2['state'] == 'ESCALATE' and '2 輪' in r2['why'] and (ws / 'issue.md').exists()


def test_update_when_main_is_newer(tmp_path, monkeypatch):
    monkeypatch.delenv('NEXT_STEP_OFFLINE', raising=False)
    monkeypatch.setattr(ns, 'behind_main', lambda: (2, ['abc123 photo check 1.42', 'def456 docs']))
    ws = tmp_path / 'ws'; ws.mkdir(); (ws / 'photos_v1').mkdir()
    out(ws, 1, {'1 照片檢查': dict(FAIL=0, WARN=0, PASS=9)}, deliverable=True)
    r = ns.decide(str(ws), 'A', 'Gemini', 'body', 'hull', {})
    assert r['state'] == 'UPDATE' and 'git pull origin main' in r['steps'][0] and 'out_v2' in r['steps'][1]
    monkeypatch.setattr(ns, 'behind_main', lambda: (None, 'no network'))
    st = {}
    assert ns.decide(str(ws), 'A', 'Gemini', 'body', 'hull', st)['state'] == 'DONE' and '查不到' in st['update_check']


def test_rerun_when_code_changed(tmp_path, monkeypatch):
    """an output made by older code is rerun with the same photos, however the update arrived"""
    monkeypatch.setattr(ns, 'code_changed_since', lambda commit: commit == 'abc1234')
    ws = tmp_path / 'ws'; ws.mkdir(); (ws / 'photos_v1').mkdir()
    out(ws, 1, {'1 照片檢查': dict(FAIL=0, WARN=0, PASS=9)}, deliverable=True)
    r = ns.decide(str(ws), 'A', 'ChatGPT', 'body', 'hull', {})
    assert r['state'] == 'RUN' and '舊的程式' in r['why'] and 'photos_v1' in r['steps'][0] and 'out_v2' in r['steps'][0]


def test_incomplete_run_is_run_again(tmp_path):
    """only the photo check ran (no FAIL, not deliverable): run all four gates, do not escalate"""
    ws = tmp_path / 'ws'; ws.mkdir(); (ws / 'photos_v1').mkdir()
    out(ws, 1, {'1 照片檢查': dict(FAIL=0, WARN=2, PASS=9)})
    r = ns.decide(str(ws), 'A', 'ChatGPT', 'body', 'hull', {})
    assert r['state'] == 'RUN' and '沒有跑完' in r['why']
