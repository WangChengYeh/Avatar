#!/usr/bin/env python3
"""deliver.py — 階段交付物打包（docs/SOP.md「每個階段的交付物」）

階段 1 結束時一定打包 33 張照片的 zip（未通過也打包，供檢查與存檔）：
    OUT/deliver/{name}_stage1_photos.zip        照片檢查 0 FAIL：這個才是交付物
    OUT/deliver/{name}_stage1_photos_FAIL.zip   有 FAIL：不能交付，manifest 列出每個未通過項目
        photos/  33 張照片（原檔，不重新壓縮）
        turnaround_report.png（照片檢查報告）
        manifest.json  每個檔的 SHA-256、照片檢查版本與總結（FAIL / WARN / PASS）、deliverable、未通過清單、打包時間

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


def zip_paths(out, name):
    d = os.path.join(out, 'deliver')
    return os.path.join(d, f'{name}_stage1_photos.zip'), os.path.join(d, f'{name}_stage1_photos_FAIL.zip')


def stage1(img, out, name, summary, checker_version, report=None, failures=()):
    """write the stage 1 zip, always: {name}_stage1_photos.zip when the check has no FAIL (the deliverable),
    {name}_stage1_photos_FAIL.zip otherwise (kept for review, not deliverable). summary = (FAIL, WARN, PASS);
    failures = the FAIL lines of the check. Missing photos are listed in the manifest and make it _FAIL too."""
    missing = [p for p in PHOTOS if not os.path.exists(os.path.join(img, p))]
    ok = not summary[0] and not missing
    good, bad = zip_paths(out, name)
    for f in (good, bad):                              # one stage 1 zip at a time: never an outdated one beside it
        if os.path.exists(f):
            os.remove(f)
    os.makedirs(os.path.dirname(good), exist_ok=True)
    dst = good if ok else bad
    files = {f'photos/{p}': os.path.join(img, p) for p in PHOTOS if p not in missing}
    if report and os.path.exists(report):
        files['turnaround_report.png'] = report
    manifest = dict(stage=1, contents='33 張照片', name=name, deliverable=ok,
                    created=datetime.datetime.now().astimezone().isoformat(timespec='seconds'),
                    photo_check=dict(version=checker_version, FAIL=summary[0], WARN=summary[1], PASS=summary[2]),
                    failures=list(failures), missing=missing,
                    sha256={k: sha256(v) for k, v in files.items()})
    tmp = dst + '.tmp'
    with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_STORED) as z:        # JPEG / PNG are compressed already
        for k, v in files.items():
            z.write(v, k)
        z.writestr('manifest.json', json.dumps(manifest, ensure_ascii=False, indent=1))
    os.replace(tmp, dst)
    return dst, ok


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
