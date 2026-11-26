#!/usr/bin/env python3
"""client_report.py — 給（內部）客戶看的進度與各階段圖，全部中文，彙整成 OUT/client/index.html

用法:
    python client_report.py IMG_DIR OUT_DIR [--name body] [--blender BLENDER] [--no-render]

run_all.py 每一步開始與結束都更新一次（--no-render，只更新進度和已有的圖），全部結束時（包括中途停止）
再完整產生一次（含 Blender 渲染的原圖對模型）。也可以單獨對既有的輸出目錄執行。未通過與需複核的項目全部列出。
    index.html            進度（4 個階段、18 個步驟、已用時間）、驗收總表、各階段的圖與清單
    01_photos.jpg         階段 1 照片：33 張總覽（水平、俯角、仰角、頭部特寫、俯視）
    02_head_review.png    階段 2 重建：全身照與頭部特寫的頭部對照（照片檢查產生）
    02_head_overlap.png   階段 2 重建：頭部回投到正面的疊圖
    03_preview.jpg        階段 3 模型：正面 / 3/4 / 側面 / 背面渲染
    04_body_compare.jpg   階段 4 成品對照：水平 8 個角度，左原圖、右模型（同一組相機）
    05_head_compare.jpg   階段 4 成品對照：8 張頭部特寫，左原圖、右模型
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
# the 18 steps of run_all.py, in Chinese, and the client stage each belongs to
STEP_ZH = {'check': '照片檢查', 'cams': '去背、建立相機', 'refine': '微調相機與外形', 'arms': '重建手臂',
           'round': '外形圓滑', 'legs': '雕刻腿部', 'mesh': '產生網格', 'headreg': '頭部特寫對位',
           'face': '臉部特徵點', 'face3d': '臉部立體與對位', 'uv': '展開貼圖座標', 'bake': '烘焙前檢查、烘焙貼圖',
           'export': '匯出模型', 'joints': '量測關節', 'rig': '建立骨架', 'unlit': '無光照材質',
           'verify': '模型檔驗證', 'fit': '成品與原圖比對'}
STAGE_OF = {'check': 1, 'cams': 2, 'refine': 2, 'arms': 2, 'round': 2, 'legs': 2, 'mesh': 2, 'headreg': 2, 'face': 2,
            'face3d': 2, 'uv': 2, 'bake': 3, 'export': 3, 'joints': 3, 'rig': 3, 'unlit': 3, 'verify': 3, 'fit': 4}
STAGES = {1: ('照片', '1 照片檢查', '成果：33 張照片。照片檢查全部通過才是好的成果；有未通過時流程停在這裡，照片照樣打包（標 _FAIL），要重畫照片。'),
          2: ('重建', '2 烘焙前檢查', '成果：相機與人體形狀。由照片算出相機和外形，再確認全身照和頭部特寫的頭部對得上（五官位置、亮度）。'),
          3: ('模型', '3 GLB 驗證', '成果：兩個模型檔（GLB）。烘焙貼圖、建立骨架、匯出，並驗證檔案結構、骨架與材質。'),
          4: ('成品驗收', '4 最終驗收', '成果：原圖對模型的對照。用拍原圖的同一組相機拍模型：左邊原圖、右邊模型，兩邊應該一樣。')}
LEVEL_ZH = {'FAIL': '未通過', 'WARN': '需複核', 'PASS': '通過'}
GATE_ZH = {'1 照片檢查': '照片檢查', '2 烘焙前檢查': '烘焙前檢查', '3 GLB 驗證（unlit）': '模型檔驗證（無光照版）',
           '3 GLB 驗證（lit）': '模型檔驗證（一般版）', '4 最終驗收': '成品與原圖比對'}
FONTS = ['/System/Library/Fonts/STHeiti Medium.ttc', '/System/Library/Fonts/Hiragino Sans GB.ttc',
         '/System/Library/Fonts/PingFang.ttc', '/Library/Fonts/Arial Unicode.ttf',
         '/System/Library/Fonts/Supplemental/Arial Unicode.ttf',
         '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc', '/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc',
         '/usr/share/fonts/truetype/wqy/wqy-microhei.ttc', 'C:/Windows/Fonts/msjh.ttc', 'C:/Windows/Fonts/msyh.ttc']
_font = {}


def font(px):
    """a Chinese-capable font (Pillow), or None: the label is then left out (index.html still names every image)"""
    if px not in _font:
        _font[px] = None
        try:
            from PIL import ImageFont
            for f in FONTS:
                if os.path.exists(f):
                    _font[px] = ImageFont.truetype(f, px)
                    break
        except ImportError:
            pass
    return _font[px]


def put_label(im, text, px=22, color=(40, 40, 40)):
    f = font(px)
    if f is None:
        return im
    from PIL import Image, ImageDraw
    pil = Image.fromarray(cv2.cvtColor(im, cv2.COLOR_BGR2RGB))
    d = ImageDraw.Draw(pil)
    d.text((4, 4), text, font=f, fill=color[::-1])
    return cv2.cvtColor(np.asarray(pil), cv2.COLOR_RGB2BGR)


def tile(path, w, label=None):
    im = cv2.imread(path) if path and os.path.exists(path) else None
    missing = im is None
    if missing:
        im = np.full((w, w, 3), 235, np.uint8)
    h = int(im.shape[0] * w / im.shape[1])
    im = cv2.resize(im, (w, h), interpolation=cv2.INTER_AREA)
    if label or missing:                               # caption strip above the picture, never over it
        im = cv2.copyMakeBorder(im, 32, 0, 0, 0, cv2.BORDER_CONSTANT, value=WHITE)
        im = put_label(im, (label or '') + ('（缺少）' if missing else ''), color=(0, 0, 200) if missing else (40, 40, 40))
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
    rows = [[tile(os.path.join(img, f + '.jpg'), w, f'水平 {a}°') for f, a in zip(MAIN, ANGLES)]]
    for ring, lab in (('el30', '俯角 30°'), ('low20', '仰角 20°'), ('head', '頭部')):
        rows.append([tile(os.path.join(img, f'{ring}_{a:03d}deg.jpg'), w, f'{lab} {a}°') for a in ANGLES])
    rows.append([tile(os.path.join(img, 'top.jpg'), w, '俯視')])
    cv2.imwrite(dst, grid(rows), [cv2.IMWRITE_JPEG_QUALITY, 88])


def compare_sheet(pairs, dst, w=320):
    """pairs of (photo, render, angle label): photo left, model right, four pairs per row"""
    tiles = []
    for p, r, lab in pairs:
        a = tile(p, w, f'原圖 {lab}')
        tiles.append(np.hstack([a, tile(r, w, f'模型 {lab}')[:a.shape[0]]]))
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


def make_images(a, cdir, render):
    made = {1: [], 2: [], 3: [], 4: []}
    if os.path.isdir(a.img):
        photo_sheet(a.img, os.path.join(cdir, '01_photos.jpg')); made[1].append('01_photos.jpg')
    for src, dst in ((os.path.join(a.out, 'turnaround_report_head_review.png'), '02_head_review.png'),
                     (os.path.join(a.out, 'view_overlays', 'head_front.png'), '02_head_overlap.png')):
        if os.path.exists(src):
            shutil.copy(src, os.path.join(cdir, dst)); made[2].append(dst)
    prev = [next((p for p in (os.path.join(a.out, f'v2_{v}_FLAT.png'), os.path.join(a.out, 'work', f'v2_{v}_FLAT.png'))
                  if os.path.exists(p)), None) for v in ('front', 'three_q', 'side', 'back')]
    if any(prev):
        labels = ('正面', '3/4', '側面', '背面')
        cv2.imwrite(os.path.join(cdir, '03_preview.jpg'), grid([[tile(p, 300, l) for p, l in zip(prev, labels)]]),
                    [cv2.IMWRITE_JPEG_QUALITY, 88])
        made[3].append('03_preview.jpg')
    glb = os.path.join(a.out, f'{a.name}_rigged.glb')
    have = [f for f in ('04_body_compare.jpg', '05_head_compare.jpg') if os.path.exists(os.path.join(cdir, f))]
    if render and os.path.exists(glb) and a.blender:
        rdir = os.path.join(a.out, 'work', 'client_renders')
        r = subprocess.run([a.blender, '-b', '--factory-startup', '--python-exit-code', '1', '--python',
                            os.path.join(HERE, 'steps', 'bl_client_render.py'), '--', glb, rdir, '1024'],
                           capture_output=True, text=True)
        if r.returncode == 0:
            compare_sheet([(os.path.join(a.img, f + '.jpg'), os.path.join(rdir, f'main_{ang:03d}.png'), f'{ang}°')
                           for f, ang in zip(MAIN, ANGLES)], os.path.join(cdir, '04_body_compare.jpg'))
            compare_sheet([(os.path.join(a.img, f'head_{ang:03d}deg.jpg'), os.path.join(rdir, f'head_{ang:03d}.png'),
                            f'頭部 {ang}°') for ang in ANGLES], os.path.join(cdir, '05_head_compare.jpg'))
            have = ['04_body_compare.jpg', '05_head_compare.jpg']
        else:
            print('client_report: Blender 渲染失敗:\n' + r.stdout[-1500:] + r.stderr[-1500:])
    made[4] += have
    return made


def main(argv=None):
    ap = argparse.ArgumentParser(description='給客戶看的進度與各階段圖')
    ap.add_argument('img'); ap.add_argument('out')
    ap.add_argument('--name', default='body')
    ap.add_argument('--blender', default=os.environ.get('BLENDER') or shutil.which('blender'))
    ap.add_argument('--no-render', action='store_true', help='不跑 Blender（流程進行中的進度更新用）')
    a = ap.parse_args(argv)
    cdir = os.path.join(a.out, 'client'); os.makedirs(cdir, exist_ok=True)
    made = make_images(a, cdir, not a.no_render)
    load = lambda f: json.load(open(f)) if os.path.exists(f) else None
    write_html(cdir, a, made, load(os.path.join(a.out, 'gates.json')) or {},
               load(os.path.join(a.out, 'fit_report.json')), gate_sections(os.path.join(a.out, 'run_all.log')),
               load(os.path.join(a.out, 'progress.json')))
    if not a.no_render:
        print(f'client_report: {os.path.join(cdir, "index.html")}')
    return 0


def fmt_time(s):
    s = int(round(s or 0))
    return f'{s // 60} 分 {s % 60:02d} 秒' if s >= 60 else f'{s} 秒'


def progress_html(prog, gates_seen):
    """4 stage chips and the 18-step list from run_all's progress.json"""
    e = html.escape
    if not prog:
        return ['<p class="meta">（沒有進度紀錄：這份報告是單獨產生的）</p>'], False
    steps = prog.get('steps', [])
    state = prog.get('state', 'running')
    running = state == 'running'
    done = sum(s['status'] == 'done' for s in steps)
    head = {'running': '進行中', 'done': '已完成', 'stopped': '已停止'}[state]
    el = (prog.get('finished') or datetime.datetime.now().timestamp()) - prog.get('started', 0)
    why = ''
    if state == 'stopped':
        at = prog.get('stopped_at', '')
        gate = {'check': '1', 'bake': '2', 'verify': '3', 'fit': '4'}.get(at)
        nf = sum(v['FAIL'] for k, v in gates_seen.items() if gate and k.startswith(gate))
        fix = {'check': '見下方「要修的項目」的診斷', 'bake': '見下方「要修的項目」的診斷：每一項是照片或程式',
               'verify': '模型檔有問題，交給 AI 改程式（見 AI 改 code 單）', 'fit': '模型和原圖對不上，見階段 4 的對照圖與清單'}.get(at, '')
        why = (f'停在「{STEP_ZH.get(at, at)}」：' + (f'{nf} 項未通過，{fix}' if nf else '程式執行出錯，交給 AI 改程式（附 run_all.log）')
               + '。停下前做出來的東西都已打包，見下方各階段的成果')
    tick = (f'<span id="el" data-start="{prog.get("started", 0)}">{fmt_time(el)}</span>' if running else fmt_time(el))
    out = [f'<p class="prog"><b>{head}</b>　{done} / {len(steps)} 步　已用 {tick}'
           + (f'<br><span class="bad">{e(why)}</span>' if why else '') + '</p>']
    bar = []
    stop_stage = prog.get('stopped_stage')
    for n, (title, gate, _) in STAGES.items():
        ss = [s for s in steps if STAGE_OF.get(s['name']) == n]
        if stop_stage is not None and state == 'stopped':      # the stage the run stopped in (pre-bake: stage 2)
            st = 'bad' if n == stop_stage else 'ok' if n < stop_stage else 'wait'
            word = {'bad': '停止', 'ok': '完成', 'wait': '未開始'}[st]
            bar.append(f'<div class="chip {st}"><div class="n">階段 {n}</div><div>{e(title)}</div><div class="w">{word}</div></div>')
            continue
        if not ss:
            st = 'skip'
        elif any(s['status'] == 'failed' for s in ss):
            st = 'bad'
        elif any(s['status'] == 'running' for s in ss):
            st = 'run'
        elif all(s['status'] == 'done' for s in ss):
            st = 'ok'
        else:
            st = 'wait'
        gate_fail = any(g.startswith(gate[0]) and v['FAIL'] for g, v in gates_seen.items())
        if st == 'ok' and gate_fail:
            st = 'warnok'
        word = {'skip': '本次未跑', 'bad': '停止', 'run': '進行中', 'ok': '完成', 'wait': '未開始',
                'warnok': '完成，但有未通過'}[st]
        bar.append(f'<div class="chip {st}"><div class="n">階段 {n}</div><div>{e(title)}</div><div class="w">{e(word)}</div></div>')
    out.append('<div class="bar">' + ''.join(bar) + '</div>')
    rows = []
    for i, s in enumerate(steps, 1):
        word = {'done': '完成', 'running': '進行中', 'failed': '停止', 'pending': '未開始'}[s['status']]
        t = fmt_time(s['seconds']) if s.get('seconds') is not None else ''
        rows.append(f'<tr class="{s["status"]}"><td>{i}</td><td>{e(STEP_ZH.get(s["name"], s["name"]))}</td>'
                    f'<td>階段 {STAGE_OF.get(s["name"], "")}</td><td>{word}</td><td>{t}</td></tr>')
    out.append(f'<details{" open" if running else ""}><summary>全部步驟</summary><table class="steps"><tr><th>#</th><th>步驟</th><th>階段</th>'
               '<th>狀態</th><th>時間</th></tr>' + ''.join(rows) + '</table></details>')
    return out, running


