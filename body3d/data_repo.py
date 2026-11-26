#!/usr/bin/env python3
"""data_repo.py — 用 GitHub 的資料 repo 交換照片與結果（docs/Project-Loop.md「資料放在哪裡」）

每個 avatar 的每個版本是資料 repo（預設 WangChengYeh/avatar_data，環境變數 AVATAR_DATA_REPO 可改）的一個 Release：
    tag      <agent>-<avatar>-v<NNN>，例：chatgpt-avatar_001-v003
    附件     photos.zip（33 張照片）、四個階段的結果包、gates.json、diagnosis.json、next_step.md

    python body3d/data_repo.py publish WS NNN      # 上傳 WS/vNNN（next_step 會自動做）
    python body3d/data_repo.py fetch TAG DEST      # 下載一個版本到 DEST/vNNN/photos、DEST/vNNN/output/deliver（Claude 重現用）
    python body3d/data_repo.py list [AGENT/AVATAR] # 列出版本

需要 gh（已登入，且對資料 repo 有寫入權限）。
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

DATA_REPO = os.environ.get('AVATAR_DATA_REPO', 'WangChengYeh/avatar_data')


def gh(*args, check=True):
    r = subprocess.run(['gh', *args], capture_output=True, text=True, timeout=900)
    if check and r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout).strip().splitlines()[-1] if (r.stderr or r.stdout) else 'gh failed')
    return r


def tag_of(ws, n):
    """<agent>-<avatar>-v<NNN> from the avatar folder WS = …/avatar/<agent>/<avatar>"""
    ws = os.path.abspath(ws)
    return f'{os.path.basename(os.path.dirname(ws)).lower()}-{os.path.basename(ws)}-v{n:03d}'


def summary(out):
    """release notes: the gate table and whether it is deliverable"""
    g = {}
    try:
        g = json.load(open(os.path.join(out, 'gates.json'), encoding='utf-8'))
    except (OSError, ValueError):
        pass
    L = ['| 關卡 | FAIL | WARN | PASS |', '| --- | --- | --- | --- |']
    L += [f'| {k} | {v["FAIL"]} | {v["WARN"]} | {v["PASS"]} |' for k, v in g.get('gates', {}).items()]
    code = (g.get('code') or {})
    L += ['', f'可交付：{"是" if g.get("deliverable") else "否"}　程式：body3d {code.get("body3d", "?")}、'
          f'commit {str(code.get("commit") or "?")[:7]}']
    return '\n'.join(L)


def publish(ws, n, repo=DATA_REPO):
    """upload WS/vNNN as a release; returns its URL. Assets are replaced (--clobber), so publishing again after a
    rerun of the same version keeps one release per version."""
    v = os.path.join(os.path.abspath(ws), f'v{n:03d}')
    photos, out = os.path.join(v, 'photos'), os.path.join(v, 'output')
    tag = tag_of(ws, n)
    tmp = tempfile.mkdtemp()
    try:
        assets = []
        if os.path.isdir(photos):
            z = os.path.join(tmp, 'photos.zip')
            with zipfile.ZipFile(z, 'w', zipfile.ZIP_STORED) as f:
                for p in sorted(os.listdir(photos)):
                    if p.lower().endswith('.jpg'):
                        f.write(os.path.join(photos, p), p)
            assets.append(z)
        d = os.path.join(out, 'deliver')
        if os.path.isdir(d):
            assets += [os.path.join(d, f) for f in sorted(os.listdir(d)) if f.endswith('.zip')]
        for f in ('gates.json', 'diagnosis.json'):
            if os.path.exists(os.path.join(out, f)):
                assets.append(os.path.join(out, f))
        if os.path.exists(os.path.join(ws, 'next_step.md')):
            assets.append(os.path.join(ws, 'next_step.md'))
        notes = summary(out)
        if gh('release', 'view', tag, '--repo', repo, check=False).returncode != 0:
            gh('release', 'create', tag, '--repo', repo, '--title', tag, '--notes', notes)
        else:
            gh('release', 'edit', tag, '--repo', repo, '--notes', notes)
        # stage zips are good or _FAIL: drop the other name of the same stage left from an earlier upload
        names = {os.path.basename(a) for a in assets}
        old = json.loads(gh('release', 'view', tag, '--repo', repo, '--json', 'assets').stdout or '{}').get('assets', [])
        for a in old:
            m = re.match(r'(.+_stage\d_[a-z]+?)(_FAIL)?\.zip$', a['name'])
            if m and a['name'] not in names:
                gh('release', 'delete-asset', tag, a['name'], '--repo', repo, '--yes', check=False)
        if assets:
            gh('release', 'upload', tag, *assets, '--repo', repo, '--clobber')
        return f'https://github.com/{repo}/releases/tag/{tag}'
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def fetch(tag, dest, repo=DATA_REPO):
    """download a version: DEST/vNNN/photos (from photos.zip) and DEST/vNNN/output/deliver (the stage zips)"""
    m = re.search(r'-v(\d{3,})$', tag)
    if not m:
        raise ValueError(f'tag 要是 <agent>-<avatar>-vNNN：{tag}')
    v = os.path.join(dest, f'v{m.group(1)}')
    tmp = tempfile.mkdtemp()
    try:
        gh('release', 'download', tag, '--repo', repo, '--dir', tmp, '--clobber')
        os.makedirs(os.path.join(v, 'photos'), exist_ok=True)
        os.makedirs(os.path.join(v, 'output', 'deliver'), exist_ok=True)
        for f in os.listdir(tmp):
            p = os.path.join(tmp, f)
            if f == 'photos.zip':
                with zipfile.ZipFile(p) as z:
                    z.extractall(os.path.join(v, 'photos'))
            elif f.endswith('.zip'):
                shutil.move(p, os.path.join(v, 'output', 'deliver', f))
            else:
                shutil.move(p, os.path.join(v, 'output', f))
        return v
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main(argv=None):
    a = argv if argv is not None else sys.argv[1:]
    if len(a) >= 3 and a[0] == 'publish':
        print(publish(a[1], int(a[2])))
    elif len(a) >= 3 and a[0] == 'fetch':
        print(fetch(a[1], a[2]))
    elif a and a[0] == 'list':
        r = gh('release', 'list', '--repo', DATA_REPO, '--limit', '200')
        pat = (a[1].replace('/', '-').lower() + '-') if len(a) > 1 else ''
        print('\n'.join(l for l in r.stdout.splitlines() if pat in l.lower()))
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
