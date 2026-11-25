#!/usr/bin/env python3
"""client_report.py — 每個階段給（內部）客戶看的圖，彙整成 OUT/client/index.html

用法:
    python client_report.py IMG_DIR OUT_DIR [--name body] [--blender BLENDER]

run_all.py 結束時（包括中途停止）自動執行；也可以單獨對既有的輸出目錄執行。FAIL 和 WARN 都列出來，不隱藏。
    01_photos.jpg         階段 1 照片：33 張總覽（主環、俯角、仰角、頭部特寫、俯視）
    02_head_review.png    階段 2 烘焙前：全身與頭部特寫的頭部對照（checker 產生）
    02_head_overlap.png   階段 2 烘焙前：頭部回投到正面的疊圖
    03_preview.jpg        階段 3 模型：正面 / 3/4 / 側面 / 背面渲染
    04_body_compare.jpg   階段 4 成品對照：主環 8 個角度，左原圖、右模型（規格相機）
    05_head_compare.jpg   階段 4 成品對照：8 張頭部特寫，左原圖、右模型
    index.html            上面所有圖、驗收總表、每道關卡的 FAIL / WARN 清單、吻合度
"""
import argparse
import datetime
import html
import json
import os
import re
import shutil
import subprocess
import sys

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, 'steps'))
MAIN = ['01_000deg_front', '02_045deg_front_left', '03_090deg_left', '04_135deg_back_left', '05_180deg_back',
        '06_225deg_back_right', '07_270deg_right', '08_315deg_front_right']
ANGLES = list(range(0, 360, 45))
WHITE = (255, 255, 255)


