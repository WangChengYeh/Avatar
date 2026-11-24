#!/usr/bin/env python3
"""
run_all.py — 33 張 T-pose 環繞照片 → 附骨架、有貼圖的 GLB（整條流程一支 Python 指令）

用法:
    python run_all.py IMG_DIR OUT_DIR [--name body] [--blender /path/to/blender] [--force] [--from STEP] [--only STEP]

步驟（每一步都是 Python；Blender 步驟以 `blender -b --python` 執行 Python 腳本）:
   1 check     check_turnaround.py 檢查照片規範（有 FAIL 就停，--force 才繼續）
   2 cams      去背、建立正交相機（cams33.py）
   3 refine    聯合微調相機 + 視覺外殼（refine33.py）
   4 arms      T-pose 手臂重建為橢圓柱（arms33.py）
   5 round     3D 開運算讓外形圓滑（round33.py）
   6 legs      腿部嚴格雕刻：兩腿之間的外殼殘留（legs33.py）
   7 mesh      Marching cubes + 平滑 + 減面 → body33s.ply（mesh33s.py）
   8 headreg   頭部特寫相機對位（headreg33.py）
   9 face      MediaPipe 臉部特徵點（face_landmarks.py，選用）
  10 face3d    用臉部特徵點對齊 3/4 頭部特寫相機、補出鼻子 / 眼窩（face33.py，選用）
  11 uv        Blender 展 UV（bl_uv33s.py）
  12 bake      頭部投影重疊檢查、多視角貼圖烘焙（bake33.py）
  13 export    Blender 匯出有貼圖的 GLB + 預覽圖（bl_export.py）
  14 joints    從網格量測關節位置（joints.py）
  15 rig       Blender 建 22 根骨頭、自動權重、匯出（rig.py）
  16 unlit     材質標為 KHR_materials_unlit（glb_unlit.py）
  17 verify    verify_glb.py 驗證兩個 GLB（有 FAIL 時結束碼 1）
  18 fit       最終驗收：成品網格以最終相機投影回 24 張全身原圖，剪影平均不一致 > 10% 判 FAIL（fit_report.py --accept）

輸出（OUT_DIR）:
    {name}_rigged.glb        無光照材質（照片已含光影，建議用這個）
    {name}_rigged_lit.glb    一般 PBR 材質
    v2_*.png                 Blender 預覽圖
    turnaround_report.png    照片檢查報告；work/ 內是中間檔
"""
import argparse, json, os, shutil, subprocess, sys, time

__version__ = '2.6.0'
HERE = os.path.dirname(os.path.abspath(__file__))
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


