#!/usr/bin/env python3
"""deliver.py — 階段交付物打包（docs/SOP.md「每個階段的交付物」）

每個階段結束一定打包成果（好或不好都有）：該階段與之前的關卡全部 0 FAIL 是 {name}_stageN_xxx.zip（好、可交付），
否則是 {name}_stageN_xxx_FAIL.zip（不好，manifest 列出未通過項目）。
    stage1_photos          33 張照片（原檔）＋照片檢查報告
    stage2_reconstruction  相機 cams33.json、人體網格、頭部對照圖與疊圖
    stage3_models          兩個 GLB＋預覽圖
    stage4_acceptance      原圖對模型對照圖、fit_report.json
    每個 zip 都有 manifest.json：每個檔的 SHA-256、各關卡總結、deliverable、未通過清單、打包時間

用法（run_all.py 會自動執行；也可以單獨執行。結束碼：可交付 0、有 FAIL 1）:
    python deliver.py stage1 IMG_DIR OUT_DIR [--name body]
"""
import argparse
import datetime
import hashlib
import json
import os
import re
import subprocess
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ANGLES = range(0, 360, 45)
MAIN = ['01_000deg_front', '02_045deg_front_left', '03_090deg_left', '04_135deg_back_left', '05_180deg_back',
        '06_225deg_back_right', '07_270deg_right', '08_315deg_front_right']
PHOTOS = ([f + '.jpg' for f in MAIN] + [f'{r}_{a:03d}deg.jpg' for r in ('el30', 'low20', 'head') for a in ANGLES]
          + ['top.jpg'])                                 # the 33 file names of the input spec


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


STAGES = {1: 'photos', 2: 'reconstruction', 3: 'models', 4: 'acceptance'}
STAGE_ZH = {1: '33 張照片', 2: '重建（相機與人體形狀）', 3: '模型（GLB）', 4: '成品驗收（原圖對模型）'}


def zip_paths(out, name, stage=1):
    d = os.path.join(out, 'deliver')
    base = f'{name}_stage{stage}_{STAGES[stage]}'
    return os.path.join(d, base + '.zip'), os.path.join(d, base + '_FAIL.zip')


def pack(out, name, stage, files, gates, failures=(), missing=(), extra=None, stopped=None):
    """write the zip of one stage, always (docs/SOP.md: every stage has a result, good or not good).
    files: {name in the zip: path}; gates: {gate: (FAIL, WARN, PASS)} of this stage and the ones before it. Good
    (the plain name, deliverable) = every gate so far has 0 FAIL and nothing is missing; otherwise _FAIL.zip with the
    failed items. stopped = (step, reason) when the run stopped inside this stage: whatever exists is packed and the
    result is _FAIL. Only one of the two exists at a time. Returns (path, good)."""
    missing = list(missing)
    if stopped:                                      # list what the stage would have made but had not yet
        missing += [k for k, v in files.items() if not (v and os.path.exists(v))]
    ok = bool(gates) and not any(g[0] for g in gates.values()) and not missing and not stopped
    good, bad = zip_paths(out, name, stage)
    for f in (good, bad):                              # never an outdated result beside the new one
        if os.path.exists(f):
            os.remove(f)
    os.makedirs(os.path.dirname(good), exist_ok=True)
    dst = good if ok else bad
    files = {k: v for k, v in files.items() if v and os.path.exists(v)}
    manifest = dict(stage=stage, contents=STAGE_ZH[stage], name=name, deliverable=ok,
                    created=datetime.datetime.now().astimezone().isoformat(timespec='seconds'),
                    gates={g: dict(FAIL=v[0], WARN=v[1], PASS=v[2]) for g, v in gates.items()},
                    failures=list(failures), missing=missing,
                    stopped=dict(step=stopped[0], reason=stopped[1]) if stopped else None,
                    sha256={k: sha256(v) for k, v in files.items()}, **(extra or {}))
    tmp = dst + '.tmp'
    with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED) as z:
        for k, v in files.items():
            z.write(v, k, compress_type=zipfile.ZIP_STORED if k.lower().endswith(('.jpg', '.png', '.glb')) else
                    zipfile.ZIP_DEFLATED)
        z.writestr('manifest.json', json.dumps(manifest, ensure_ascii=False, indent=1))
    os.replace(tmp, dst)
    return dst, ok


def stage1(img, out, name, summary, checker_version, report=None, failures=(), autofix=None, diagnosis=None):
    """the 33 photos (+ check report). summary = (FAIL, WARN, PASS) of the photo check"""
    missing = [p for p in PHOTOS if not os.path.exists(os.path.join(img, p))]
    files = {f'photos/{p}': os.path.join(img, p) for p in PHOTOS}
    files['turnaround_report.png'] = report
    extra = dict(photo_check_version=checker_version)
    if autofix:                                        # photos corrected automatically: what changed, and from what
        files['autofix.json'] = autofix
        extra['autofix'] = json.load(open(autofix))['fixes']
    if diagnosis:
        extra['diagnosis'] = diagnosis
    return pack(out, name, 1, files, {'1 照片檢查': tuple(summary)}, failures, missing, extra)


def main(argv=None):
    ap = argparse.ArgumentParser(description='階段交付物打包')
    ap.add_argument('stage', choices=['stage1'])
    ap.add_argument('img'); ap.add_argument('out')
    ap.add_argument('--name', default='body')
    a = ap.parse_args(argv)
    os.makedirs(a.out, exist_ok=True)
    report = os.path.join(a.out, 'turnaround_report.png')
    r = subprocess.run([sys.executable, os.path.join(HERE, 'check_turnaround.py'), a.img, '--out', report],
                       capture_output=True, text=True)
    m = re.findall(r'總結: (\d+) 個 FAIL, (\d+) 個 WARN, (\d+) 個 PASS', r.stdout)
    v = re.search(r'check_turnaround 版本 (\S+?)（', r.stdout)
    if not m:
        print(r.stdout[-2000:] + r.stderr[-2000:]); return 2
    dst, ok = stage1(a.img, a.out, a.name, tuple(map(int, m[-1])), v.group(1) if v else '?', report,
                     fail_lines(r.stdout))
    print(('階段 1 交付：' if ok else '階段 1 未通過（不能交付，照片仍打包供檢查）：') + dst)
    return 0 if ok else 1


def fail_lines(text):
    """the [FAIL] lines of a check's output, without the tag"""
    return [m.strip() for m in re.findall(r'^\s*\[FAIL\]\s*(.*)$', text, re.M)]


if __name__ == '__main__':
    sys.exit(main())
