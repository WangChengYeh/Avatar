#!/usr/bin/env python3
"""deliver.py — 階段交付物打包（docs/SOP.md「每個階段的交付物」）

階段 1 結束（照片檢查 0 FAIL）時交付 33 張照片的 zip：
    OUT/deliver/{name}_stage1_photos.zip
        photos/  33 張照片（原檔，不重新壓縮）
        turnaround_report.png（照片檢查報告）
        manifest.json  每個檔的 SHA-256、照片檢查版本與總結（FAIL / WARN / PASS）、打包時間

用法（run_all.py 會自動執行；也可以單獨執行，照片檢查有 FAIL 時拒絕打包）:
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


def stage1(img, out, name, summary, checker_version, report=None):
    """write OUT/deliver/{name}_stage1_photos.zip; summary = (FAIL, WARN, PASS) of the photo check (must be 0 FAIL)"""
    if summary[0]:
        raise ValueError(f'照片檢查有 {summary[0]} 項未通過，階段 1 還不能交付')
    missing = [p for p in PHOTOS if not os.path.exists(os.path.join(img, p))]
    if missing:
        raise ValueError('缺少照片：' + '、'.join(missing))
    d = os.path.join(out, 'deliver'); os.makedirs(d, exist_ok=True)
    dst = os.path.join(d, f'{name}_stage1_photos.zip')
    files = {f'photos/{p}': os.path.join(img, p) for p in PHOTOS}
    if report and os.path.exists(report):
        files['turnaround_report.png'] = report
    manifest = dict(stage=1, deliverable='33 張照片', name=name,
                    created=datetime.datetime.now().astimezone().isoformat(timespec='seconds'),
                    photo_check=dict(version=checker_version, FAIL=summary[0], WARN=summary[1], PASS=summary[2]),
                    sha256={k: sha256(v) for k, v in files.items()})
    tmp = dst + '.tmp'
    with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_STORED) as z:        # JPEG / PNG are compressed already
        for k, v in files.items():
            z.write(v, k)
        z.writestr('manifest.json', json.dumps(manifest, ensure_ascii=False, indent=1))
    os.replace(tmp, dst)
    return dst


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
    try:
        print('階段 1 交付：' + stage1(a.img, a.out, a.name, tuple(map(int, m[-1])), v.group(1) if v else '?', report))
    except ValueError as error:
        print(f'不能交付：{error}'); return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