def main(argv=None):
    ap = argparse.ArgumentParser(description=f'body3d run_all {__version__}')
    ap.add_argument('img_dir'); ap.add_argument('out_dir')
    ap.add_argument('--name', default='body')
    ap.add_argument('--blender')
    ap.add_argument('--force', action='store_true', help='照片檢查有 FAIL 也繼續')
    ap.add_argument('--from', dest='start', choices=STEPS, default='check')
    ap.add_argument('--only', choices=STEPS)
    ap.add_argument('--pose', choices=['tpose', 'apose'], default='tpose')
    ap.add_argument('--version', action='version', version=f'body3d {__version__}')
    a = ap.parse_args(argv)

    img = os.path.abspath(a.img_dir); out = os.path.abspath(a.out_dir)
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

    def step_check():
        status_path = os.path.join(work, 'check_status.json')
        if os.path.exists(status_path):
            os.remove(status_path)
        rc = run([py, os.path.join(HERE, 'check_turnaround.py'), img, '--pose', a.pose,
                  '--camera-check', '--out', os.path.join(out, 'turnaround_report.png')],
                 out, log, ok_codes=(0, 1, 3))
        with open(status_path, 'w') as f:
            json.dump(dict(passed=rc == 0), f)
        if rc == 1 and not a.force:
            raise RuntimeError('照片檢查有 FAIL（見 run_all.log / turnaround_report.png）。修正照片，或加 --force 繼續')
        if rc == 1:
            print('     照片檢查有 FAIL，--force 繼續')
        if rc == 3:
            print('     臉部一致性未通過完整驗證，相機使用較寬的搜尋範圍。')

    def step_face():
        for angle in ('000', '045', '315'):
            f = os.path.join(img, f'head_{angle}deg.jpg')
            name = 'face_lm33.npy' if angle == '000' else f'face_lm33_{angle}.npy'
            dst = os.path.join(work, name)
            if os.path.exists(dst):
                os.remove(dst)
            if os.path.exists(f):
                run([py, S('face_landmarks.py'), f, dst], work, log)

    def step_bake():
        rc = run([py, os.path.join(HERE, 'check_turnaround.py'), img, '--head-overlap-work', work,
                  '--view-overlay-dir', os.path.join(out, 'view_overlays')],
                 work, log, ok_codes=(0, 1), show_output=True)
        if rc and not a.force:
            raise RuntimeError('烘焙前頭部檢查有 FAIL（見 run_all.log）。修正照片，或加 --force 繼續')
        if rc:
            print('     烘焙前頭部檢查有 FAIL，--force 繼續')
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
        txt = open(log, errors='replace').read()
        for part in txt.split('\nverify_glb ')[-2:]:
            print('   verify_glb ' + '\n   '.join(l for l in part.splitlines() if 'FAIL' in l or 'WARN' in l or '總結' in l or l.endswith('.glb')))
        if bad:
            raise RuntimeError('verify_glb 有 FAIL（見 run_all.log）')

    def step_fit():
        rc = run([py, os.path.join(HERE, 'fit_report.py'), work, '--accept', '--json', os.path.join(out, 'fit_report.json')],
                 out, log, ok_codes=(0, 1))
        txt = open(log, errors='replace').read().split('\n$ ')[-1]
        print('   ' + '\n   '.join(l for l in txt.splitlines() if l.startswith(('[PASS]', '[WARN]', '[FAIL]'))))
        if rc and not a.force:
            raise RuntimeError('成品與原圖剪影差異太大（見 fit_report.json）：先修正照片（第 10 / 10d / 10e 項），或加 --force')
        if rc:
            print('     成品與原圖剪影差異太大，--force 繼續')

    actions = {
        'check': step_check,
        'cams': lambda: run([py, S('cams33.py'), img], work, log),
        'refine': lambda: run([py, S('refine33.py')], work, log),
        'arms': lambda: run([py, S('arms33.py'), '0.20'], work, log),
        'round': lambda: run([py, S('round33.py'), 'occ33b.npy', 'occ33c.npy', '3'], work, log),
        'legs': lambda: run([py, S('legs33.py'), 'occ33c.npy', 'occ33d.npy'], work, log),
        'mesh': lambda: (os.path.exists(os.path.join(work, 'body33s_noface.ply')) and os.remove(os.path.join(work, 'body33s_noface.ply')),
                         run([py, S('mesh33s.py'), 'occ33d.npy', 'body33s.ply'], work, log)),
        'headreg': lambda: run([py, S('headreg33.py')], work, log),
        'face': step_face,
        'face3d': lambda: run([py, S('face33.py'), img], work, log),
        'uv': lambda: run(need_blender() + [S('bl_uv33s.py'), '--', work], work, log),
        'bake': step_bake,
        'export': step_export,
        'joints': lambda: run([py, S('joints.py'), 'body33s.ply'], work, log),
        'rig': lambda: run(need_blender() + [S('rig.py'), '--', glb_tex, os.path.join(work, 'joints.json'), lit], work, log),
        'unlit': lambda: run([py, S('glb_unlit.py'), lit, unlit], work, log),
        'verify': step_verify,
        'fit': step_fit,
    }
    todo = [a.only] if a.only else STEPS[STEPS.index(a.start):]
    print(f'body3d {__version__}  照片: {img}  輸出: {out}  Blender: {blender or "(找不到)"}')
    t0 = time.time()
    try:
        for i, s in enumerate(todo):
            print(f'[{STEPS.index(s) + 1:2d}/{len(STEPS)}] {s}', flush=True)
            actions[s]()
    except RuntimeError as e:
        print(f'\n失敗於步驟 {s}: {e}', file=sys.stderr)
        return 1
    print(f'\n完成（{(time.time() - t0) / 60:.1f} 分鐘）')
    if 'unlit' in todo or 'verify' in todo:
        print(f'  {unlit}\n  {lit}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
