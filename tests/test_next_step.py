"""next_step.py (docs/Agent-Runbook.md): one next action per state; the avatar folder is
<Google Drive>/avatar/<chatgpt|gemini>/<avatar_NNN>/ with one version vNNN/{photos,output} per round"""
import json

import next_step as ns


def setup_module():
    import os
    os.environ['NEXT_STEP_OFFLINE'] = '1'          # these tests do not ask GitHub
    ns.code_changed_since = lambda commit: False   # the outputs here were made by this code


def version(ws, n, gates=None, fails=(), deliverable=False, photos=True):
    v = ws / f'v{n:03d}'; (v / 'photos').mkdir(parents=True)
    if photos:
        (v / 'photos' / '01_000deg_front.jpg').write_bytes(b'x')
    if gates is not None:
        (v / 'output').mkdir()
        json.dump(dict(gates=gates, deliverable=deliverable, code=dict(commit='abc1234')), open(v / 'output' / 'gates.json', 'w'))
        (v / 'output' / 'run_all.log').write_text(''.join(f'  [FAIL] {f}: x\n' for f in fails), encoding='utf-8')
    return v


def avatar(tmp_path):
    ws = tmp_path / 'avatar' / 'chatgpt' / 'avatar_001'; ws.mkdir(parents=True)
    return ws


G0 = {'1 照片檢查': dict(FAIL=0, WARN=0, PASS=9)}
G1 = {'1 照片檢查': dict(FAIL=1, WARN=0, PASS=9)}


def test_states(tmp_path):
    ws = avatar(tmp_path); state = {}
    r = ns.decide(str(ws), 'avatar_001', 'ChatGPT', 'avatar_001', 'hull', state)
    assert r['state'] == 'START' and 'v001/photos' in r['steps'][0]
    version(ws, 1)
    r = ns.decide(str(ws), 'avatar_001', 'ChatGPT', 'avatar_001', 'hull', state)
    assert r['state'] == 'RUN' and 'v001/output' in r['steps'][0]
    (ws / 'v001' / 'output').mkdir()
    json.dump(dict(gates=G0, deliverable=True, code=dict(commit='abc1234')), open(ws / 'v001' / 'output' / 'gates.json', 'w'))
    assert ns.decide(str(ws), 'avatar_001', 'ChatGPT', 'avatar_001', 'hull', state)['state'] == 'DONE'


def test_same_fail_twice_escalates(tmp_path):
    ws = avatar(tmp_path); state = {}
    version(ws, 1, G1, ['head 45° 臉部位置'])
    r1 = ns.decide(str(ws), 'avatar_001', 'ChatGPT', 'avatar_001', 'hull', state)
    assert r1['state'] == 'ESCALATE' and '診斷' in r1['why']                # a FAIL with no diagnosis
    version(ws, 2, G1, ['head 45° 臉部位置'])
    r2 = ns.decide(str(ws), 'avatar_001', 'ChatGPT', 'avatar_001', 'hull', state)
    issue = (ws / 'issue.md').read_text(encoding='utf-8')
    assert r2['state'] == 'ESCALATE' and '2 輪' in r2['why'] and '沒有上傳到資料 repo' in issue   # offline: no release


def test_update_when_main_is_newer(tmp_path, monkeypatch):
    monkeypatch.delenv('NEXT_STEP_OFFLINE', raising=False)
    monkeypatch.setattr(ns, 'behind_main', lambda: (2, ['abc123 photo check 1.42', 'def456 docs']))
    ws = avatar(tmp_path); version(ws, 1, G0, deliverable=True)
    r = ns.decide(str(ws), 'avatar_001', 'Gemini', 'avatar_001', 'hull', {})
    assert r['state'] == 'UPDATE' and 'git pull origin main' in r['steps'][0]
    assert 'v002/photos' in r['steps'][1] and 'v001/photos/*.jpg' in r['steps'][1] and 'v002/output' in r['steps'][2]
    monkeypatch.setattr(ns, 'behind_main', lambda: (None, 'no network'))
    st = {}
    assert ns.decide(str(ws), 'avatar_001', 'Gemini', 'avatar_001', 'hull', st)['state'] == 'DONE' and '查不到' in st['update_check']


def test_rerun_when_code_changed(tmp_path, monkeypatch):
    monkeypatch.setattr(ns, 'code_changed_since', lambda commit: commit == 'abc1234')
    ws = avatar(tmp_path); version(ws, 1, G0, deliverable=True)
    r = ns.decide(str(ws), 'avatar_001', 'ChatGPT', 'avatar_001', 'hull', {})
    assert r['state'] == 'RUN' and '舊的程式' in r['why'] and 'v002/photos' in r['steps'][0]


