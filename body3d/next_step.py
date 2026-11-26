#!/usr/bin/env python3
"""next_step.py — 執行者（ChatGPT／Gemini）每做完一步就跑這個：它只回答「下一步做什麼」（docs/Agent-Runbook.md）

    python body3d/next_step.py --workspace ~/avatar/chatgpt/avatar_001

WS 是這個 avatar 的資料夾：…/avatar/<chatgpt|gemini>/<avatar_NNN>/（agent 與 avatar 名稱從路徑來）。
每一輪是一個版本 vNNN/：vNNN/photos（33 張照片）、vNNN/output（run_all 的輸出）；狀態檔 avatar_state.json 在 WS。
重畫或重跑都開下一個版本（複製上一版的照片），不覆蓋舊的版本。
next_step 看最新的版本，讀它的驗收結果、診斷、工作單與過去每一輪的記錄，給出**一個**狀態與要照做的指令：

    UPDATE    GitHub 上的 main 有新的 SOP／程式（Claude 合併了）：git pull，用目前的照片從頭重跑
    START     還沒跑過：跑 run_all.py
    RUN       照片有了、還沒跑；或最新的結果是舊的程式跑的（body3d/ 之後改過）：跑 run_all.py
    RETOUCH   照片的問題：照 AI 修圖單重畫 → 下一個版本 v(N+1)/photos → 跑 run_all.py
    CODE      程式的問題：照 AI 改 code 單改程式 → 開 PR 給 Claude → 等合併
    ESCALATE  處理不掉：發 GitHub issue 給 Claude（內文已寫好）→ 等
    WAITING   issue 或 PR 還沒解決：等；Claude 合併了修正（程式變了）或 issue／PR 關閉，就繼續（issue 開著也一樣，跑完回報到 issue）
    DONE      四包都是好的：做交付檢查

每個有結果的版本會自動上傳到資料 repo（GitHub Release，data_repo.py），issue 內文附上連結。
只有 DONE 和 WAITING 可以停下來。其他狀態照指令做完，再跑一次 next_step，不要問人要不要繼續。
結果也寫在 WS/next_step.md 與 WS/avatar_state.json。
"""
import argparse
import datetime
import json
import os
import re
import shlex
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
REPEAT_ROUNDS = 2                      # the same FAIL item in this many runs in a row -> escalate


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
    return sorted({m.split(':', 1)[0].strip() for m in re.findall(r'^\s*\[FAIL\]\s*(.*)$', text, re.M)})


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


def run_cmd(photos, out, name, template):
    t = f' --template {template}' if template != 'hull' else ''
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
    if state.get('offline') or os.environ.get('NEXT_STEP_OFFLINE') or os.environ.get('NEXT_STEP_NO_PUBLISH'):
        return
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


def current_code():
    sys.path.insert(0, HERE)
    import run_all
    return run_all.code_hash()


def wait_answered(w, state):
    """Claude answers an escalation by merging a fix; the issue itself stays open until the executor reports the
    rerun (docs/Project-Loop.md). So a wait is over once the code here differs from the code it was registered
    under, whatever GitHub says (R33: issue #65 open by design, gh not logged in -> WAITING forever).
    Waits registered before this rule carry no fingerprint: use the code of the last run before the wait."""
    since = w.get('code')
    if not since and state.get('runs'):
        since = (load(os.path.join(state['runs'][-1]['out'], 'gates.json'), {}) or {}).get('code', {}).get('hash')
    return bool(since) and since != current_code()


FILE_LIST_HEAD = ['| agent | avatar | 版本 | 時間 | 結果 | 下一步 | 結果包 | 分享連結 |',
                  '| --- | --- | --- | --- | --- | --- | --- | --- |']


