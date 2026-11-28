#!/usr/bin/env python3
"""next_step.py — 執行者（ChatGPT／Gemini）每做完一步就跑這個：它只回答「下一步做什麼」（docs/Agent-Runbook.md）

    python body3d/next_step.py --workspace ~/avatar/chatgpt/avatar_001

WS 是這個 avatar 的資料夾：…/avatar/<chatgpt|gemini>/<avatar_NNN>/（agent 與 avatar 名稱從路徑來）。
每一輪是一個版本 vNNN/：vNNN/photos（33 張照片）、vNNN/output（run_all 的輸出）；狀態檔 avatar_state.json 在 WS。
重畫或重跑都開下一個版本（複製上一版的照片），不覆蓋舊的版本。
next_step 看最新的版本，讀它的驗收結果、診斷、工作單與過去每一輪的記錄，給出**一個**狀態與要照做的指令：

    UPDATE    GitHub 上的 main 有新的 SOP／程式（Claude 合併了）：git pull，用目前的照片從頭重跑
    DRAW      分段畫（先給輪廓再畫，body3d/guides.py）：這一段要畫哪幾張、照哪幾張輪廓圖，寫在 vNNN/guides/guides.md；
              畫完放進 vNNN/photos 再跑 next_step：它量這一段有沒有照著線，沒照著的點名重畫，照著了就給下一段的輪廓圖。
              六段都畫完才是 RUN。新的 avatar 一律分段畫；已經在做的 avatar 由 Claude 在 body3d/orders.json 指定
    START     （不再使用：新的 avatar 從 DRAW 第 1 段開始）
    RUN       照片有了、還沒跑；或最新的結果是舊的程式跑的（body3d/ 之後改過）：跑 run_all.py
    RETOUCH   照片的問題：照 AI 修圖單重畫 → 下一個版本 v(N+1)/photos → 跑 run_all.py
    CODE      程式的問題：照 AI 改 code 單改程式 → 開 PR 給 Claude → 等合併
    ESCALATE  處理不掉：發 GitHub issue 給 Claude（內文已寫好）→ 等
    WAITING   issue 或 PR 還沒解決：等；Claude 合併了修正（程式變了）或 issue／PR 關閉，就繼續（issue 開著也一樣，跑完回報到 issue）
    DONE      四包都是好的：做交付檢查

每個有結果的版本，執行者用 Google Drive 連結器放到雲端硬碟 avatar/<agent>/<avatar>/vNNN/（next_step.md 會寫要放哪些檔、
放到哪裡），issue 內文寫雲端硬碟的路徑。GitHub repo 是公開的：照片不上傳到 GitHub（資料 repo 的 Release 只在
AVATAR_DATA_PUBLISH=1 時上傳）。
只有 DONE 和 WAITING 可以停下來。其他狀態照指令做完，再跑一次 next_step，不要問人要不要繼續。
結果也寫在 WS/next_step.md 與 WS/avatar_state.json。
"""
import argparse
import datetime
import json
import os
import re
import shlex
import time
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
# --wait: the program waits for Claude's fix itself, in slices the sandbox does not kill. No executor documents how
# long one command may run (Codex cloud: none published, users report whole tasks cut at about 25 min; one rebuild
# command has run 7 min there and 13 min in Gemini's Antigravity), so the slice is learned on the spot: every slice
# leaves a heartbeat; a slice that never wrote "done" was killed, and the next ones stay at 70 % of what it survived.
# A slice that ends on its own makes the next one 1.5x longer, up to WAIT_MAX.
WAIT_FIRST, WAIT_MAX, WAIT_MIN, WAIT_POLL = 300, 1200, 60, 60     # seconds
STALE_RUN = 1800                       # progress.json says "running" and has not changed for this long: it was killed
STALL_ROUNDS = 2                       # this many retries in a row without progress, a FAIL item still there -> escalate
MAX_ROUNDS = 5                         # a FAIL item in this many runs in a row, progress or not -> escalate


def load(p, default=None):
    try:
        return json.load(open(p, encoding='utf-8'))
    except (OSError, ValueError):
        return default


def versions(ws):
    """[(n, path)] of WS/v001, v002 … in order"""
    out = []
    for f in os.listdir(ws) if os.path.isdir(ws) else []:
        m = re.fullmatch(r'v(\d{3,})', f)
        if m and os.path.isdir(os.path.join(ws, f)):
            out.append((int(m.group(1)), os.path.join(ws, f)))
    return sorted(out)


def vdir(ws, n):
    return os.path.join(ws, f'v{n:03d}')


def has_photos(d):
    return os.path.isdir(d) and any(f.lower().endswith('.jpg') for f in os.listdir(d))