def tile(path, w, label=None):
    im = cv2.imread(path) if path and os.path.exists(path) else None
    if im is None:
        im = np.full((w, w, 3), 235, np.uint8)
        cv2.putText(im, 'missing', (10, w // 2), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 200), 2)
    h = int(im.shape[0] * w / im.shape[1])
    im = cv2.resize(im, (w, h), interpolation=cv2.INTER_AREA)
    if label:
        cv2.putText(im, label, (8, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (40, 40, 40), 2, cv2.LINE_AA)
    return im


def grid(rows, gap=6):
    """rows of tiles -> one image (rows padded to the widest, tiles to the tallest of their row)"""
    out = []
    for r in rows:
        h = max(t.shape[0] for t in r)
        r = [cv2.copyMakeBorder(t, 0, h - t.shape[0], 0, gap, cv2.BORDER_CONSTANT, value=WHITE) for t in r]
        out.append(np.hstack(r))
    w = max(r.shape[1] for r in out)
    out = [cv2.copyMakeBorder(r, 0, gap, 0, w - r.shape[1], cv2.BORDER_CONSTANT, value=WHITE) for r in out]
    return np.vstack(out)


def photo_sheet(img, dst, w=200):
    rows = [[tile(os.path.join(img, f + '.jpg'), w, f'{a}') for f, a in zip(MAIN, ANGLES)]]
    for ring, lab in (('el30', '+30'), ('low20', '-20'), ('head', 'head')):
        rows.append([tile(os.path.join(img, f'{ring}_{a:03d}deg.jpg'), w, f'{lab} {a}') for a in ANGLES])
    rows.append([tile(os.path.join(img, 'top.jpg'), w, 'top')])
    cv2.imwrite(dst, grid(rows), [cv2.IMWRITE_JPEG_QUALITY, 88])


def compare_sheet(pairs, dst, w=320):
    """pairs of (photo, render, label): photo left, model right, four pairs per row"""
    tiles = [np.hstack([tile(p, w, lab), tile(r, w, 'model')[:tile(p, w).shape[0]]]) for p, r, lab in pairs]
    cv2.imwrite(dst, grid([tiles[i:i + 4] for i in range(0, len(tiles), 4)], gap=14), [cv2.IMWRITE_JPEG_QUALITY, 88])


def gate_sections(log):
    """the last run of each gate in run_all.log -> {gate: [(level, line)]}"""
    if not os.path.exists(log):
        return {}
    out = {}
    for part in open(log, errors='replace').read().split('\n$ ')[1:]:
        cmd = part.split('\n', 1)[0]
        if 'check_turnaround.py' in cmd:
            g = '2 烘焙前檢查' if '--head-overlap-work' in cmd else '1 照片檢查'
        elif 'verify_glb.py' in cmd:
            g = '3 GLB 驗證（unlit）' if '--expect-unlit' in cmd else '3 GLB 驗證（lit）'
        elif 'fit_report.py' in cmd:
            g = '4 最終驗收'
        else:
            continue
        out[g] = [(m.group(1), m.group(2).strip()) for m in re.finditer(r'^\s*\[(FAIL|WARN)\]\s*(.*)$', part, re.M)]
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description='每個階段給客戶看的圖')
    ap.add_argument('img'); ap.add_argument('out')
    ap.add_argument('--name', default='body')
    ap.add_argument('--blender', default=os.environ.get('BLENDER') or shutil.which('blender'))
    a = ap.parse_args(argv)
    cdir = os.path.join(a.out, 'client'); os.makedirs(cdir, exist_ok=True)
    made = {}

    photo_sheet(a.img, os.path.join(cdir, '01_photos.jpg')); made[1] = ['01_photos.jpg']
    made[2] = []
    for src, dst in ((os.path.join(a.out, 'turnaround_report_head_review.png'), '02_head_review.png'),
                     (os.path.join(a.out, 'view_overlays', 'head_front.png'), '02_head_overlap.png')):
        if os.path.exists(src):
            shutil.copy(src, os.path.join(cdir, dst)); made[2].append(dst)
    made[3] = []
    prev = [next((p for p in (os.path.join(a.out, f'v2_{v}_FLAT.png'), os.path.join(a.out, 'work', f'v2_{v}_FLAT.png'))
                  if os.path.exists(p)), None) for v in ('front', 'three_q', 'side', 'back')]
    if any(prev):
        cv2.imwrite(os.path.join(cdir, '03_preview.jpg'), grid([[tile(p, 300) for p in prev]]), [cv2.IMWRITE_JPEG_QUALITY, 88])
        made[3].append('03_preview.jpg')
    made[4] = []
    glb = os.path.join(a.out, f'{a.name}_rigged.glb')
    if os.path.exists(glb) and a.blender:
        rdir = os.path.join(a.out, 'work', 'client_renders')
        r = subprocess.run([a.blender, '-b', '--factory-startup', '--python-exit-code', '1', '--python',
                            os.path.join(HERE, 'steps', 'bl_client_render.py'), '--', glb, rdir, '1024'],
                           capture_output=True, text=True)
        if r.returncode == 0:
            compare_sheet([(os.path.join(a.img, f + '.jpg'), os.path.join(rdir, f'main_{ang:03d}.png'), f'{ang}')
                           for f, ang in zip(MAIN, ANGLES)], os.path.join(cdir, '04_body_compare.jpg'))
            compare_sheet([(os.path.join(a.img, f'head_{ang:03d}deg.jpg'), os.path.join(rdir, f'head_{ang:03d}.png'),
                            f'head {ang}') for ang in ANGLES], os.path.join(cdir, '05_head_compare.jpg'))
            made[4] += ['04_body_compare.jpg', '05_head_compare.jpg']
        else:
            print('client_report: Blender render failed:\n' + r.stdout[-1500:] + r.stderr[-1500:])

    gj = os.path.join(a.out, 'gates.json')
    gates = json.load(open(gj)) if os.path.exists(gj) else {}
    fitj = os.path.join(a.out, 'fit_report.json')
    fit = json.load(open(fitj)) if os.path.exists(fitj) else None
    issues = gate_sections(os.path.join(a.out, 'run_all.log'))
    write_html(cdir, a, made, gates, fit, issues)
    print(f'client_report: {os.path.join(cdir, "index.html")}')
    return 0


STAGES = {1: ('階段 1 · 照片', '1 照片檢查', '33 張輸入照片。照片檢查有 FAIL 時要重畫照片，模型不會做。'),
          2: ('階段 2 · 烘焙前（頭部）', '2 烘焙前檢查', '重建後，全身照與頭部特寫的頭部是否對得上（五官位置、亮度）。'),
          3: ('階段 3 · 模型', '3 GLB 驗證', 'GLB 的正面、3/4、側面、背面渲染，以及檔案結構、骨架、材質的驗證。'),
          4: ('階段 4 · 成品對照', '4 最終驗收', '模型用輸入照片的相機拍：左邊原圖、右邊模型，兩邊應該一樣。')}


def write_html(cdir, a, made, gates, fit, issues):
    e = html.escape
    g = gates.get('gates', {})
    deliverable = gates.get('deliverable')
    status = ('可交付' if deliverable else '不可交付' + ('（用了 --force，只供診斷）' if gates.get('force') else ''))
    color = '#1b7f3b' if deliverable else '#b3261e'
    try:
        import run_all
        ver = run_all.__version__
    except Exception:
        ver = '?'
    rows = ''.join(f'<tr><td>{e(k)}</td><td class="{"f" if v["FAIL"] else ""}">{v["FAIL"]}</td><td>{v["WARN"]}</td>'
                   f'<td>{v["PASS"]}</td><td>{v["TOTAL"]}</td></tr>' for k, v in g.items())
    body = [f'<h1>Avatar 驗收報告</h1><p class="meta">照片 {e(os.path.basename(os.path.abspath(a.img)))} · 輸出 {e(os.path.basename(os.path.abspath(a.out)))} · '
            f'body3d {e(ver)} · {datetime.datetime.now():%Y-%m-%d %H:%M}</p>',
            f'<p class="status" style="background:{color}">{e(status)}</p>',
            '<table><tr><th>關卡</th><th>FAIL</th><th>WARN</th><th>PASS</th><th>共計</th></tr>' + rows + '</table>']
    if fit and 'mean' in fit:
        body.append(f'<p>成品與原圖剪影吻合度 <b>{100 * (1 - fit["mean"]):.1f}%</b>（24 張全身圖平均；'
                    f'≥ 92% 通過，< 90% 判 FAIL）</p>')
    for n, (title, gate, desc) in STAGES.items():
        body.append(f'<h2>{e(title)}</h2><p>{e(desc)}</p>')
        for f in made.get(n, []):
            body.append(f'<a href="{f}"><img src="{f}"></a>')
        if not made.get(n):
            body.append('<p class="meta">（這次沒有跑到這個階段）</p>')
        found = [(k, lst) for k, lst in issues.items() if k.startswith(gate)]
        for k, lst in found:
            nf = sum(l == 'FAIL' for l, _ in lst); nw = len(lst) - nf
            body.append(f'<details{" open" if nf else ""}><summary>{e(k)}：{nf} 個 FAIL、{nw} 個 WARN</summary><ul>'
                        + ''.join(f'<li class="{l.lower()}"><b>{l}</b> {e(t)}</li>' for l, t in lst) + '</ul></details>')
    css = ('body{font-family:-apple-system,"PingFang TC",sans-serif;max-width:1400px;margin:24px auto;padding:0 16px;color:#222}'
           'img{max-width:100%;border:1px solid #ddd;margin:6px 0}.meta{color:#777;font-size:13px}'
           '.status{color:#fff;display:inline-block;padding:6px 14px;border-radius:6px;font-weight:600}'
           'table{border-collapse:collapse}td,th{border:1px solid #ccc;padding:4px 10px;text-align:right}'
           'td:first-child,th:first-child{text-align:left}td.f{color:#b3261e;font-weight:700}'
           'li.fail b{color:#b3261e}li.warn b{color:#a66300}li{margin:3px 0;font-size:14px}summary{cursor:pointer;margin:6px 0}')
    open(os.path.join(cdir, 'index.html'), 'w', encoding='utf-8').write(
        f'<!DOCTYPE html><html lang="zh-Hant"><head><meta charset="utf-8"><title>Avatar 驗收報告</title>'
        f'<style>{css}</style></head><body>' + '\n'.join(body) + '</body></html>')


if __name__ == '__main__':
    sys.exit(main())