def test_incomplete_run_is_run_again(tmp_path):
    ws = avatar(tmp_path); version(ws, 1, {'1 照片檢查': dict(FAIL=0, WARN=2, PASS=9)})
    r = ns.decide(str(ws), 'avatar_001', 'ChatGPT', 'avatar_001', 'hull', {})
    assert r['state'] == 'RUN' and '沒有跑完' in r['why'] and 'v002' in r['steps'][0]


def test_agent_and_avatar_from_the_path(tmp_path):
    ws = avatar(tmp_path)
    assert ns.main(['--workspace', str(ws)]) == 0
    st = json.load(open(ws / 'avatar_state.json'))
    assert st['last']['state'] == 'START' and 'next_step.py --workspace' in (ws / 'next_step.md').read_text(encoding='utf-8')


def test_code_hash_ignores_commits_follows_content(tmp_path):
    """same code = same fingerprint, committed or not; an edit changes it"""
    import run_all
    (tmp_path / 'a.py').write_text('x = 1\n'); (tmp_path / 'b.json').write_text('{}')
    h1 = run_all.code_hash(str(tmp_path))
    assert run_all.code_hash(str(tmp_path)) == h1
    (tmp_path / 'a.py').write_text('x = 2\n')
    assert run_all.code_hash(str(tmp_path)) != h1


def test_issue_links_the_release(tmp_path):
    ws = avatar(tmp_path); version(ws, 1, G1, ['x'])
    state = dict(published={'v001': dict(url='https://github.com/o/r/releases/tag/chatgpt-avatar_001-v001', sig=[])})
    ns.decide(str(ws), 'avatar_001', 'ChatGPT', 'avatar_001', 'hull', state)
    issue = (ws / 'issue.md').read_text(encoding='utf-8')
    assert 'releases/tag/chatgpt-avatar_001-v001' in issue and 'data_repo.py fetch chatgpt-avatar_001-v001' in issue


def test_release_tag_from_the_path(tmp_path):
    import data_repo
    assert data_repo.tag_of(str(tmp_path / 'avatar' / 'Gemini' / 'avatar_002'), 7) == 'gemini-avatar_002-v007'


def test_wait_ends_when_the_fix_arrives(tmp_path, monkeypatch):
    """R33: Claude answers issue #65 with a merged fix and keeps the issue open until the executor reports; the
    executor's gh is not logged in. The wait ends once the code differs from the code it was registered under."""
    monkeypatch.setattr(ns, 'gh', lambda *a: None)                  # gh not logged in
    monkeypatch.setattr(ns, 'current_code', lambda: 'new')
    ws = avatar(tmp_path)
    version(ws, 1, G1, ['el30_000deg 斜角照是外殼形狀'])
    state = dict(waiting=dict(kind='issue', number=65, code='new'))
    assert ns.decide(str(ws), 'avatar_001', 'ChatGPT', 'avatar_001', 'hull', state)['state'] == 'WAITING'
    state = dict(waiting=dict(kind='issue', number=65, code='old'))
    r = ns.decide(str(ws), 'avatar_001', 'ChatGPT', 'avatar_001', 'hull', state)
    assert r['state'] != 'WAITING' and state['waiting'] is None and state['report_to']['number'] == 65
    # a wait registered before the fingerprint: the code of the last run before the wait decides
    v = ws / 'v001' / 'output'
    g = json.load(open(v / 'gates.json')); g['code']['hash'] = 'old'; json.dump(g, open(v / 'gates.json', 'w'))
    state = dict(waiting=dict(kind='issue', number=65), runs=[dict(out=str(v), fail=[])])
    r = ns.decide(str(ws), 'avatar_001', 'ChatGPT', 'avatar_001', 'hull', state)
    assert r['state'] != 'WAITING' and state['report_to']['number'] == 65


def test_escalate_without_gh_goes_through_a_person(tmp_path, monkeypatch):
    """R33-R41: the executor had no gh, so `gh issue create` could not run and it kept redrawing for 8 rounds.
    Without gh the ESCALATE steps hand the issue to a person and say not to redraw meanwhile."""
    monkeypatch.setattr(ns, 'gh', lambda *a: None)
    ws = avatar(tmp_path); state = {}
    version(ws, 1, G1, ['0° 全視角外殼覆蓋']); ns.decide(str(ws), 'avatar_001', 'ChatGPT', 'avatar_001', 'hull', state)
    version(ws, 2, G1, ['0° 全視角外殼覆蓋'])
    r = ns.decide(str(ws), 'avatar_001', 'ChatGPT', 'avatar_001', 'hull', state)
    assert r['state'] == 'ESCALATE' and '人' in r['why'] and not any(s.startswith('gh issue create') for s in r['steps'])
    assert any('不要再重畫' in s for s in r['steps']) and (ws / 'issue.md').exists() and (ws / 'issue_title.txt').exists()
