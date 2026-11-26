#!/usr/bin/env python3
"""next_step.py — 執行者（ChatGPT／Gemini）每做完一步就跑這個：它只回答「下一步做什麼」（docs/Agent-Runbook.md）

    python body3d/next_step.py --workspace WS --avatar avatar-A --agent ChatGPT

WS 是這個 avatar 的工作區：照片資料夾 photos_vN/、輸出資料夾 out_vN/、狀態檔 avatar_state.json 都在裡面。
next_step 找最新的 out_vN，讀它的驗收結果、診斷、工作單與過去每一輪的記錄，給出**一個**狀態與要照做的指令：

    START     還沒跑過：跑 run_all.py
    RUN       照片有了、還沒跑（或剛 pull 了新的 SOP）：跑 run_all.py
    RETOUCH   照片的問題：照 AI 修圖單重畫 → 放進 photos_v(N+1) → 跑 run_all.py
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


def latest(ws, prefix):
    """(n, path) of the highest WS/prefix_vN, or (0, None)"""
    best = (0, None)
    for f in os.listdir(ws) if os.path.isdir(ws) else []:
        m = re.fullmatch(prefix + r'_v(\d+)', f)
        if m and os.path.isdir(os.path.join(ws, f)) and int(m.group(1)) > best[0]:
            best = (int(m.group(1)), os.path.join(ws, f))
    return best


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


def run_cmd(ws, photos, n, name, template):
    out = os.path.join(ws, f'out_v{n}')
    t = f' --template {template}' if template != 'hull' else ''
    return f'python {os.path.join(REPO, "body3d", "run_all.py")} {photos} {out} --name {name}{t}'


def decide(ws, avatar, agent, name, template, state):
    pn, photos = latest(ws, 'photos')
    on, out = latest(ws, 'out')
    me = f'python {os.path.join(REPO, "body3d", "next_step.py")} --workspace {ws} --avatar {avatar} --agent {agent}'
    if not photos:
        return dict(state='START', why='工作區還沒有照片', steps=[
            f'照 docs/Workflow-and-Validation.md#生圖規格 生 33 張照片，放進 {os.path.join(ws, "photos_v1")}（檔名照規格）',
            run_cmd(ws, os.path.join(ws, 'photos_v1'), 1, name, template), me])
    # waiting on Claude: an issue or a PR
    w = state.get('waiting')
    if w:
        kind, num = w['kind'], w['number']
        st = gh(kind, 'view', str(num), '--json', 'state', '--jq', '.state')
        if st in ('CLOSED', 'MERGED'):
            state['waiting'] = None
            nxt = on + 1
            return dict(state='RUN', why=f'{kind} #{num} 已解決（{st}）：拿新的 SOP／程式從頭重跑', steps=[
                f'cd {REPO} && git pull origin main',
                run_cmd(ws, photos, nxt, name, template), me])
        return dict(state='WAITING', why=f'等 Claude 處理 {kind} #{num}（目前 {st or "查不到狀態：檢查 gh 是否登入"}）', steps=[
            f'可以停下來。之後再跑：{me}'])
    if not out or on < pn:
        n = max(on + 1, pn)
        return dict(state='RUN', why=f'photos_v{pn} 還沒跑過', steps=[run_cmd(ws, photos, n, name, template), me])
    gates = load(os.path.join(out, 'gates.json'), {})
    progress = load(os.path.join(out, 'progress.json'), {})
    diagnosis = load(os.path.join(out, 'diagnosis.json'), []) or []
    if progress.get('state') == 'running':
        return dict(state='WAITING', why=f'{out} 還在跑', steps=[f'等它跑完，再跑：{me}'])
    if gates.get('deliverable'):
        return dict(state='DONE', why=f'{out}：四道關卡全部 0 FAIL，四包都是好的', steps=[
            '照 docs/SOP.md#可以交付了嗎 做交付檢查：逐項看需複核（WARN）記在 Issue；在 Yoga2 匯入 GLB 截圖（站姿、抬手）',
            f'交付：{os.path.join(out, "deliver")} 四包 + {os.path.join(out, "client")}'])
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
        nxt = pn + 1
        new = os.path.join(ws, f'photos_v{nxt}')
        req = os.path.join(out, 'ai_fix_request')
        redo = sorted(os.listdir(os.path.join(req, 'photos')))
        return dict(state='RETOUCH', why=f'照片的問題（{first["item"]}，信心{first["confidence"]}）', steps=[
            f'把 {os.path.join(req, "AI修圖單.md")} 與 {req}/photos、{req}/reference 交給生圖 AI，照單重畫：{"、".join(redo)}',
            f'mkdir -p {new} && cp {photos}/*.jpg {new}/   # 先複製整組，再用重畫好的覆蓋那 {len(redo)} 張',
            f'把重畫好的照片（同檔名）放進 {new}',
            run_cmd(ws, new, max(on + 1, nxt), name, template), me])
    if not reason and first and first['owner'] != '照片' and os.path.exists(os.path.join(out, 'ai_code_request', 'AI改code單.md')):
        return dict(state='CODE', why=f'程式的問題（{first["item"]}，信心{first["confidence"]}）', steps=[
            f'照 {os.path.join(out, "ai_code_request", "AI改code單.md")} 在 {REPO} 開分支、補檢查、改程式、驗收（兩組完美照片全部通過）',
            '開 PR 給 Claude review（用 .github/pull_request_template.md），記下 PR 編號 N',
            f'{me} --waiting-pr N   # 登記等待；合併後 next_step 會叫你 pull、重跑'])
    # escalate: write the issue body
    reason = reason or escalate.REASONS[0]
    tried = '；'.join(f'{os.path.basename(r["out"])}（{os.path.basename(r["photos"])}）：{len(r.get("fail", []))} 項 FAIL'
                     for r in history[-4:])
    body = escalate.body(out, agent, avatar, tried=f'最近幾輪：{tried}。重複出現的 FAIL：{"、".join(sorted(repeated)) or "無"}',
                         reason=reason)
    issue = os.path.join(ws, 'issue.md')
    open(issue, 'w', encoding='utf-8').write(body)
    title = f'[SOP] {avatar}：{reason}'
    return dict(state='ESCALATE', why=reason, steps=[
        f'gh issue create --repo WangChengYeh/Avatar --title "{title}" --body-file {issue}   # 記下 issue 編號 N',
        f'把 {os.path.join(out, "deliver")} 裡的 _FAIL.zip 拖進 issue 留言附上',
        f'{me} --waiting-issue N   # 登記等待；Claude 關閉 issue 後 next_step 會叫你 pull、重跑'])


def main(argv=None):
    ap = argparse.ArgumentParser(description='下一步做什麼')
    ap.add_argument('--workspace', required=True); ap.add_argument('--avatar', required=True)
    ap.add_argument('--agent', required=True); ap.add_argument('--name', default='body')
    ap.add_argument('--template', default='hull', choices=['hull', 'makehuman'])
    ap.add_argument('--waiting-issue', type=int); ap.add_argument('--waiting-pr', type=int)
    a = ap.parse_args(argv)
    ws = os.path.abspath(a.workspace); os.makedirs(ws, exist_ok=True)
    sp = os.path.join(ws, 'avatar_state.json')
    state = load(sp, {}) or {}
    if a.waiting_issue or a.waiting_pr:
        state['waiting'] = dict(kind='issue' if a.waiting_issue else 'pr', number=a.waiting_issue or a.waiting_pr)
    r = decide(ws, a.avatar, a.agent, a.name, a.template, state)
    state['last'] = dict(r, at=datetime.datetime.now().astimezone().isoformat(timespec='seconds'))
    json.dump(state, open(sp, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    stop = r['state'] in ('DONE', 'WAITING')
    text = [f'# 下一步：{r["state"]}', '', f'原因：{r["why"]}', ''] + [f'{i}. `{s}`' if s.startswith(('python', 'gh ', 'mkdir', 'cd '))
                                                                   else f'{i}. {s}' for i, s in enumerate(r['steps'], 1)]
    text += ['', '可以停下來。' if stop else '**照上面做完，再跑一次 next_step。不要停下來問人。**']
    open(os.path.join(ws, 'next_step.md'), 'w', encoding='utf-8').write('\n'.join(text))
    print('\n'.join(text))
    return 0


if __name__ == '__main__':
    sys.exit(main())