def fail_items(out):
    """the labels of the FAIL lines of the last run (what 'the same FAIL' compares)"""
    log = os.path.join(out, 'run_all.log')
    if not os.path.exists(log):
        return []
    text = open(log, encoding='utf-8', errors='replace').read()
    # the label ends at the first colon, ASCII or full-width: the pre-bake lines use '：' (R55-R61, #79: with ':' only
    # the "label" kept the measured value, no item was ever the same in two runs, and nothing was ever stuck)
    return sorted({re.split(r'[:：]', m, 1)[0].strip() for m in re.findall(r'^\s*\[FAIL\]\s*(.*)$', text, re.M)})


def reached(gates):
    """the last gate a run got to (gates.json keys '1 照片檢查' …), None if unknown"""
    ns = [int(m.group()) for k in (gates or {}).get('gates', {}) for m in [re.match(r'\d+', str(k))] if m]
    return max(ns) if ns else None


def progressed(a, b):
    """run b made progress over run a: a later gate, or the same gate with fewer FAIL items. Stopping at an earlier
    gate is not progress, however few items fail there (gate 2 with 3 FAILs -> gate 1 with 1)"""
    ra, rb = a.get('reached'), b.get('reached')
    if ra is not None and rb is not None and ra != rb:
        return rb > ra
    return len(b.get('fail', [])) < len(a.get('fail', []))


def stuck(runs):
    """runs (oldest first, one code) -> the FAIL items that are stuck (empty: none): in every run of the last
    MAX_ROUNDS, or in every run of the last STALL_ROUNDS retries, none of which made progress"""
    def common(rs):
        s = set(rs[0].get('fail', []))
        for r in rs[1:]:
            s &= set(r.get('fail', []))
        return s
    if len(runs) >= MAX_ROUNDS and common(runs[-MAX_ROUNDS:]):
        return common(runs[-MAX_ROUNDS:])
    last = runs[-(STALL_ROUNDS + 1):]
    if len(last) == STALL_ROUNDS + 1 and not any(progressed(a, b) for a, b in zip(last, last[1:])):
        return common(last)
    return set()


def gh(*args):
    try:
        r = subprocess.run(['gh', *args], capture_output=True, text=True, timeout=60, cwd=REPO)
        return r.stdout.strip() if r.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def behind_main():
    """(commits the local checkout is behind origin/main, the new commits' subjects) after a git fetch;
    (None, error) when GitHub cannot be reached — next_step then goes on with what it has"""
    try:
        f = subprocess.run(['git', '-C', REPO, 'fetch', '--quiet', 'origin', 'main'], capture_output=True, text=True,
                           timeout=120)
        if f.returncode != 0:
            return None, (f.stderr or 'git fetch 失敗').strip().splitlines()[-1]
        n = subprocess.run(['git', '-C', REPO, 'rev-list', '--count', 'HEAD..origin/main'], capture_output=True,
                           text=True).stdout.strip()
        log = subprocess.run(['git', '-C', REPO, 'log', '--format=%h %s', 'HEAD..origin/main', '-n', '8'],
                             capture_output=True, text=True).stdout.strip().splitlines()
        return int(n or 0), log
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        return None, str(error)


def code_changed_since(commit):
    """True when body3d/ differs between the commit that made an output and this checkout (code updated since);
    None when that cannot be told (no commit recorded, commit unknown here)"""
    if not commit:
        return None
    try:
        r = subprocess.run(['git', '-C', REPO, 'diff', '--quiet', commit, '--', 'body3d'], capture_output=True,
                           timeout=60)
        return {0: False, 1: True}.get(r.returncode)
    except (OSError, subprocess.SubprocessError):
        return None


ALL33 = (['01_000deg_front', '02_045deg_front_left', '03_090deg_left', '04_135deg_back_left', '05_180deg_back',
          '06_225deg_back_right', '07_270deg_right', '08_315deg_front_right', 'top']
         + [f'{r}_{a:03d}deg' for r in ('el30', 'low20', 'head') for a in range(0, 360, 45)])    # = guides.ALL, without cv2


def orders():
    """what Claude tells an avatar to do, by 'agent/avatar' (body3d/orders.json, read after every pull). The executors
    act on next_step only, not on issue comments (docs/Handoff.md), so an instruction for one avatar goes here.
    {"do": "staged", "id": ..., "issue": N, "why": ...}: redraw in stages, keeping every photo that follows its
    lines (guides.py finds the first stage that does not)"""
    return load(os.path.join(HERE, 'orders.json'), {}) or {}


