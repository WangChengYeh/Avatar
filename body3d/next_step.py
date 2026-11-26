#!/usr/bin/env python3
"""next_step.py — 執行者（ChatGPT／Gemini）每做完一步就跑這個：它只回答「下一步做什麼」（docs/Agent-Runbook.md）

    python body3d/next_step.py --workspace "<Google Drive>/avatar/chatgpt/avatar_001"

WS 是這個 avatar 的資料夾，放在 Google Drive：avatar/<chatgpt|gemini>/<avatar_NNN>/（agent 與 avatar 名稱從路徑來）。
每一輪是一個版本 vNNN/：vNNN/photos（33 張照片）、vNNN/output（run_all 的輸出）；狀態檔 avatar_state.json 在 WS。
重畫或重跑都開下一個版本（複製上一版的照片），不覆蓋舊的版本。
next_step 看最新的版本，讀它的驗收結果、診斷、工作單與過去每一輪的記錄，給出**一個**狀態與要照做的指令：

    UPDATE    GitHub 上的 main 有新的 SOP／程式（Claude 合併了）：git pull，用目前的照片從頭重跑
    START     還沒跑過：跑 run_all.py
    RUN       照片有了、還沒跑；或最新的結果是舊的程式跑的（body3d/ 之後改過）：跑 run_all.py
    RETOUCH   照片的問題：照 AI 修圖單重畫 → 下一個版本 v(N+1)/photos → 跑 run_all.py
    CODE      程式的問題：照 AI 改 code 單改程式 → 開 PR 給 Claude → 等合併
    ESCALATE  處理不掉：發 GitHub issue 給 Claude（內文已寫好）→ 等
    WAITING   issue 或 PR 還沒解決：等；解決了就 pull、跑 run_all.py
    DONE      四包都是好的：做交付檢查

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
    q = shlex.quote                                    # Google Drive paths have spaces ("My Drive")
    return [f'mkdir -p {q(new + "/photos")} && cp {q(photos)}/*.jpg {q(new + "/photos")}/' + (f'   # {why}' if why else ''),
            run_cmd(f'{new}/photos', f'{new}/output', name, template)]


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
    body = f'**位置**：Google Drive `avatar/{agent.lower()}/{avatar}/{os.path.basename(cur)}`\n\n' + body
    issue = os.path.join(ws, 'issue.md')
    open(issue, 'w', encoding='utf-8').write(body)
    title = f'[SOP] {agent}／{avatar}：{reason}'
    return dict(state='ESCALATE', why=reason, steps=[
        f'gh issue create --repo WangChengYeh/Avatar --title {q(title)} --body-file {q(issue)}   # 記下 issue 編號 N',
        f'把 {os.path.join(out, "deliver")} 裡的 _FAIL.zip 拖進 issue 留言附上',
        f'{me} --waiting-issue N   # 登記等待；Claude 關閉 issue 後 next_step 會叫你 pull、重跑'])


def main(argv=None):
    ap = argparse.ArgumentParser(description='下一步做什麼')
    ap.add_argument('--workspace', required=True, help='這個 avatar 的資料夾：<Google Drive>/avatar/<chatgpt|gemini>/<avatar_NNN>')
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
        state['waiting'] = dict(kind='issue' if a.waiting_issue else 'pr', number=a.waiting_issue or a.waiting_pr)
    r = decide(ws, a.avatar, a.agent, a.name, a.template, state)
    state['last'] = dict(r, at=datetime.datetime.now().astimezone().isoformat(timespec='seconds'))
    json.dump(state, open(sp, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    stop = r['state'] in ('DONE', 'WAITING')
    text = [f'# 下一步：{r["state"]}', '', f'原因：{r["why"]}', ''] + [f'{i}. `{s}`' if s.startswith(('python', 'gh ', 'mkdir', 'cd ', '/', "'"))
                                                                   else f'{i}. {s}' for i, s in enumerate(r['steps'], 1)]
    text += ['', '可以停下來。' if stop else '**照上面做完，再跑一次 next_step。不要停下來問人。**']
    open(os.path.join(ws, 'next_step.md'), 'w', encoding='utf-8').write('\n'.join(text))
    print('\n'.join(text))
    return 0


if __name__ == '__main__':
    sys.exit(main())
