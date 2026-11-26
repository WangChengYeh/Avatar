#!/usr/bin/env python3
"""escalate.py — 診斷處理不掉時，整理發給 Claude 的 GitHub issue 內文（docs/Project-Loop.md）

    python escalate.py OUTPUT_DIR --agent ChatGPT --avatar avatar_001 [--tried "重畫 el30_090 兩次，仍 FAIL"] [--reason ...]
    gh issue create --title "[SOP] ChatGPT／avatar_001：<一句話>" --body-file issue.md
（一般由 next_step 走到 ESCALATE 時自動產生；照片不附在公開的 issue，寫雲端硬碟的路徑）

內文：SOP／程式版本與 git commit、驗收總表、停在哪一步、診斷（照修的順序）、每一項未通過的原文、AI 修圖單／
改 code 單是否已產生、run_all.log 末段。
"""
import argparse
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REASONS = ['診斷信心低或沒有對應的規則', '同一個 FAIL 修了 2 輪還在', 'SOP 或檢查有缺口（後面才 FAIL，前面沒抓到）',
           '程式出錯、或 AI 改 code 單做不完', 'SOP 互相矛盾或不清楚', '懷疑門檻錯']


def load(path):
    try:
        return json.load(open(path, encoding='utf-8'))
    except (OSError, ValueError):
        return None


def versions():
    out = {}
    for script, key in (('run_all.py', 'body3d'), ('check_turnaround.py', '照片檢查')):
        try:
            r = subprocess.run([sys.executable, os.path.join(HERE, script), '--version'], capture_output=True, text=True,
                               timeout=60)
            out[key] = (r.stdout or r.stderr).strip().split()[-1]
        except (OSError, subprocess.SubprocessError, IndexError):
            out[key] = '?'
    try:
        out['commit'] = subprocess.run(['git', '-C', HERE, 'rev-parse', '--short', 'HEAD'], capture_output=True,
                                       text=True).stdout.strip() or '?'
        dirty = subprocess.run(['git', '-C', HERE, 'status', '--porcelain', '--untracked-files=no'], capture_output=True,
                               text=True).stdout.strip()
        if dirty:
            out['commit'] += '（有未提交的改動）'
    except OSError:
        out['commit'] = '?'
    return out


def auto_reason(diagnosis, progress, gates):
    """the escalation rule the evidence matches, if any (the executor confirms)"""
    if progress and progress.get('state') == 'stopped' and not any(v['FAIL'] for v in (gates or {}).get('gates', {}).values()):
        return REASONS[3]
    if diagnosis and any(d.get('confidence') == '低' for d in diagnosis):
        return REASONS[0]
    g = (gates or {}).get('gates', {})
    first_fail = next((k for k, v in g.items() if v['FAIL']), None)
    if first_fail and first_fail[0] in '34' and all(v['FAIL'] == 0 for k, v in g.items() if k[0] < first_fail[0]):
        return REASONS[2]                              # caught late, nothing earlier caught it (R17)
    if g and not diagnosis and any(v['FAIL'] for v in g.values()):
        return REASONS[0]
    return None


def body(out, agent, avatar, tried='', reason=None):
    gates = load(os.path.join(out, 'gates.json'))
    progress = load(os.path.join(out, 'progress.json'))
    diagnosis = load(os.path.join(out, 'diagnosis.json')) or []
    v = versions()
    reason = reason or auto_reason(diagnosis, progress, gates) or '（請選一條，見 docs/Project-Loop.md）'
    L = [f'**執行者**：{agent}　**Avatar**：{avatar}', f'**為什麼發**：{reason}', '',
         f'**版本**：body3d {v["body3d"]}、照片檢查 {v["照片檢查"]}、commit `{v["commit"]}`', '']
    if gates:
        L += ['### 驗收總表', '', '| 關卡 | FAIL | WARN | PASS |', '| --- | --- | --- | --- |']
        L += [f'| {k} | {x["FAIL"]} | {x["WARN"]} | {x["PASS"]} |' for k, x in gates.get('gates', {}).items()]
        L += ['', f'可交付：{"是" if gates.get("deliverable") else "否"}', '']
    if progress and progress.get('state') == 'stopped':
        L += [f'**停在**：`{progress.get("stopped_at")}`（階段 {progress.get("stopped_stage", "?")}）：{progress.get("reason", "")}', '']
    if diagnosis:
        L += ['### 診斷（照修的順序）', '']
        for d in sorted(diagnosis, key=lambda d: d.get('order', 99)):
            L += [f'{d.get("order", "-")}. **{d["item"]}**［{d.get("stage_name", "")}｜{d["owner"]}｜信心{d["confidence"]}］：{d["cause"]}',
                  f'   - 怎麼修：{d["action"]}', f'   - 路徑：{" → ".join(d["path"])}']
        L.append('')
    else:
        L += ['### 診斷', '', '（沒有診斷：這一關沒有診斷樹，或程式在診斷前就停了）', '']
    log = os.path.join(out, 'run_all.log')
    fails = []
    if os.path.exists(log):
        text = open(log, encoding='utf-8', errors='replace').read()
        fails = [m.strip() for m in re.findall(r'^\s*\[FAIL\]\s*(.*)$', text, re.M)]
    if fails:
        L += ['<details><summary>未通過原文（' + str(len(fails)) + ' 項）</summary>', '', '```']
        L += fails[-60:] + ['```', '</details>', '']
    req = [p for p in ('ai_fix_request/AI修圖單.md', 'ai_code_request/AI改code單.md') if os.path.exists(os.path.join(out, p))]
    L += ['**已產生的工作單**：' + ('、'.join(f'`{p}`' for p in req) if req else '沒有'),
          '**結果包**：' + ('、'.join(sorted(os.listdir(os.path.join(out, 'deliver')))) if os.path.isdir(os.path.join(out, 'deliver')) else '沒有')
          + '（`_FAIL.zip` 請拖進 issue 附上）', '']
    if os.path.exists(log):
        tail = open(log, encoding='utf-8', errors='replace').read().splitlines()[-40:]
        L += ['<details><summary>run_all.log 末段</summary>', '', '```'] + tail + ['```', '</details>', '']
    L += ['### 做過什麼', '', tried or '（請補：照哪張單、修了幾輪、每一輪的結果）', '',
          '### 我的判斷', '', '（請補：原因在哪個階段、是照片／檢查／程式／SOP，為什麼）']
    return '\n'.join(L)


def main(argv=None):
    ap = argparse.ArgumentParser(description='整理發給 Claude 的 GitHub issue 內文')
    ap.add_argument('out'); ap.add_argument('--agent', required=True); ap.add_argument('--avatar', required=True)
    ap.add_argument('--tried', default=''); ap.add_argument('--reason', choices=REASONS)
    a = ap.parse_args(argv)
    print(body(a.out, a.agent, a.avatar, a.tried, a.reason))
    return 0


if __name__ == '__main__':
    sys.exit(main())