def draw_step(ws, n, photos, me):
    """the DRAW state for version n, or None when its six stages are drawn and measured"""
    sys.path.insert(0, HERE)
    import guides
    gdir = os.path.join(vdir(ws, n), 'guides')
    st = guides.make(photos, gdir, log_path=os.path.join(ws, 'stage_log.json'))    # one log for the avatar
    if not st['stage']:
        return None
    redo = st['redo']
    bad = {}
    for r in st['results']:
        if r['level'] == 'FAIL' and r['photo'] in redo:
            bad.setdefault(r['photo'], []).append(r['item'])
    why = f'分段畫，第 {st["stage"]} 段（共 {len(guides.STAGES)} 段）：{st["title"]}'
    if redo:
        why += '。沒有照著線、要重畫的：' + '；'.join(f'{k}（{"、".join(v)}）' for k, v in sorted(bad.items()))
    if st['waived']:
        why += f'。連續 {guides.MAX_TRIES} 次沒照著線、先放行的：{"、".join(st["waived"])}'
    front = os.path.join(photos, guides.FULL[0] + '.jpg')
    give = (f'把 {st["guides"]}、同一個資料夾裡的輪廓圖（{len(st["files"])} 張 *_guide.png）和正面照 {front} 交給生圖 AI，'
            if st['files'] else f'照 {st["guides"]} ')
    return dict(state='DRAW', why=why, steps=[
        give + f'畫這 {len(st["draw"])} 張：{"、".join(st["draw"])}',
        f'把畫好的照片（檔名 <名稱>.jpg，照片上不能留下輪廓圖的線）放進 {photos}' + ('（覆蓋沒照著線的那幾張）' if redo else ''),
        me])


def run_cmd(photos, out, name, template):
    t = f' --template {template}' if template not in (None, 'auto') else ''
    q = shlex.quote
    return f'{q(sys.executable)} {q(os.path.join(REPO, "body3d", "run_all.py"))} {q(photos)} {q(out)} --name {q(name)}{t}'


def next_version_steps(ws, n, photos, name, template, why=''):
    """copy this round's photos into a new version v(n) and run it there (a rerun never overwrites a version)"""
    new = vdir(ws, n)
    q = shlex.quote                                    # paths may have spaces
    return [f'mkdir -p {q(new + "/photos")} && cp {q(photos)}/*.jpg {q(new + "/photos")}/' + (f'   # {why}' if why else ''),
            run_cmd(f'{new}/photos', f'{new}/output', name, template)]


def auto_publish(ws, state):
    """upload the latest version with results to the data repo (once per change of its results); the release URL
    goes into the state and the issue body. Never blocks the next step: a failure is recorded and shown."""
    # opt-in only: the data repo is public and the photos are of a person; results are exchanged on the Drive
    if (state.get('offline') or os.environ.get('NEXT_STEP_OFFLINE') or os.environ.get('NEXT_STEP_NO_PUBLISH')
            or os.environ.get('AVATAR_DATA_PUBLISH') != '1'):
        state.pop('publish_error', None)               # not publishing: an old failure is not news (Gemini: "v003 沒有上傳"
        return                                         # in every next_step.md since v003)
    vs = versions(ws)
    if not vs:
        return
    n, cur = vs[-1]
    out = os.path.join(cur, 'output')
    g = os.path.join(out, 'gates.json')
    prog = load(os.path.join(out, 'progress.json'), {}) or {}
    if not os.path.exists(g) or prog.get('state') == 'running':
        return
    d = os.path.join(out, 'deliver')
    sig = [os.path.getmtime(g)] + sorted(os.listdir(d)) if os.path.isdir(d) else [os.path.getmtime(g)]
    pub = state.setdefault('published', {})
    key = os.path.basename(cur)
    if pub.get(key, {}).get('sig') == sig:
        return
    try:
        import data_repo
        pub[key] = dict(url=data_repo.publish(ws, n), sig=sig)
        state.pop('publish_error', None)
    except Exception as error:                         # no gh / no permission / offline: say so, go on
        state['publish_error'] = f'{key} 沒有上傳到資料 repo：{error}'


def wait_budget(state, hb_path, fixed=None):
    """seconds this wait slice may take, from what the earlier slices did (state['wait'], the heartbeat file)"""
    w = state.setdefault('wait', {})
    hb = load(hb_path, None)
    if hb and not hb.get('done'):                      # the last slice was killed: the sandbox's limit, measured
        survived = max(0.0, hb.get('beat', hb['started']) - hb['started'])
        if survived >= WAIT_MIN:                       # sooner than that is a person stopping it, not a time limit
            w['killed_after'] = round(min(survived, w.get('killed_after', survived)), 1)
    elif hb and hb.get('full') and not w.get('killed_after') and not fixed:
        w['budget'] = min(WAIT_MAX, round(1.5 * hb.get('budget', WAIT_FIRST)))
    budget = fixed if fixed else w.get('budget', WAIT_FIRST)
    if w.get('killed_after') is not None:
        budget = min(budget, 0.7 * w['killed_after'])
    budget = int(max(WAIT_MIN, min(WAIT_MAX, budget)))
    if not fixed:                                      # --wait N is for this call: what was learned stays
        w['budget'] = budget
    return budget


