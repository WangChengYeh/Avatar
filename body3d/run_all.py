#!/usr/bin/env python3
"""
run_all.py — 33 張 T-pose 環繞照片 → 附骨架、有貼圖的 GLB（整條流程一支 Python 指令）

用法:
    python run_all.py IMG_DIR OUT_DIR [--name body] [--blender /path/to/blender] [--force] [--from STEP] [--only STEP]

關卡有 FAIL 就停（--force 才繼續，供診斷）。停或不停，做出來的東西都打包成各階段的成果（docs/SOP.md）：
該階段與之前的關卡全部 0 FAIL 是好的 zip，否則是 _FAIL.zip（停下的那個階段有多少給多少）。
結束碼：全部完成且 0 FAIL 為 0，其餘為 1。

步驟（每一步都是 Python；Blender 步驟以 `blender -b --python` 執行 Python 腳本）:
   1 check     check_turnaround.py 檢查照片規範；打包階段 1 成果（33 張照片）
   2 cams      去背、建立正交相機（cams33.py）
   3 refine    聯合微調相機 + 視覺外殼（refine33.py）
   4 arms      T-pose 手臂重建為橢圓柱（arms33.py）
   5 round     3D 開運算讓外形圓滑（round33.py）
   6 legs      腿部嚴格雕刻：兩腿之間的外殼殘留（legs33.py）
   7 mesh      Marching cubes + 平滑 + 減面 → body33s.ply（mesh33s.py）
   8 headreg   頭部特寫相機對位（headreg33.py），再把頭修到 8 張特寫的輪廓（headsil33.py）
   9 face      MediaPipe 臉部特徵點（face_landmarks.py，必要）
  10 face3d    用臉部特徵點對齊 3/4 頭部特寫相機、補出鼻子 / 眼窩（face33.py，必要）
  11 uv        Blender 展 UV（bl_uv33s.py）；--template makehuman：擬合 MakeHuman 人體（mh33.py）
  12 bake      頭部投影重疊檢查、多視角貼圖烘焙（bake33.py）
  13 export    Blender 匯出有貼圖的 GLB + 預覽圖（bl_export.py）
  14 joints    從網格量測關節位置（joints.py）
  15 rig       Blender 建 22 根骨頭、自動權重、匯出（rig.py）；makehuman 版跳過 14、15，第 13 步直接匯出含骨架 GLB
  16 unlit     材質標為 KHR_materials_unlit（glb_unlit.py）
  17 verify    verify_glb.py 驗證兩個 GLB（有 FAIL 時結束碼 1）
  18 fit       最終驗收：成品網格以最終相機投影回 24 張全身原圖，剪影平均不一致 > 10% 判 FAIL（fit_report.py --accept）

輸出（OUT_DIR）:
    {name}_rigged.glb        無光照材質（照片已含光影，建議用這個）
    {name}_rigged_lit.glb    一般 PBR 材質
    v2_*.png                 Blender 預覽圖
    gates.json               4 道關卡各自的 FAIL / WARN / PASS / 共計、deliverable（見 docs/SOP.md）
    client/index.html        給客戶看的進度與各階段圖（中文，每一步更新；client_report.py）
    progress.json            18 個步驟的狀態與時間
    deliver/{name}_stage1_photos.zip  階段 1 交付物：33 張照片 + 照片檢查報告 + manifest（照片檢查 0 FAIL）
    deliver/{name}_stage1_photos_FAIL.zip  照片檢查有 FAIL 時：一樣打包，不能交付，manifest 列出未通過項目
    turnaround_report.png    照片檢查報告；work/ 內是中間檔
"""
import argparse, json, os, shutil, subprocess, sys, time

__version__ = '2.19.1'
HERE = os.path.dirname(os.path.abspath(__file__))
AUTOFIX_ROUNDS = 3                 # photo-stage fix-and-check rounds (autofix.py)
STEPS_DIR = os.path.join(HERE, 'steps')
STEPS = ['check', 'cams', 'refine', 'arms', 'round', 'legs', 'mesh', 'headreg', 'face', 'face3d', 'uv', 'bake', 'export',
         'joints', 'rig', 'unlit', 'verify', 'fit']


