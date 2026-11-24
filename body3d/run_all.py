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
  10 uv        Blender 展 UV（bl_uv33s.py）
  11 bake      頭部投影重疊檢查、多視角貼圖烘焙（bake33.py）
  12 export    Blender 匯出有貼圖的 GLB + 預覽圖（bl_export.py）
  13 joints    從網格量測關節位置（joints.py）
  14 rig       Blender 建 22 根骨頭、自動權重、匯出（rig.py）
  15 unlit     材質標為 KHR_materials_unlit（glb_unlit.py）
  16 verify    verify_glb.py 驗證兩個 GLB（有 FAIL 時結束碼 1）

輸出（OUT_DIR）:
    {name}_rigged.glb        無光照材質（照片已含光影，建議用這個）
    {name}_rigged_lit.glb    一般 PBR 材質
    v2_*.png                 Blender 預覽圖
    turnaround_report.png    照片檢查報告；work/ 內是中間檔
"""
import argparse, os, shutil, subprocess, sys, time

__version__ = '2.3.0'
HERE = os.path.dirname(os.path.abspath(__file__))
STEPS_DIR = os.path.join(HERE, 'steps')
STEPS = ['check', 'cams', 'refine', 'arms', 'round', 'legs', 'mesh', 'headreg', 'face', 'uv', 'bake', 'export',
         'joints', 'rig', 'unlit', 'verify']


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
        p = subprocess.run(cmd, cwd=cwd, stdout=f, stderr=subprocess.STDOUT)
        if show_output:
            f.seek(start)
            print(f.read(), end='', flush=True)
    print(f'     ({time.time() - t:.0f} s, exit {p.returncode})', flush=True)
    if p.returncode not in ok_codes:
        tail = open(log, errors='replace').read().splitlines()[-25:]
        raise RuntimeError(f'步驟失敗（exit {p.returncode}），log: {log}\n' + '\n'.join(tail))
    return p.returncode


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
        return [blender, '-b', '--factory-startup', '--python']

    def step_check():
        rc = run([py, os.path.join(HERE, 'check_turnaround.py'), img, '--pose', a.pose,
                  '--out', os.path.join(out, 'turnaround_report.png')], out, log, ok_codes=(0, 1))
        if rc and not a.force:
            raise RuntimeError('照片檢查有 FAIL（見 run_all.log / turnaround_report.png）。修正照片，或加 --force 繼續')
        if rc:
            print('     照片檢查有 FAIL，--force 繼續')

    def step_face():
        f = os.path.join(img, 'head_000deg.jpg')
        dst = os.path.join(work, 'face_lm33.npy')
        if os.path.exists(dst):
            os.remove(dst)
        if os.path.exists(f):
            run([py, S('face_landmarks.py'), f, dst], work, log)

    def step_bake():
        run([py, os.path.join(HERE, 'check_turnaround.py'), img, '--head-overlap-work', work], work, log, show_output=True)
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

    actions = {
        'check': step_check,
        'cams': lambda: run([py, S('cams33.py'), img], work, log),
        'refine': lambda: run([py, S('refine33.py')], work, log),
        'arms': lambda: run([py, S('arms33.py'), '0.20'], work, log),
        'round': lambda: run([py, S('round33.py'), 'occ33b.npy', 'occ33c.npy', '3'], work, log),
        'legs': lambda: run([py, S('legs33.py'), 'occ33c.npy', 'occ33d.npy'], work, log),
        'mesh': lambda: run([py, S('mesh33s.py'), 'occ33d.npy', 'body33s.ply'], work, log),
        'headreg': lambda: run([py, S('headreg33.py')], work, log),
        'face': step_face,
        'uv': lambda: run(need_blender() + [S('bl_uv33s.py'), '--', work], work, log),
        'bake': step_bake,
        'export': step_export,
        'joints': lambda: run([py, S('joints.py'), 'body33s.ply'], work, log),
        'rig': lambda: run(need_blender() + [S('rig.py'), '--', glb_tex, os.path.join(work, 'joints.json'), lit], work, log),
        'unlit': lambda: run([py, S('glb_unlit.py'), lit, unlit], work, log),
        'verify': step_verify,
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