def wait_slice(check, budget, hb_path, poll=WAIT_POLL, clock=time.time, sleep=time.sleep, say=print):
    """call check() every `poll` seconds until it no longer says WAITING or `budget` seconds are over; returns
    (the last result, seconds waited). The heartbeat file says how far this slice got if the sandbox kills it"""
    t0 = clock()
    hb = dict(started=t0, beat=t0, budget=budget, done=False, full=False)

    def beat(**kw):
        hb.update(beat=clock(), **kw)
        tmp = hb_path + '.tmp'
        json.dump(hb, open(tmp, 'w')); os.replace(tmp, hb_path)
    beat()
    r = check()
    while r['state'] == 'WAITING' and budget - (clock() - t0) >= 5:
        end = clock() + min(poll, budget - (clock() - t0))
        while clock() < end:
            sleep(min(10, max(0.0, end - clock()))); beat()
        say(f'（等了 {round((clock() - t0) / 60, 1)} 分鐘，再檢查一次 GitHub…）', flush=True)
        r = check()
    beat(done=True, full=r['state'] == 'WAITING')
    return r, clock() - t0


def current_code():
    """the fingerprint of all of body3d/, next_step itself included: a wait on Claude ends when any of it changes"""
    sys.path.insert(0, HERE)
    import run_all
    return run_all.code_hash(control=True)


def wait_answered(w, state):
    """Claude answers an escalation by merging a fix; the issue itself stays open until the executor reports the
    rerun (docs/Project-Loop.md). So a wait is over once the code here differs from the code it was registered
    under, whatever GitHub says (R33: issue #65 open by design, gh not logged in -> WAITING forever).
    Waits registered before this rule carry no fingerprint: use the code of the last run before the wait."""
    since = w.get('code')
    if not since and state.get('runs'):
        since = (load(os.path.join(state['runs'][-1]['out'], 'gates.json'), {}) or {}).get('code', {}).get('hash')
    return bool(since) and since != current_code()


def agent_label(agent):
    """the GitHub label that says which agent did it (docs/Project-Loop.md#誰做的)"""
    return 'agent:' + agent.lower()


def drive_dir(ws, n):
    """where this version's results go on the Drive: avatar/<agent>/<avatar>/vNNN (docs/SOP.md)"""
    ws = os.path.abspath(ws)
    return f'avatar/{os.path.basename(os.path.dirname(ws)).lower()}/{os.path.basename(ws)}/v{n:03d}'


def drive_files(ws):
    """the latest version's files to put on the Drive, and where"""
    vs = versions(ws)
    if not vs:
        return None
    n, cur = vs[-1]
    out = os.path.join(cur, 'output')
    if not os.path.exists(os.path.join(out, 'gates.json')):
        return None
    d = os.path.join(out, 'deliver')
    files = sorted(f for f in os.listdir(d) if f.endswith('.zip')) if os.path.isdir(d) else []
    # the unlit GLB on its own too, so anyone can download a version's model from the Drive without unpacking the
    # 10-28 MB stage 3 pack. Its name carries the version: every version of an avatar makes the same
    # <name>_rigged.glb, and downloaded side by side they could not be told apart. A copy named
    # <name>_vNNN_rigged.glb is made next to the packs (output/deliver) for the upload.
    glb = []
    for f in sorted(f for f in os.listdir(out) if f.endswith('_rigged.glb')):
        named = f'{f[:-len("_rigged.glb")]}_v{n:03d}_rigged.glb'
        src, dst = os.path.join(out, f), os.path.join(d, named)
        os.makedirs(d, exist_ok=True)
        if not os.path.exists(dst) or os.path.getmtime(dst) < os.path.getmtime(src):
            shutil.copy2(src, dst)
        glb.append(named)
    return drive_dir(ws, n), files + glb + ['gates.json', 'next_step.md']