def find_blender(given):
    for c in [given, os.environ.get('BLENDER'), shutil.which('blender'), '/opt/homebrew/bin/blender',
              '/Applications/Blender.app/Contents/MacOS/Blender', r'C:\Program Files\Blender Foundation\Blender\blender.exe']:
        if c and os.path.exists(c):
            return c
    return None


def run(cmd, cwd, log, ok_codes=(0,), show_output=False):
    print('   $', ' '.join(os.path.basename(c) if i < 2 else c for i, c in enumerate(cmd)), flush=True)
    t = time.time()
    with open(log, 'a+') as f:
        f.write('\n$ ' + ' '.join(cmd) + '\n'); f.flush()
        start = f.tell()
        p = subprocess.Popen(cmd, cwd=cwd, stdout=f, stderr=subprocess.STDOUT)
        peak = None
        if hasattr(os, 'wait4'):                      # peak memory of this step (the child and what it waited for)
            _, status, ru = os.wait4(p.pid, 0)
            rc = os.waitstatus_to_exitcode(status); p.returncode = rc
            peak = ru.ru_maxrss / (1 if sys.platform == 'darwin' else 1 / 1024) / 2 ** 30   # macOS: bytes, Linux: KiB
        else:
            rc = p.wait()
        if show_output:
            f.seek(start)
            print(f.read(), end='', flush=True)
        msg = f'({time.time() - t:.0f} s, exit {rc}' + (f', peak memory {peak:.2f} GiB' if peak is not None else '') + ')'
        f.write(f'STEP {os.path.basename(cmd[-1] if cmd[-1].endswith(".py") else cmd[1] if len(cmd) > 1 else cmd[0])} {msg}\n')
    print(f'     {msg}', flush=True)
    if rc not in ok_codes:
        tail = open(log, errors='replace').read().splitlines()[-25:]
        raise RuntimeError(f'步驟失敗（exit {rc}），log: {log}\n' + '\n'.join(tail))
    return rc


def code_version():
    """the git commit of this checkout (and whether body3d/ has uncommitted changes): which code made an output"""
    def git(*a):
        try:
            r = subprocess.run(['git', '-C', HERE, *a], capture_output=True, text=True, timeout=30)
            return r.stdout.strip() if r.returncode == 0 else ''
        except (OSError, subprocess.SubprocessError):
            return ''
    commit = git('rev-parse', 'HEAD')
    return dict(commit=commit or None, dirty=bool(git('status', '--porcelain', '--', HERE)), body3d=__version__,
                hash=code_hash())


def code_hash(root=HERE):
    """fingerprint of the code itself (every .py / .json under body3d/, committed or not): next_step reruns an output
    whose code_hash differs from the code now, and only then (uncommitted edits while fixing code are the same code)"""
    import hashlib
    h = hashlib.sha256()
    for d, dirs, files in sorted(os.walk(root)):
        dirs[:] = sorted(x for x in dirs if x != '__pycache__')
        for f in sorted(files):
            if f.endswith(('.py', '.json')):
                p = os.path.join(d, f)
                h.update(os.path.relpath(p, root).encode()); h.update(open(p, 'rb').read())
    return h.hexdigest()[:16]