def write_html(cdir, a, made, gates, fit, issues, prog):
    e = html.escape
    g = gates.get('gates', {})
    try:
        import run_all
        ver = run_all.__version__
    except Exception:
        ver = '?'
    body = [f'<h1>Avatar 製作進度與驗收</h1><p class="meta">照片 {e(os.path.basename(os.path.abspath(a.img)))} · '
            f'輸出 {e(os.path.basename(os.path.abspath(a.out)))} · 流程版本 {e(ver)} · '
            f'更新時間 {datetime.datetime.now():%Y-%m-%d %H:%M}'
            + (f' · 程式 commit {e(str((prog or {}).get("code", {}).get("commit") or "?")[:7])}'
               + ('（有未提交的改動）' if (prog or {}).get('code', {}).get('dirty') else '') if prog else '') + '</p>']
    prog_html, running = progress_html(prog, g)
    body += prog_html
    if not running and gates:
        ok = gates.get('deliverable')
        word = '可以交付' if ok else '不能交付（有未通過；做出來的東西都已打包，標 _FAIL）'
        body.append(f'<p class="status {"ok" if ok else "bad"}">{e(word)}</p>')
    todo = [(k, t) for k, lst in issues.items() for l, t in lst if l == 'FAIL']
    dpath = os.path.join(a.out, 'diagnosis.json')
    leaves = json.load(open(dpath)) if os.path.exists(dpath) else []
    if todo:                                           # what has to be fixed, before anything else
        diag = ''
        if leaves:                                     # the diagnosis tree's answer: who fixes what, and why
            leaves = sorted(leaves, key=lambda d: d.get('order', 99))
            diag = ('<p><b>診斷（照修的順序：前面階段先修，同階段信心高的先修）</b></p><ol class="diag">' + ''.join(
                f"<li>{'<b>先修這一項</b> ' if i == 0 else ''}<span class='g'>{e(d.get('stage_name', ''))}</span> "
                f"<span class='own {'p' if d['owner'] == '照片' else 'c'}'>{e(d['owner'])}</span>"
                f"<span class='conf'>信心{e(d['confidence'])}</span> <b>{e(d['item'])}</b>：{e(d['cause'])}"
                f"<br>怎麼修：{e(d['action'])}<br><span class='g'>路徑：{e(' → '.join(d['path']))}</span></li>"
                for i, d in enumerate(leaves)) + '</ol>')
        req = os.path.join(a.out, 'ai_fix_request', 'AI修圖單.md')
        if os.path.exists(req):                        # photo problems: what to hand to the AI
            n_ph = len(os.listdir(os.path.join(a.out, 'ai_fix_request', 'photos')))
            diag += (f'<p class="deliver fixed"><b>AI 修圖單</b>：{n_ph} 張照片要請 AI 重畫，'
                     '<a href="../ai_fix_request/AI修圖單.md">AI修圖單.md</a>（附原圖與「應該的樣子」參考圖，'
                     '也在結果包的 ai_fix_request/）</p>')
        creq = os.path.join(a.out, 'ai_code_request', 'AI改code單.md')
        if os.path.exists(creq):                       # program problems: what to hand to the coding AI
            diag += ('<p class="deliver fixed"><b>AI 改 code 單</b>：程式的問題交給 AI 改程式，'
                     '<a href="../ai_code_request/AI改code單.md">AI改code單.md</a>（原因、數字、要補的檢查、要改的檔、驗收方式；'
                     '也在結果包的 ai_code_request/）</p>')
        body.append('<div class="todo"><b>要修的項目（' + str(len(todo)) + ' 項未通過）</b>' + diag
                    + '<details><summary>未通過項目原文</summary><ol>'
                    + ''.join(f'<li><span class="g">{e(GATE_ZH.get(k, k))}</span>　{e(t)}</li>' for k, t in todo)
                    + '</ol></details></div>')
    if g:
        rows = ''.join(f'<tr><td>{e(GATE_ZH.get(k, k))}</td><td class="{"f" if v["FAIL"] else ""}">{v["FAIL"]}</td>'
                       f'<td>{v["WARN"]}</td><td>{v["PASS"]}</td><td>{v["TOTAL"]}</td></tr>' for k, v in g.items())
        body.append('<h2>驗收總表</h2><table><tr><th>關卡</th><th>未通過</th><th>需複核</th><th>通過</th><th>共計</th></tr>'
                    + rows + '</table>')
    if fit and 'mean' in fit:
        body.append(f'<p>成品與原圖的剪影吻合度 <b>{100 * (1 - fit["mean"]):.1f}%</b>（24 張全身圖平均；'
                    f'≥ 92% 通過，低於 90% 未通過）</p>')
    for n, (title, gate, desc) in STAGES.items():
        body.append(f'<h2>階段 {n}・{e(title)}</h2><p>{e(desc)}</p>')
        af = os.path.join(a.out, 'autofix.json')
        if n == 1 and os.path.exists(af):
            fx = json.load(open(af))['fixes']
            body.append('<div class="deliver fixed"><b>已自動修正 ' + str(len(fx)) + ' 張</b>（原檔沒動，修正後的照片另存；'
                        '每一項都用同一項檢查驗證過）<ul>' + ''.join(
                f"<li>第 {x['round']} 輪　{e(x['photo'])}　{e(x['kind'])}：平移 ({x['dx_px']:+.0f}, {x['dy_px']:+.0f}) px，"
                f"{x['before_mm']} → {x['after_mm']} mm</li>" for x in fx) + '</ul></div>')
        import deliver
        good, bad = deliver.zip_paths(a.out, a.name, n)
        for z, word, cls in ((good, '成果（好，可交付）', 'deliver'), (bad, '成果（有未通過，不好，不能交付）', 'deliver bad')):
            if os.path.exists(z):
                body.append(f'<p class="{cls}">{word}：<a href="../deliver/{e(os.path.basename(z))}">'
                            f'{e(os.path.basename(z))}</a>（{os.path.getsize(z) / 2 ** 20:.1f} MB，'
                            f'{e(deliver.STAGE_ZH[n])}與清單）</p>')
        if not (os.path.exists(good) or os.path.exists(bad)):
            body.append('<p class="deliver no">這個階段還沒做完，還沒有成果</p>')
        for f in made.get(n, []):
            body.append(f'<a href="{f}"><img src="{f}?v={int(os.path.getmtime(os.path.join(cdir, f)))}"></a>')
        if not made.get(n):
            body.append('<p class="meta">（還沒有這個階段的圖）</p>')
        for k, lst in ((k, v) for k, v in issues.items() if k.startswith(gate[0])):
            nf = sum(l == 'FAIL' for l, _ in lst); nw = len(lst) - nf
            body.append(f'<details{" open" if nf else ""}><summary>{e(GATE_ZH.get(k, k))}：{nf} 項未通過、{nw} 項需複核'
                        '</summary><ul>' + ''.join(f'<li class="{l.lower()}"><b>{LEVEL_ZH[l]}</b> {e(t)}</li>'
                                                    for l, t in sorted(lst, key=lambda x: x[0] != 'FAIL'))
                        + '</ul></details>')
    css = ('body{font-family:-apple-system,"PingFang TC","Microsoft JhengHei",sans-serif;max-width:1400px;margin:24px auto;'
           'padding:0 16px;color:#222}img{max-width:100%;border:1px solid #ddd;margin:6px 0}.meta{color:#777;font-size:13px}'
           '.status{color:#fff;display:inline-block;padding:6px 14px;border-radius:6px;font-weight:600}'
           '.prog{font-size:17px}.bad{color:#b3261e}.status.ok{background:#1b7f3b;color:#fff}.status.bad{background:#b3261e;color:#fff}'
           '.bar{display:flex;gap:8px;margin:8px 0 12px}.chip{flex:1;border-radius:8px;padding:8px 12px;background:#eee;color:#555}'
           '.chip .n{font-size:12px}.chip .w{font-weight:600;margin-top:2px}.chip.ok{background:#e3f4e8;color:#1b7f3b}'
           '.chip.run{background:#fff4d6;color:#8a5a00}.chip.bad{background:#fde7e5;color:#b3261e}'
           '.chip.warnok{background:#fde7e5;color:#b3261e}.chip.skip{background:#f4f4f4;color:#aaa}'
           'table{border-collapse:collapse}td,th{border:1px solid #ccc;padding:4px 10px;text-align:right}'
           'td:first-child,th:first-child{text-align:left}td.f{color:#b3261e;font-weight:700}'
           '.steps td:nth-child(2),.steps td:nth-child(3),.steps td:nth-child(4){text-align:left}'
           'tr.running td{background:#fff4d6}tr.failed td{background:#fde7e5}tr.pending td{color:#aaa}'
           '.deliver{background:#e3f4e8;padding:6px 10px;border-radius:6px}.deliver.no{background:#f4f4f4;color:#777}.deliver.bad{background:#fde7e5;color:#b3261e}.deliver.fixed{background:#eef4ff;color:#1a3d7c}'
           '.todo{border:2px solid #b3261e;background:#fff5f4;border-radius:8px;padding:8px 14px;margin:10px 0}'
           '.todo b{color:#b3261e}.todo .g{color:#777;font-size:13px}.todo li{font-size:15px;margin:6px 0}'
           '.own{color:#fff;border-radius:4px;padding:1px 6px;margin-right:6px;font-size:13px}.own.p{background:#a66300}.own.c{background:#1a3d7c}'
           '.conf{color:#555;font-size:13px;margin-right:6px}'
           'li.fail b{color:#b3261e}li.warn b{color:#a66300}li{margin:3px 0;font-size:14px}summary{cursor:pointer;margin:6px 0}')
    refresh = '<meta http-equiv="refresh" content="20">' if running else ''
    if running:                                        # elapsed time ticks between the 20 s reloads
        body.append('<script>const el=document.getElementById("el");if(el)setInterval(()=>{const s=Math.round('
                    'Date.now()/1000-el.dataset.start);el.textContent=s>=60?`${Math.floor(s/60)} 分 '
                    '${String(s%60).padStart(2,"0")} 秒`:`${s} 秒`},1000)</script>')
    tmp = os.path.join(cdir, 'index.html.tmp')
    open(tmp, 'w', encoding='utf-8').write(
        f'<!DOCTYPE html><html lang="zh-Hant"><head><meta charset="utf-8">{refresh}<title>Avatar 製作進度與驗收</title>'
        f'<style>{css}</style></head><body>' + '\n'.join(body) + '</body></html>')
    os.replace(tmp, os.path.join(cdir, 'index.html'))          # a viewer never sees a half-written page


if __name__ == '__main__':
    sys.exit(main())