def update_file_list(ws, agent, avatar, next_state):
    """one row per version in avatar/file_list.md (next to the agent folders; docs/File-List.md): what each round
    gave and its result packs, so everyone finds the files by name. The share-link column is kept as people fill it."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(ws)))
    path = os.path.join(root, 'file_list.md')
    rows, links = {}, {}
    if os.path.exists(path):
        for line in open(path, encoding='utf-8').read().splitlines():
            c = [x.strip() for x in line.strip().strip('|').split('|')]
            if len(c) == 8 and c[2].startswith('v') and c[2][1:].isdigit():
                rows[(c[0], c[1], c[2])] = line
                links[(c[0], c[1], c[2])] = c[7]
    vs = versions(ws)
    for n, d in vs:
        out = os.path.join(d, 'output')
        g = load(os.path.join(out, 'gates.json'), None)
        if not g:
            continue
        key = (agent.lower(), avatar, f'v{n:03d}')
        res = '、'.join(f'{k.split()[0]}:{v["FAIL"]}F/{v["WARN"]}W' for k, v in g.get('gates', {}).items())
        res += '，可交付' if g.get('deliverable') else '，不能交付'
        when = datetime.datetime.fromtimestamp(os.path.getmtime(os.path.join(out, 'gates.json'))).strftime('%Y-%m-%d %H:%M')
        dl = os.path.join(out, 'deliver')
        packs = '<br>'.join(sorted(f for f in os.listdir(dl) if f.endswith('.zip'))) if os.path.isdir(dl) else ''
        nxt = next_state if n == vs[-1][0] else ''
        rows[key] = f'| {key[0]} | {key[1]} | {key[2]} | {when} | {res} | {nxt} | {packs} | {links.get(key, "")} |'
    if not rows:
        return None
    text = ['# avatar 檔案清單', '', '由 next_step 每一輪自動更新（docs/File-List.md）。「分享連結」欄由人或執行者填，'
            'next_step 會保留。這一份有人物照片的連結，不要放進公開的 GitHub。', ''] + FILE_LIST_HEAD
    text += [rows[k] for k in sorted(rows)]
    try:
        open(path, 'w', encoding='utf-8').write('\n'.join(text) + '\n')
        return path
    except OSError:
        return None


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
            steps = [f'cd {shlex.quote(REPO)} && git pull origin main   # {n_behind} 個新的 commit：' + '；'.join(info[:3])]
            if photos and out:
                steps += next_version_steps(ws, cn + 1, photos, name, template, '新的 SOP 可能改了檢查：同一組照片從頭重跑')
            elif photos:
                steps.append(run_cmd(photos, os.path.join(cur, 'output'), name, template))
            steps.append(me)
            return dict(state='UPDATE', why=f'GitHub 上的 main 比本機新 {n_behind} 個 commit（Claude 合併了新的 SOP／程式）',
                        steps=steps)
    if not photos:
        target = cur if cur and not out else vdir(ws, cn + 1)
        return dict(state='START', why=f'{os.path.basename(target)} 還沒有照片', steps=[
            f'照 docs/Workflow-and-Validation.md#生圖規格 生 33 張照片，放進 {target}/photos（檔名照規格）',
            run_cmd(f'{target}/photos', f'{target}/output', name, template), me])
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
        return dict(state='WAITING', why=f'等 Claude 處理 {kind} #{num}（目前 {st or "查不到狀態：檢查 gh 是否登入"}）', steps=[
            f'可以停下來。之後再跑：{me}'])
    if not out or not (os.path.exists(os.path.join(out, 'gates.json')) or os.path.exists(os.path.join(out, 'progress.json'))):
        return dict(state='RUN', why=f'{os.path.basename(cur)} 的照片還沒跑過', steps=[
            run_cmd(photos, os.path.join(cur, 'output'), name, template), me])
    gates = load(os.path.join(out, 'gates.json'), {})
    progress = load(os.path.join(out, 'progress.json'), {})
    diagnosis = load(os.path.join(out, 'diagnosis.json'), []) or []
    if progress.get('state') == 'running':
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
    # the same FAIL item two runs in a row -> escalate (the executor does not decide this)
    import escalate
    history = state.setdefault('runs', [])
    items = fail_items(out)
    if not history or history[-1].get('out') != out:
        history.append(dict(out=out, photos=photos, fail=items,
                            at=datetime.datetime.now().astimezone().isoformat(timespec='seconds')))
    repeated = set(items)
    for r in history[-REPEAT_ROUNDS:]:
        repeated &= set(r.get('fail', []))
    reason = None
    if len(history) >= REPEAT_ROUNDS and repeated:
        reason = escalate.REASONS[1]
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
    url = state.get('published', {}).get(os.path.basename(cur), {}).get('url')
    body = (f'**資料**：{url}（照片與結果包；重現：`python body3d/data_repo.py fetch {os.path.basename(url)} DIR`）\n\n'
            if url else f'**資料**：沒有上傳到資料 repo（{state.get("publish_error", "未知")}），請把 _FAIL.zip 附在 issue\n\n') + body
    issue = os.path.join(ws, 'issue.md')
    open(issue, 'w', encoding='utf-8').write(body)
    title = f'[SOP] {agent}／{avatar}：{reason}'
    return dict(state='ESCALATE', why=reason, steps=[
        f'gh issue create --repo WangChengYeh/Avatar --title {q(title)} --body-file {q(issue)}   # 記下 issue 編號 N',
        '照片與結果包已在資料 repo（issue 內文有連結）；沒有上傳成功時，把 output/deliver 裡的 _FAIL.zip 拖進 issue 附上',
        f'{me} --waiting-issue N   # 登記等待；Claude 關閉 issue 後 next_step 會叫你 pull、重跑'])


def main(argv=None):
    ap = argparse.ArgumentParser(description='下一步做什麼')
    ap.add_argument('--workspace', required=True, help='這個 avatar 的資料夾：…/avatar/<chatgpt|gemini>/<avatar_NNN>')
    ap.add_argument('--avatar', help='預設：資料夾名稱（avatar_NNN）')
    ap.add_argument('--agent', help='預設：上一層資料夾名稱（chatgpt／gemini）')
    ap.add_argument('--name', help='GLB 名稱，預設：avatar 名稱')
    ap.add_argument('--template', default='hull', choices=['hull', 'makehuman'])
    ap.add_argument('--waiting-issue', type=int); ap.add_argument('--waiting-pr', type=int)
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
    r = decide(ws, a.avatar, a.agent, a.name, a.template, state)
    state['last'] = dict(r, at=datetime.datetime.now().astimezone().isoformat(timespec='seconds'))
    fl = update_file_list(ws, a.agent, a.avatar, r['state'])
    rt = state.get('report_to')                         # still shown on DONE (the last report), then cleared
    if rt and r['state'] == 'DONE':
        state.pop('report_to', None)
    json.dump(state, open(sp, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    stop = r['state'] in ('DONE', 'WAITING')
    text = [f'# 下一步：{r["state"]}', '', f'原因：{r["why"]}', ''] + [f'{i}. `{s}`' if s.startswith(('python', 'gh ', 'mkdir', 'cd ', '/', "'"))
                                                                   else f'{i}. {s}' for i, s in enumerate(r['steps'], 1)]
    if rt:
        text += ['', f'**回報**：Claude 已經針對 {rt["kind"]} #{rt["number"]} 更新了 SOP／程式（issue 可能還開著，'
                     f'等你回報）。照上面繼續；這一輪跑完，把結果和 Claude 在 issue 留言要的數字回覆到 #{rt["number"]}：'
                     f'`gh issue comment {rt["number"]} --repo WangChengYeh/Avatar --body-file <檔案>`。'
                     '沒有 gh 時，把要回覆的內容寫進 issue_reply.md，交給人貼上。']
    if fl:
        text += ['', f'檔案清單：{fl}（這一輪已記上；要給 Claude 看的版本，在「分享連結」欄填上雲端硬碟的連結）']
    pub = state.get('published', {})
    if pub:
        last = sorted(pub)[-1]
        text += ['', f'資料：{last} 已上傳 {pub[last]["url"]}']
    if state.get('publish_error'):
        text += ['', f'注意：{state["publish_error"]}（下次跑 next_step 會再試；一直失敗就照 ESCALATE 發 issue）']
    text += ['', '可以停下來。' if stop else '**照上面做完，再跑一次 next_step。不要停下來問人。**']
    open(os.path.join(ws, 'next_step.md'), 'w', encoding='utf-8').write('\n'.join(text))
    print('\n'.join(text))
    return 0


if __name__ == '__main__':
    sys.exit(main())