def decide(ws, avatar, agent, name, template, state):
    vs = versions(ws)
    cn, cur = vs[-1] if vs else (0, None)
    photos = os.path.join(cur, 'photos') if cur and has_photos(os.path.join(cur, 'photos')) else None
    out = os.path.join(cur, 'output') if cur and os.path.isdir(os.path.join(cur, 'output')) else None
    q = shlex.quote
    me = f'{q(sys.executable)} {q(os.path.join(REPO, "body3d", "next_step.py"))} --workspace {q(ws)}'   # the same Python, with the packages
    # a newer SOP / program on GitHub (Claude merged something): pull it first, then run again under it
    if not state.get('offline') and not os.environ.get('NEXT_STEP_OFFLINE'):
        n_behind, info = behind_main()
        if n_behind is None:
            state['update_check'] = f'查不到 GitHub 上的 main（{info}）：先用本機的版本繼續'
        elif n_behind > 0:
            w = state.get('waiting')
            if w and gh(w['kind'], 'view', str(w['number']), '--json', 'state', '--jq', '.state') in ('CLOSED', 'MERGED'):
                state['waiting'] = None                    # Claude's fix is in this update: one rerun covers both
            # pull, then ask again: whether the photos must be rerun is decided after the pull, from the code that
            # makes the results (run_all.code_hash). Every merge used to force a rerun in a new version, docs and
            # next_step-only changes included (Gemini v014 -> v015, ChatGPT v061 -> v062: the same photos, the same
            # numbers).
            steps = [f'cd {shlex.quote(REPO)} && git pull origin main   # {n_behind} 個新的 commit：' + '；'.join(info[:3]), me]
            return dict(state='UPDATE', why=f'GitHub 上的 main 比本機新 {n_behind} 個 commit（Claude 合併了新的 SOP／程式）：'
                                            '先 pull，再跑一次 next_step；重建或檢查的程式有變才需要重跑',
                        steps=steps)
    if not photos:
        target = cur if cur and not out else vdir(ws, cn + 1)
        tn = int(os.path.basename(target)[1:])
        # an empty newest version of an avatar that has photos (the copy into it did not happen): copy them, never
        # start over. Starting over would ask for a new front photo, and the front photo is who this person is
        prev = [d for _, d in vs[:-1] if has_photos(os.path.join(d, 'photos'))] if cur and not out else []
        if prev:
            return dict(state='DRAW', why=f'{os.path.basename(target)} 還沒有照片：先把 {os.path.basename(prev[-1])} 的照片複製過來'
                                          '（不要重畫正面照：它是這個人物的定義）',
                        steps=[f'mkdir -p {q(target + "/photos")} && cp {q(prev[-1] + "/photos")}/*.jpg {q(target + "/photos")}/', me])
        # a new avatar is drawn in stages (guides.py): the front photo first, every later photo from the ones before
        state['staged'] = dict(order=(state.get('staged') or {}).get('order'), version=tn)
        os.makedirs(os.path.join(target, 'photos'), exist_ok=True)
        return draw_step(ws, tn, os.path.join(target, 'photos'), me)
    # Claude's order for this avatar: redraw in stages. A new version with every photo copied; guides.py then names
    # the first stage whose photos do not follow their lines
    order = orders().get(f'{agent.lower()}/{avatar}')
    sg = state.get('staged') or {}
    if order and order.get('do') == 'staged' and (sg.get('order') != order['id'] or sg.get('version', 0) > cn):
        new = vdir(ws, cn + 1)
        state['staged'] = dict(order=order['id'], version=cn + 1)
        if order.get('issue'):
            state['waiting'] = None
            state['report_to'] = dict(kind='issue', number=order['issue'])
        return dict(state='DRAW', why='Claude 把這個 avatar 改成分段畫（先給輪廓再畫）：' + order.get('why', '')
                                      + f' 先把目前的照片複製到 {os.path.basename(new)}，下一步會告訴你哪幾張要照輪廓圖重畫',
                    steps=[f'mkdir -p {q(new + "/photos")} && cp {q(photos)}/*.jpg {q(new + "/photos")}/', me])
    # waiting on Claude: an issue or a PR
    w = state.get('waiting')
    if w:
        kind, num = w['kind'], w['number']
        st = gh(kind, 'view', str(num), '--json', 'state', '--jq', '.state')
        if st not in ('CLOSED', 'MERGED') and wait_answered(w, state):
            state['waiting'] = None                    # the fix is here: go on under it, report on the issue
            state['report_to'] = dict(kind=kind, number=num)
            w = None
    if w:
        if st in ('CLOSED', 'MERGED'):
            state['waiting'] = None
            return dict(state='RUN', why=f'{kind} #{num} 已解決（{st}）：拿新的 SOP／程式從頭重跑', steps=[
                f'cd {shlex.quote(REPO)} && git pull origin main'] + next_version_steps(ws, cn + 1, photos, name, template) + [me])
        return dict(state='WAITING', why=f'等 Claude 處理 {kind} #{num}（目前 {st or "查不到狀態：檢查 gh 是否登入"}）', claude=True, steps=[
            f'{me} --wait   # 程式自己等：每分鐘檢查一次 GitHub，Claude 的修正一合併就回來告訴你下一步；'
            '等不到也會在沙盒逾時之前回來，再跑一次同一個指令繼續等'])
    if not out or not (os.path.exists(os.path.join(out, 'gates.json')) or os.path.exists(os.path.join(out, 'progress.json'))):
        # drawn in stages: this version is run only when its six stages are drawn and follow their lines
        n_spec = sum(os.path.isfile(os.path.join(photos, n_ + '.jpg')) for n_ in ALL33)   # the 33 of the spec, by name
        if state.get('staged') or n_spec < 33:
            state.setdefault('staged', dict(order=None, version=cn))
            d = draw_step(ws, cn, photos, me)
            if d:
                return d
        return dict(state='RUN', why=f'{os.path.basename(cur)} 的照片還沒跑過', steps=[
            run_cmd(photos, os.path.join(cur, 'output'), name, template), me])
    gates = load(os.path.join(out, 'gates.json'), {})
    progress = load(os.path.join(out, 'progress.json'), {})
    diagnosis = load(os.path.join(out, 'diagnosis.json'), []) or []
    if progress.get('state') == 'running':
        # run_all saves progress.json at the start and end of every step (the longest takes a few minutes). One that
        # still says "running" long after was killed with its sandbox: nothing is running, and waiting never ends
        idle = time.time() - os.path.getmtime(os.path.join(out, 'progress.json'))
        if idle > STALE_RUN:
            return dict(state='RUN', why=f'{os.path.basename(cur)} 的重建被中斷了（progress.json 已經 {round(idle / 60)} 分鐘沒有更新，'
                                         '沒有東西在跑）：用同一組照片在新的版本從頭重跑',
                        steps=next_version_steps(ws, cn + 1, photos, name, template) + [me])
        return dict(state='WAITING', why=f'{os.path.basename(cur)} 還在跑', steps=[f'等它跑完，再跑：{me}'])
    # results made by older code are not results: rerun the same photos with the code of this checkout
    made_by = (gates.get('code') or progress.get('code') or {})
    if made_by.get('hash'):                            # the code's own fingerprint: uncommitted edits count as they are
        sys.path.insert(0, HERE)
        import run_all
        changed = made_by['hash'] != run_all.code_hash()
    else:
        changed = code_changed_since(made_by.get('commit'))
    if changed or not (made_by.get('hash') or made_by.get('commit')):
        why = (f'{os.path.basename(cur)} 是舊的程式跑的（commit {str(made_by.get("commit"))[:7]}，之後 body3d/ 改過）'
               if changed else f'{os.path.basename(cur)} 沒有記錄是哪一版程式跑的')
        return dict(state='RUN', why=why + '：用目前的程式、同一組照片重跑',
                    steps=next_version_steps(ws, cn + 1, photos, name, template) + [me])
    if gates.get('deliverable'):
        return dict(state='DONE', why=f'{os.path.basename(cur)}：四道關卡全部 0 FAIL，四包都是好的', steps=[
            '照 docs/SOP.md#可以交付了嗎 做交付檢查：逐項看需複核（WARN）記在 Issue；在 Yoga2 匯入 GLB 截圖（站姿、抬手）',
            f'交付：{os.path.join(out, "deliver")} 四包 + {os.path.join(out, "client")}'])
    g_ = gates.get('gates', {})
    if not any(v['FAIL'] for v in g_.values()) and progress.get('state') != 'stopped':
        # nothing failed but not deliverable: the four gates did not all run (e.g. --only / --from): run it all
        return dict(state='RUN', why=f'{os.path.basename(cur)} 沒有跑完四道關卡（沒有 FAIL，但也還不能交付）：從頭完整跑',
                    steps=next_version_steps(ws, cn + 1, photos, name, template) + [me])
    # the same FAIL item, no progress -> escalate (the executor does not decide this). A retry makes progress when it
    # fails fewer items or gets to a later gate: a small redraw that fixes some photos keeps going (R52: ChatGPT
    # escalated after fixing 5 of 7). Only runs of the same code count: after an update the new SOP gets its own
    # tries (R48: the same photos rerun on new code, with a new arm reference, escalated before anyone redrew with it)
    import escalate
    history = state.setdefault('runs', [])
    items = fail_items(out)
    code = made_by.get('hash') or made_by.get('commit')
    if not history or history[-1].get('out') != out:
        history.append(dict(out=out, photos=photos, fail=items, code=code, reached=reached(gates),
                            at=datetime.datetime.now().astimezone().isoformat(timespec='seconds')))
    repeated = stuck([r for r in history if r.get('code') == code])
    reason = escalate.REASONS[1] if repeated else None
    reason = reason or escalate.auto_reason(diagnosis, progress, gates)
    first = sorted(diagnosis, key=lambda d: d.get('order', 99))[0] if diagnosis else None
    if not reason and first and first['owner'] == '照片' and os.path.exists(os.path.join(out, 'ai_fix_request', 'AI修圖單.md')):
        new = vdir(ws, cn + 1)
        req = os.path.join(out, 'ai_fix_request')
        redo = sorted(os.listdir(os.path.join(req, 'photos')))
        return dict(state='RETOUCH', why=f'照片的問題（{first["item"]}，信心{first["confidence"]}）', steps=[
            f'把 {os.path.join(req, "AI修圖單.md")} 與 {req}/photos、{req}/reference 交給生圖 AI，照單重畫：{"、".join(redo)}',
            f'mkdir -p {q(new + "/photos")} && cp {q(photos)}/*.jpg {q(new + "/photos")}/   # 先複製整組，再用重畫好的覆蓋那 {len(redo)} 張',
            f'把重畫好的照片（同檔名）放進 {new}/photos',
            run_cmd(f'{new}/photos', f'{new}/output', name, template), me])
    if not reason and first and first['owner'] != '照片' and os.path.exists(os.path.join(out, 'ai_code_request', 'AI改code單.md')):
        return dict(state='CODE', why=f'程式的問題（{first["item"]}，信心{first["confidence"]}）', steps=[
            f'照 {os.path.join(out, "ai_code_request", "AI改code單.md")} 在 {REPO} 開分支、補檢查、改程式、驗收（兩組完美照片全部通過）',
            '開 PR 給 Claude review（用 .github/pull_request_template.md），記下 PR 編號 N',
            f'{me} --waiting-pr N   # 登記等待；合併後 next_step 會叫你 pull、重跑'])
    # escalate: write the issue body
    reason = reason or escalate.REASONS[0]
    tried = '；'.join(f'{os.path.basename(os.path.dirname(r["out"]))}：{len(r.get("fail", []))} 項 FAIL' for r in history[-4:])
    body = escalate.body(out, agent, avatar, tried=f'最近幾輪：{tried}。重複出現的 FAIL：{"、".join(sorted(repeated)) or "無"}',
                         reason=reason)
    body = (f'> 由 **{agent}** 發（執行者，{avatar}）\n\n'
            f'**資料**：雲端硬碟 `{drive_dir(ws, cn)}`（照片與結果包，用 Google Drive 連結器讀）\n\n' + body)
    issue = os.path.join(ws, 'issue.md')
    open(issue, 'w', encoding='utf-8').write(body)
    title = f'[{agent}] [SOP] {avatar}：{reason}'       # who did it, visible in every list (docs/Project-Loop.md#誰做的)
    # everyone has GitHub (docs/Project-Loop.md#三個角色怎麼操作): the executor posts it itself, with gh or its
    # GitHub connector (R33-R47: no gh, the step could not run, the issue waited for a person)
    open(os.path.join(ws, 'issue_title.txt'), 'w', encoding='utf-8').write(title)
    return dict(state='ESCALATE', why=reason, steps=[
        f'gh issue create --repo WangChengYeh/Avatar --title {q(title)} --body-file {q(issue)} --label {q(agent_label(agent))} --label sop-escalation   # 記下 issue 編號 N',
        f'（沒有 gh 時用 GitHub 連結器在 WangChengYeh/Avatar 開 issue：標題是 {os.path.join(ws, "issue_title.txt")} 的內容，內文是 {issue}，加 label {agent_label(agent)}、sop-escalation；記下編號 N）',
        f'確認這一版的結果包已在雲端硬碟 {drive_dir(ws, cn)}（issue 內文寫了路徑；照片不要附在公開的 issue）',
        f'{me} --waiting-issue N   # 登記等待；Claude 關閉 issue 後 next_step 會叫你 pull、重跑'])


