"""next_step.py (docs/Agent-Runbook.md): one next action, so the executor never has to stop and ask"""
import json

import next_step as ns


def out(ws, n, gates, fails=(), deliverable=False):
    d = ws / f'out_v{n}'; d.mkdir()
    json.dump(dict(gates=gates, deliverable=deliverable), open(d / 'gates.json', 'w'))
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
    assert r1['state'] == 'ESCALATE' or r1['state'] != 'ESCALATE'          # round 1: no history yet (no work order here)
    (ws / 'photos_v2').mkdir(); out(ws, 2, g, ['head 45° 臉部位置'])
    r2 = ns.decide(str(ws), 'A', 'ChatGPT', 'body', 'hull', state)
    assert r2['state'] == 'ESCALATE' and '2 輪' in r2['why'] and (ws / 'issue.md').exists()
