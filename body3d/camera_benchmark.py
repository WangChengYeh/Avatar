#!/usr/bin/env python3
"""
camera_benchmark.py — 用「已知相機」的合成照片量相機估計的誤差（審查第 4 項的驗收）

用法:
    python camera_benchmark.py 合成照片資料夾 輸出資料夾 [--true-distance 4.0] [--full]

合成照片由 tests/render_synth.py 產生：俯角環 30°、仰角環 −20°、每 45° 一張；--true-distance 表示用
該距離（m）的透視相機渲染，省略表示正交。會依序跑 run_all.py 的 check → cams → refine（--full 再跑到
face3d，另外量全身剪影差異與臉部特徵點誤差），然後報告:
    角度誤差    每個環的 |Δφ|、|Δθ| 平均 / 最大（真值 = 檔名角度、30° / −20°）
    透視誤判    正交照片被判成透視的張數；透視照片沒被判成透視的張數
    距離誤差    估計的相機距離和真值的差
    全身剪影    fit_report.py --region body 的平均不一致比例（--full）
    臉部特徵點  face33 對齊後的特徵點誤差中位數（--full）
結果另存成 輸出資料夾/camera_benchmark.json。
"""
import argparse, json, os, re, subprocess, sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
TRUE_TH = {'main': 0.0, 'el30': 30.0, 'low20': -20.0}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('photos'); ap.add_argument('out')
    ap.add_argument('--true-distance', type=float)
    ap.add_argument('--full', action='store_true')
    a = ap.parse_args()
    steps = ['check', 'cams', 'refine'] + (['arms', 'round', 'legs', 'mesh', 'headreg', 'face', 'face3d'] if a.full else [])
    for st in steps:
        r = subprocess.run([sys.executable, os.path.join(HERE, 'run_all.py'), a.photos, a.out, '--only', st, '--force'],
                           capture_output=True, text=True)
        # run_all exits 1 whenever a gate has a FAIL, even with --force; the benchmark's photos fail the photo check
        # on purpose (a perspective camera), so only a stop (a step that did not finish) is a failure here
        out = r.stdout + r.stderr
        if r.returncode and ('停在步驟' in out or 'Traceback' in out):
            sys.exit(f'{st} 失敗:\n{r.stdout[-2000:]}{r.stderr[-2000:]}')
    work = os.path.join(a.out, 'work')
    cams = json.load(open(os.path.join(work, 'cams33.json')))
    passed = json.load(open(os.path.join(work, 'check_status.json'))).get('passed')
    res = dict(check_passed=passed, rings={})
    print(f'照片檢查 {"通過" if passed else "未通過相機校準條件"}；真值：{"透視 %.1f m" % a.true_distance if a.true_distance else "正交"}')
    print(f'{"環":6s}{"|Δφ| 平均/最大":>16s}{"|Δθ| 平均/最大":>16s}{"判成透視":>10s}{"距離誤差 平均/最大":>20s}')
    for ring in ('main', 'el30', 'low20'):
        rows = [(n, c) for n, c in cams.items() if c.get('kind') == ring]
        if not rows:
            continue
        dphi = [abs((c['phi'] - float(re.search(r'(\d{3})deg', n).group(1)) + 180) % 360 - 180) for n, c in rows]
        dth = [abs(c['th'] - TRUE_TH[ring]) for n, c in rows]
        ds = [c.get('D') for n, c in rows]
        npersp = sum(1 for d in ds if d)
        derr = [abs(d - a.true_distance) for d in ds if d and a.true_distance]
        res['rings'][ring] = dict(dphi_mean=float(np.mean(dphi)), dphi_max=float(max(dphi)), dth_mean=float(np.mean(dth)),
                                  dth_max=float(max(dth)), n=len(rows), n_perspective=npersp,
                                  dist_err_mean=float(np.mean(derr)) if derr else None, dist_err_max=float(max(derr)) if derr else None)
        r_ = res['rings'][ring]
        de = f"{r_['dist_err_mean']:.2f} / {r_['dist_err_max']:.2f} m" if derr else '-'
        print(f'{ring:6s}{r_["dphi_mean"]:8.1f} / {r_["dphi_max"]:4.1f}°{r_["dth_mean"]:8.1f} / {r_["dth_max"]:4.1f}°'
              f'{npersp:6d}/{len(rows)}{de:>20s}')
    if a.full:
        sys.path.insert(0, HERE)
        import fit_report
        fr = fit_report.fit(work, region='body')
        res['body_xor_mean'] = float(np.mean([r['xor'] for r in fr]))
        log = open(os.path.join(a.out, 'run_all.log')).read()
        m = re.search(r'landmark misalignment median ([\d.]+) mm -> ([\d.]+) mm', log)
        res['face_landmark_mm'] = float(m.group(2)) if m else None
        print(f'全身剪影不一致（24 視角平均）{100 * res["body_xor_mean"]:.2f}%；臉部特徵點誤差中位數 {res["face_landmark_mm"]} mm')
    json.dump(res, open(os.path.join(a.out, 'camera_benchmark.json'), 'w'), indent=1)


if __name__ == '__main__':
    main()