def main(argv=None):
    ap = argparse.ArgumentParser(description='下一步做什麼')
    ap.add_argument('--workspace', required=True, help='這個 avatar 的資料夾：…/avatar/<chatgpt|gemini>/<avatar_NNN>')
    ap.add_argument('--avatar', help='預設：資料夾名稱（avatar_NNN）')
    ap.add_argument('--agent', help='預設：上一層資料夾名稱（chatgpt／gemini）')
    ap.add_argument('--name', help='GLB 名稱，預設：avatar 名稱')
    ap.add_argument('--template', default=None, choices=['makehuman', 'hull', 'auto'],
                    help='不寫就是 run_all 的預設：MakeHuman 模板（沒有 MakeHuman 擴充時 run_all 會自動安裝，裝不了才退回外殼）')
    ap.add_argument('--waiting-issue', type=int); ap.add_argument('--waiting-pr', type=int)
    ap.add_argument('--wait', type=float, nargs='?', const=0, default=None, metavar='分鐘',
                    help='WAITING（等 Claude）時不馬上結束：每分鐘檢查一次，最多等這麼久就回來；不給數字就自己學沙盒的時限')
    a = ap.parse_args(argv)
    ws = os.path.abspath(a.workspace); os.makedirs(ws, exist_ok=True)
    a.avatar = a.avatar or os.path.basename(ws)
    a.agent = a.agent or {'chatgpt': 'ChatGPT', 'gemini': 'Gemini'}.get(os.path.basename(os.path.dirname(ws)).lower(),
                                                                       os.path.basename(os.path.dirname(ws)))
    a.name = a.name or a.avatar
    sp = os.path.join(ws, 'avatar_state.json')
    state = load(sp, {}) or {}
    if a.waiting_issue or a.waiting_pr:
        state['waiting'] = dict(kind='issue' if a.waiting_issue else 'pr', number=a.waiting_issue or a.waiting_pr,
                                code=current_code())   # the wait is over once the code changes (wait_answered)
        state.pop('report_to', None)
    auto_publish(ws, state)
    waited = None
    if a.wait is not None:
        hb_path = os.path.join(ws, 'wait_heartbeat.json')
        budget = wait_budget(state, hb_path, fixed=60 * a.wait if a.wait else None)
        json.dump(state, open(sp, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        r, waited = wait_slice(lambda: decide(ws, a.avatar, a.agent, a.name, a.template, state), budget, hb_path)
    else:
        r = decide(ws, a.avatar, a.agent, a.name, a.template, state)
    on_claude = bool(r.pop('claude', False))
    state['last'] = dict(r, at=datetime.datetime.now().astimezone().isoformat(timespec='seconds'))
    rt = state.get('report_to')                         # still shown on DONE (the last report), then cleared
    if rt and r['state'] == 'DONE':
        state.pop('report_to', None)
    json.dump(state, open(sp, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    stop = r['state'] in ('DONE', 'WAITING') and not on_claude
    text = [f'# 下一步：{r["state"]}', '', f'原因：{r["why"]}', ''] + [f'{i}. `{s}`' if s.startswith(('python', 'gh ', 'mkdir', 'cd ', '/', "'"))
                                                                   else f'{i}. {s}' for i, s in enumerate(r['steps'], 1)]
    if rt:
        text += ['', f'**回報**：Claude 已經針對 {rt["kind"]} #{rt["number"]} 更新了 SOP／程式（issue 可能還開著，'
                     f'等你回報）。照上面繼續；這一輪跑完，把結果和 Claude 在 issue 留言要的數字回覆到 #{rt["number"]}：'
                     f'`gh issue comment {rt["number"]} --repo WangChengYeh/Avatar --body-file <檔案>`（或用 GitHub 連結器留言）。'
                     f'留言第一行寫「> 由 **{a.agent}** 回報」，讓人知道是誰。']
    vs_ = versions(ws)
    made = (load(os.path.join(vs_[-1][1], 'output', 'gates.json'), {}) or {}) if vs_ else {}
    if made.get('template'):                            # which template this version was built with, and why
        text += ['', '**模板**：' + ('MakeHuman（含手指的 52 根骨頭）' if made['template'] == 'makehuman' else '外殼流程（22 根骨頭）')
                 + ('；MakeHuman 擴充是這一次自動安裝的' if str(made.get('mpfb_install') or '').startswith('installed') else '')
                 + ('；預設是 MakeHuman，但這台機器的 Blender 沒有 MakeHuman 擴充（MPFB），自動安裝也沒有成功（'
                    + str(made.get('mpfb_install') or '沒有嘗試')[:200] + '），所以退回外殼流程。能連網時手動安裝：'
                    '`blender --online-mode --command extension install -s -e mpfb`，裝好後下一版就是 MakeHuman'
                    if made['template'] == 'hull' and made.get('mpfb') is False else '')]
    df = drive_files(ws)
    if df:
        text += ['', f'**雲端硬碟**：用 Google Drive 連結器把這一版的 {"、".join(df[1])} 放到 `{df[0]}/`（已經放過就略過）']
    pub = state.get('published', {})
    if pub:
        last = sorted(pub)[-1]
        text += ['', f'資料：{last} 已上傳 {pub[last]["url"]}']
    if state.get('publish_error'):
        text += ['', f'注意：{state["publish_error"]}（下次跑 next_step 會再試；一直失敗就照 ESCALATE 發 issue）']
    if on_claude:
        if waited is not None:
            text += ['', f'這次等了 {round(waited / 60, 1)} 分鐘，GitHub 上還沒有 Claude 的修正。']
        text += ['', '**再跑一次上面的指令繼續等（不要停下來問人）。**沒有任何東西會主動通知你：只有再跑一次才會再檢查 GitHub。']
    else:
        text += ['', '可以停下來。' if stop else '**照上面做完，再跑一次 next_step。不要停下來問人。**']
    open(os.path.join(ws, 'next_step.md'), 'w', encoding='utf-8').write('\n'.join(text))
    print('\n'.join(text))
    return 0


if __name__ == '__main__':
    sys.exit(main())