def main(argv=None):
    ap = argparse.ArgumentParser(description=f'body3d run_all {__version__}')
    ap.add_argument('img_dir'); ap.add_argument('out_dir')
    ap.add_argument('--name', default='body')
    ap.add_argument('--blender')
    ap.add_argument('--force', action='store_true', help='關卡有 FAIL 也繼續做完（診斷用，之後的成果都標 _FAIL）')
    ap.add_argument('--no-autofix', action='store_true', help='照片檢查未通過時不自動修正')
    ap.add_argument('--from', dest='start', choices=STEPS, default='check')
    ap.add_argument('--only', choices=STEPS)
    ap.add_argument('--pose', choices=['tpose', 'apose'], default='tpose')
    ap.add_argument('--template', choices=['hull', 'makehuman'], default='hull',
                    help='hull：剪影外殼網格＋自動權重（原流程）；makehuman：把 MakeHuman 人體擬合到外殼，'
                         '用它的拓樸、Mixamo 骨架（含手指）與權重（需在 Blender 安裝 MPFB 擴充）')
    ap.add_argument('--version', action='version', version=f'body3d {__version__}')
    a = ap.parse_args(argv)

    img = os.path.abspath(a.img_dir); out = os.path.abspath(a.out_dir)
    if (a.start != 'check' or a.only) and a.only != 'check' and os.path.exists(os.path.join(out, 'autofix.json')):
        img = json.load(open(os.path.join(out, 'autofix.json')))['photos']     # resume with the fixed photos
    work = os.path.join(out, 'work'); os.makedirs(work, exist_ok=True)
    log = os.path.join(out, 'run_all.log')
    py = sys.executable
    S = lambda f: os.path.join(STEPS_DIR, f)
    blender = find_blender(a.blender)
    glb_tex = os.path.join(work, 'textured.glb')
    lit = os.path.join(out, f'{a.name}_rigged_lit.glb'); unlit = os.path.join(out, f'{a.name}_rigged.glb')

    def need_blender():
        if not blender:
            raise RuntimeError('找不到 Blender（4.2 以上）。用 --blender 指定路徑或設定環境變數 BLENDER')
        # --python-exit-code 1: an exception in the Blender script must fail the step (Blender exits 0 otherwise)
        return [blender, '-b', '--factory-startup', '--python-exit-code', '1', '--python']

    gates = {}                     # gate -> (FAIL, WARN, PASS) from each checker's own summary line
    fails = {}                     # gate -> its [FAIL] lines
    go_on = a.force
    packed = set()                 # stages whose result is zipped already
    diagnosis = []                 # leaves of the diagnosis tree for the FAILs (diagnose.py, docs/Diagnosis-Tree.md)

    def diagnose(gate):
        """walk the diagnosis tree for this gate's FAILs; print the leaves and keep them for the zip and the page"""
        try:
            import diagnose as dz
            leaves = (dz.diagnose_photo_fails(fails.get('1 照片檢查', [])) if gate == 1
                      else dz.diagnose_prebake(img, work, fails.get('2 烘焙前檢查', [])))
        except Exception as error:                     # the diagnosis must never hide the gate's own result
            print(f'     診斷樹失敗：{error}')
            return
        diagnosis[:] = dz.fix_order([d for d in diagnosis if d['gate'] != gate] + [dict(d, gate=gate) for d in leaves])
        for d in diagnosis:                            # in fix order: earlier stage first, then higher confidence
            print(f"     診斷 {d['order']}［{d['stage_name']}｜{d['owner']}｜信心{d['confidence']}］{d['item']}："
                  f"{d['cause']} → {d['action']}")
        json.dump(diagnosis, open(os.path.join(out, 'diagnosis.json'), 'w'), ensure_ascii=False, indent=1)
        try:                                           # photo problems go back to the AI: the retouch request
            import ai_request
            r = ai_request.make(img, out, diagnosis)
            if r:
                print(f'     AI 修圖單：{os.path.join(r, "AI修圖單.md")}')
            c = ai_request.make_code(out, diagnosis, img)   # program problems: only when no photo comes first
            if c:
                print(f'     AI 改 code 單：{os.path.join(c, "AI改code單.md")}')
        except Exception as error:
            print(f'     AI 修圖單失敗：{error}')

    def stage_files(stage):
        """what a stage produces (whatever of it exists when it is packed)"""
        if stage == 2:
            ov = os.path.join(out, 'view_overlays')
            return {'cams33.json': os.path.join(work, 'cams33.json'), os.path.basename(mesh_ply): mesh_ply,
                    'turnaround_report_head_review.png': os.path.join(out, 'turnaround_report_head_review.png'),
                    **{f'view_overlays/{f}': os.path.join(ov, f) for f in (os.listdir(ov) if os.path.isdir(ov) else [])}}
        if stage == 3:
            return {os.path.basename(unlit): unlit, os.path.basename(lit): lit,
                    **{f: os.path.join(out, f) for f in sorted(os.listdir(out)) if f.startswith('v2_') and f.endswith('.png')}}
        cdir = os.path.join(out, 'client')
        return {'fit_report.json': os.path.join(out, 'fit_report.json'), 'gates.json': os.path.join(out, 'gates.json'),
                '04_body_compare.jpg': os.path.join(cdir, '04_body_compare.jpg'),
                '05_head_compare.jpg': os.path.join(cdir, '05_head_compare.jpg')}

    def stage_zip(stage, stopped=None):
        """pack a stage's result, good or _FAIL (docs/SOP.md), with the gates of this stage and the earlier ones;
        stopped = (step, reason) when the run stopped inside this stage: whatever exists is packed, as _FAIL"""
        import deliver
        g = {k: v for k, v in gates.items() if int(k[0]) <= stage}
        dg = [d for d in diagnosis if d['gate'] <= stage]
        z, ok = deliver.pack(out, a.name, stage, stage_files(stage), g, [l for k in g for l in fails.get(k, [])],
                             extra=dict(diagnosis=dg) if dg else None,
                             stopped=stopped)
        packed.add(stage)
        print(f'     階段 {stage} 成果' + ('（好，可交付）：' if ok else '（不好，標 _FAIL）：') + z)

    def tally(gate):
        """read the summary line of the command run last (all checkers print the same format)"""
        import re
        if not os.path.exists(log):
            return
        txt = open(log, errors='replace').read().split('\n$ ')[-1]
        m = re.findall(r'總結: (\d+) 個 FAIL, (\d+) 個 WARN, (\d+) 個 PASS', txt)
        import deliver
        crashed = 'Traceback (most recent call last)' in txt or not m
        if crashed:
            # a checker that crashed has not checked: its exit code 1 looks like 'has a FAIL' and the counts of the
            # items it got through looked like a pass (MakeHuman run: pre-bake 0 FAIL after a crash). Always a FAIL.
            err = [l for l in txt.splitlines() if l.strip()][-1:] or ['（沒有輸出）']
            f, w, p_ = (tuple(int(x) for x in m[-1]) if m else (0, 0, 0))
            gates[gate] = (f + 1, w, p_)
            fails[gate] = deliver.fail_lines(txt) + [f'檢查程式出錯: {gate} 沒有檢查完（{err[0].strip()[:200]}）']
            print(f'     {gate}：檢查程式出錯，記為 FAIL（{err[0].strip()[:120]}）')
        else:
            gates[gate] = tuple(int(x) for x in m[-1])
            fails[gate] = deliver.fail_lines(txt)

    def gate_table():
        if not gates:
            return
        import unicodedata
        pad = lambda t, n: t + ' ' * max(0, n - sum(2 if unicodedata.east_asian_width(ch) in 'WF' else 1 for ch in t))
        print('\n' + pad('驗收總表', 22) + ' FAIL  WARN  PASS  共計')
        for g, (f, w, p_) in gates.items():
            print('  ' + pad(g, 20) + f'{f:5d}{w:6d}{p_:6d}{f + w + p_:6d}' + ('  ← FAIL' if f else ''))
        # deliverable (docs/SOP.md): all four gates ran and none has a FAIL
        all_ran = all(any(g.startswith(n) for g in gates) for n in '1234')
        deliverable = all_ran and not any(f for f, _, _ in gates.values())
        print(f'  可交付: {"是" if deliverable else "否"}' + ('' if deliverable else
              '（有 FAIL）' if any(f for f, _, _ in gates.values()) else '（沒有從頭跑完四道關卡）'))
        json.dump(dict(gates={g: dict(FAIL=f, WARN=w, PASS=p_, TOTAL=f + w + p_) for g, (f, w, p_) in gates.items()},
                       deliverable=deliverable, code=code),
                  open(os.path.join(out, 'gates.json'), 'w'), ensure_ascii=False, indent=1)

    def client_report(quick=False):
        """progress and pictures for the (internal) client, in Chinese, FAIL / WARN included: OUT/client/index.html.
        quick: during the run (progress and the pictures that already exist, no Blender render)"""
        try:
            import client_report as cr
            cr.main([img, out, '--name', a.name] + (['--blender', blender] if blender else [])
                    + (['--no-render'] if quick else []))
        except Exception as error:                     # the report must never hide the run's own result
            print(f'  client_report 失敗：{error}')

    progress = {}

    def save_progress():
        tmp = os.path.join(out, 'progress.json.tmp')
        json.dump(progress, open(tmp, 'w'), ensure_ascii=False, indent=1)
        os.replace(tmp, os.path.join(out, 'progress.json'))

    def photo_check():
        rc = run([py, os.path.join(HERE, 'check_turnaround.py'), img, '--pose', a.pose,
                  '--out', os.path.join(out, 'turnaround_report.png')],
                 out, log, ok_codes=(0, 1))
        tally('1 照片檢查')
        return rc

    def step_check():
        nonlocal img
        status_path = os.path.join(work, 'check_status.json')
        record_path = os.path.join(out, 'autofix.json')
        for f in (status_path, record_path, os.path.join(out, 'diagnosis.json')):
            if os.path.exists(f):
                os.remove(f)
        for d in ('ai_fix_request', 'ai_code_request'):
            if os.path.isdir(os.path.join(out, d)):
                shutil.rmtree(os.path.join(out, d))
        rc = photo_check()
        # FAIL: fix what can be fixed with high confidence and check again (docs/SOP.md); stop when anything needs
        # regeneration, confidence is low, or a round does not lower the FAIL count
        record = []
        for rnd in range(1, AUTOFIX_ROUNDS + 1):
            if rc != 1 or a.no_autofix or '1 照片檢查' not in gates:
                break
            import autofix
            before = gates['1 照片檢查'][0]
            p = autofix.plan(img, fails['1 照片檢查'])
            for why in p['reasons']:
                print('     不能自動修：' + why)
            if not p['ok']:
                print('     自動修正：有項目要重新生成或信心不夠，不修，停在照片檢查')
                break
            dst = os.path.join(out, f'photos_fixed_r{rnd}')
            if os.path.isdir(dst):
                shutil.rmtree(dst)
            record += autofix.apply(img, dst, p, rnd)
            for it in p['items']:
                print(f"     自動修正第 {rnd} 輪：{it['photo']} 平移 ({it['dx_px']:+.0f}, {it['dy_px']:+.0f}) px，"
                      f"{it['before_mm']} → {it['after_mm']} mm")
            img = dst
            rc = photo_check()
            if gates['1 照片檢查'][0] >= before:
                print('     自動修正沒有減少未通過項目，停在照片檢查')
                rc = 1
                break
        if record:
            json.dump(dict(photos=img, original=os.path.abspath(a.img_dir), fixes=record),
                      open(record_path, 'w'), ensure_ascii=False, indent=1)
        with open(status_path, 'w') as f:
            json.dump(dict(passed=rc == 0), f)
        if rc == 1:
            diagnose(1)
        if '1 照片檢查' not in gates:
            print('     照片檢查沒有印出總結，不打包階段 1 的照片')
        else:                                        # stage 1: the 33 photos, zipped even when the check fails
            import deliver, re
            txt = open(log, errors='replace').read().split('\n$ ')[-1]
            v = re.search(r'check_turnaround 版本 (\S+?)（', txt)
            z, ok = deliver.stage1(img, out, a.name, gates['1 照片檢查'], v.group(1) if v else '?',
                                   os.path.join(out, 'turnaround_report.png'), deliver.fail_lines(txt),
                                   autofix=record_path if record else None,
                                   diagnosis=[d for d in diagnosis if d['gate'] == 1])
            print('     階段 1 成果' + ('（好，可交付）：' if ok else '（有未通過，標 _FAIL）：') + z)
        if rc == 1 and not go_on:
            raise RuntimeError('照片檢查有 FAIL（見 run_all.log / turnaround_report.png）。修正照片，或加 --force 繼續做完供診斷')
        if rc == 1:
            print('     照片檢查有 FAIL，--force 繼續：之後的成果都標 _FAIL')

    def step_face():
        for angle in ('000', '045', '315'):
            f = os.path.join(img, f'head_{angle}deg.jpg')
            name = 'face_lm33.npy' if angle == '000' else f'face_lm33_{angle}.npy'
            dst = os.path.join(work, name)
            if os.path.exists(dst):
                os.remove(dst)
            if not os.path.exists(f):
                raise RuntimeError(f'缺少頭部特寫 {f}：臉部步驟是必要的')
            # exit 2 = no face found: the photo check has already failed it, so only --force goes on (results _FAIL)
            run([py, S('face_landmarks.py'), f, dst], work, log, ok_codes=(0, 2) if go_on else (0,))

    def step_bake():
        rc = run([py, os.path.join(HERE, 'check_turnaround.py'), img, '--head-overlap-work', work,
                  '--view-overlay-dir', os.path.join(out, 'view_overlays')],
                 work, log, ok_codes=(0, 1), show_output=True)
        tally('2 烘焙前檢查')
        if rc:
            diagnose(2)
        stage_zip(2)
        if rc and not go_on:
            raise RuntimeError('烘焙前頭部檢查有 FAIL（見 run_all.log）。修正照片，或加 --force 繼續做完供診斷')
        if rc:
            print('     烘焙前頭部檢查有 FAIL，--force 繼續：之後的成果都標 _FAIL')
        run([py, S('bake33.py'), work, img], work, log)

    def step_export():
        run(need_blender() + [S('bl_export.py'), '--', work, glb_tex], work, log)
        for f in os.listdir(work):
            if f.startswith('v2_') and f.endswith('.png'):
                shutil.copy(os.path.join(work, f), os.path.join(out, f))

    def step_verify():
        bad = 0
        for g, extra in ((unlit, ['--expect-unlit']), (lit, [])):
            bad |= run([py, os.path.join(HERE, 'verify_glb.py'), g] + extra, out, log, ok_codes=(0, 1))
            tally('3 GLB 驗證' + ('（unlit）' if extra else '（lit）'))
        txt = open(log, errors='replace').read()
        for part in txt.split('\nverify_glb ')[-2:]:
            print('   verify_glb ' + '\n   '.join(l for l in part.splitlines() if 'FAIL' in l or 'WARN' in l or '總結' in l or l.endswith('.glb')))
        stage_zip(3)
        if bad and not go_on:
            raise RuntimeError('verify_glb 有 FAIL（見 run_all.log）')
        if bad:
            print('     GLB 驗證有 FAIL，--force 繼續：之後的成果都標 _FAIL')

    mh = a.template == 'makehuman'
    mesh_ply = os.path.join(work, 'body_mh.ply' if mh else 'body33s.ply')

    def step_mh_export():
        run(need_blender() + [S('mh_export.py'), '--', work, lit], work, log)
        # previews for stage 3 (the hull path gets them from bl_export): the spec cameras of the level ring
        rdir = os.path.join(work, 'previews')
        run(need_blender() + [S('bl_client_render.py'), '--', lit, rdir, '900'], work, log)
        for phi, v in (('000', 'front'), ('045', 'three_q'), ('090', 'side'), ('180', 'back')):
            src = os.path.join(rdir, f'main_{phi}.png')
            if os.path.exists(src):
                shutil.copy(src, os.path.join(out, f'v2_{v}_FLAT.png'))

    def skip(msg):
        return lambda: print('     ' + msg)

    def step_fit():
        mesh = ['--mesh', 'body_mh.ply'] if mh else []
        rc = run([py, os.path.join(HERE, 'fit_report.py'), work, '--accept', '--json', os.path.join(out, 'fit_report.json')] + mesh,
                 out, log, ok_codes=(0, 1))
        tally('4 最終驗收')
        txt = open(log, errors='replace').read().split('\n$ ')[-1]
        print('   ' + '\n   '.join(l for l in txt.splitlines() if l.startswith(('[PASS]', '[WARN]', '[FAIL]', '總結'))))
        if rc and not go_on:
            raise RuntimeError('成品與原圖剪影差異太大（見 fit_report.json）：先修正照片（第 10 / 10d / 10e 項）')
        if rc:
            print('     成品與原圖剪影差異太大，--force 繼續：成果標 _FAIL')

    def step_headreg():
        # register the head close-ups on the untrimmed hull, then trim the head to their outlines (headsil33)
        hull = os.path.join(work, 'body33s_hull.ply')
        if os.path.exists(hull):
            shutil.copy(hull, os.path.join(work, 'body33s.ply'))
        run([py, S('headreg33.py')], work, log)
        run([py, S('headsil33.py')], work, log)

    actions = {
        'check': step_check,
        'cams': lambda: run([py, S('cams33.py'), img], work, log),
        'refine': lambda: run([py, S('refine33.py')], work, log),
        'arms': lambda: run([py, S('arms33.py'), '0.20'], work, log),
        'round': lambda: run([py, S('round33.py'), 'occ33b.npy', 'occ33c.npy', '3'], work, log),
        'legs': lambda: run([py, S('legs33.py'), 'occ33c.npy', 'occ33d.npy'], work, log),
        'mesh': lambda: ([os.remove(os.path.join(work, f)) for f in ('body33s_noface.ply', 'body33s_hull.ply')
                          if os.path.exists(os.path.join(work, f))],
                         run([py, S('mesh33s.py'), 'occ33d.npy', 'body33s.ply'], work, log)),
        'headreg': step_headreg,
        'face': step_face,
        'face3d': lambda: run([py, S('face33.py'), img], work, log, ok_codes=(0, 2) if go_on else (0,)),
        'uv': lambda: run(need_blender() + [S('bl_uv33s.py'), '--', work], work, log),
        'bake': step_bake,
        'export': step_export,
        'joints': lambda: run([py, S('joints.py'), 'body33s.ply'], work, log),
        'rig': lambda: run(need_blender() + [S('rig.py'), '--', glb_tex, os.path.join(work, 'joints.json'), lit], work, log),
        'unlit': lambda: run([py, S('glb_unlit.py'), lit, unlit], work, log),
        'verify': step_verify,
        'fit': step_fit,
    }
    if mh:                                   # MakeHuman body replaces the hull mesh from the UV step on
        actions.update({
            'uv': lambda: run([py, S('mh33.py'), work, need_blender()[0]], work, log),
            'export': step_mh_export,
            'joints': skip('MakeHuman 骨架（mh33.py 已擬合關節）'),
            'rig': skip('MakeHuman Mixamo 骨架與權重（52 根骨頭，含手指）'),
        })
    todo = [a.only] if a.only else STEPS[STEPS.index(a.start):]
    print(f'body3d {__version__}  照片: {img}  輸出: {out}  Blender: {blender or "(找不到)"}')
    t0 = time.time()
    code = code_version()                            # next_step reruns an output made by older code
    progress.update(started=t0, state='running', code=code,
                    steps=[dict(name=s, status='pending', seconds=None) for s in todo])
    try:
        for i, s in enumerate(todo):
            print(f'[{STEPS.index(s) + 1:2d}/{len(STEPS)}] {s}', flush=True)
            st = progress['steps'][i]; st['status'] = 'running'; ts = time.time()
            save_progress(); client_report(quick=True)
            actions[s]()
            st['status'] = 'done'; st['seconds'] = round(time.time() - ts, 1)
            save_progress()
    except RuntimeError as e:
        st['status'] = 'failed'; st['seconds'] = round(time.time() - ts, 1)
        progress.update(state='stopped', stopped_at=s, reason=str(e).split('\n')[0], finished=time.time())
        save_progress()
        gate_table()
        client_report()
        # what was made is still handed over: the stage the run stopped in is packed with whatever it has, as _FAIL
        from client_report import STAGE_OF
        here = STAGE_OF.get(s, 1)
        if s == 'bake' and gates.get('2 烘焙前檢查', (0,))[0]:  # the pre-bake check (end of stage 2) runs inside 'bake'
            here = 2
        progress['stopped_stage'] = here; save_progress()
        for n in range(2, here + 1):
            if n not in packed or n == here:
                stage_zip(n, stopped=(s, str(e).split('\n')[0]) if n == here else None)
        client_report(quick=True)                    # the page links the zips packed just now
        print(f'\n停在步驟 {s}: {e}', file=sys.stderr)
        return 1
    progress.update(state='done', finished=time.time())
    save_progress()
    gate_table()
    client_report()
    if 'fit' in todo:                                # stage 4 result: the photo / model comparison and the numbers
        stage_zip(4)
        client_report(quick=True)                    # the page links the stage 4 zip too
    print(f'\n完成（{(time.time() - t0) / 60:.1f} 分鐘）')
    if 'unlit' in todo or 'verify' in todo:
        print(f'  {unlit}\n  {lit}')
    return 1 if any(f for f, _, _ in gates.values()) else 0


if __name__ == '__main__':
    sys.exit(main())
