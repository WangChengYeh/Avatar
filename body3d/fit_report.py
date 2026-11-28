#!/usr/bin/env python3
"""
fit_report.py — 把重建的網格投影回每張照片，比對剪影（判斷是「照片的問題」還是「腳本的問題」）

用法:
    python fit_report.py WORK_DIR [--mesh body33s.ply] [--region legs|body] [--max-extra 600]

對每個身體視角（主環、俯角、仰角）算:
    extra    模型超出照片剪影 > 3 px 的像素數（多出來的幾何 = 重建殘留，例如兩腿之間的外殼）
    missing  照片有、模型沒有 > 3 px 的像素數（被削掉太多）
    xor      兩個剪影不一致的面積 / 照片面積
判讀:
    - 只有少數視角 extra 大、其他視角乾淨 → 腳本（外殼投票或相機）問題，照片沒問題
    - 某一張 missing 大、其他都乾淨 → 那張照片的形狀和其他張不一致（照片問題）
結束碼: 主環平均 extra > --max-extra 時為 1。
"""
import argparse, json, os, sys
import cv2
import numpy as np

__version__ = '1.1.0'


sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'steps'))
import camera


def project(P, c):
    return np.c_[camera.project(P, c)]


def silhouette(V, F, c, shape):
    sil = np.zeros(shape, np.uint8)
    for t in (project(V, c)[F] * 4).astype(np.int32):
        cv2.fillConvexPoly(sil, t, 1, shift=2)
    return sil > 0


def fit(work, mesh='body33s.ply', region='legs'):
    import trimesh
    m = trimesh.load(os.path.join(work, mesh))
    cams = json.load(open(os.path.join(work, 'cams33.json')))
    rows = []
    for n in sorted(cams):
        c = cams[n]
        if c.get('kind') == 'head' or n == 'top':
            continue
        M = cv2.imread(os.path.join(work, f'mask_{n}.png'), 0) > 0
        S = silhouette(m.vertices, m.faces, c, M.shape)
        h = c['cv'] - np.arange(M.shape[0])[:, None]                # height above the feet in pixels
        zone = (h > c['s'] * 0.05) & (h < c['s'] * 0.72) if region == 'legs' else np.ones_like(M)
        k = np.ones((7, 7), np.uint8)
        extra = S & (cv2.dilate(M.astype(np.uint8), k) == 0) & zone
        missing = M & (cv2.dilate(S.astype(np.uint8), k) == 0) & zone
        xor = ((S ^ M) & zone).sum() / max(1, (M & zone).sum())
        rows.append(dict(view=n, kind=c.get('kind'), extra=int(extra.sum()), missing=int(missing.sum()), xor=float(xor)))
    return rows


# final acceptance (run_all step 18, --accept): the finished mesh projected with the final cameras onto every
# full-body photo, region body. Calibrated on perfect synthetic photos (cameras known): mean 5.6–6.6 %, worst view
# 9.3 %; v1220 (photos failing the check): mean 15.5 %, worst 29.8 %.
ACCEPT_PASS, ACCEPT_FAIL, VIEW_WARN = 0.08, 0.10, 0.12


def acceptance(rows):
    """(level, mean xor, [(view, xor) over VIEW_WARN]) for the body-region rows"""
    x = np.array([r['xor'] for r in rows]) if rows else np.zeros(1)
    worst = [(r['view'], r['xor']) for r in sorted(rows, key=lambda r: -r['xor']) if r['xor'] > VIEW_WARN]
    mean = float(x.mean())
    level = 'FAIL' if mean > ACCEPT_FAIL else 'WARN' if mean > ACCEPT_PASS or worst else 'PASS'
    return level, mean, worst


def main():
    ap = argparse.ArgumentParser(description=f'fit_report {__version__}')
    ap.add_argument('work'); ap.add_argument('--mesh', default='body33s.ply')
    ap.add_argument('--region', choices=['legs', 'body'], default='legs')
    ap.add_argument('--max-extra', type=float, default=600)
    ap.add_argument('--accept', action='store_true',
                    help='最終驗收：全身剪影平均不一致 ≤ 8%% PASS、> 10%% FAIL（結束碼 1），單張 > 12%% WARN')
    ap.add_argument('--json', help='另存每張結果與驗收結論')
    ap.add_argument('--glb', help='成品 GLB（無光照）：和 --photos 一起給，驗收時加做「全身差異依關節分區」（part_compare.py）')
    ap.add_argument('--photos', help='原始照片的資料夾')
    ap.add_argument('--parts-picture', help='差異對照圖（最差的幾個角度）存到這裡')
    a = ap.parse_args()
    if a.accept:
        a.region = 'body'
    rows = fit(a.work, a.mesh, a.region)
    print(f'{"視角":24s}{"extra":>8s}{"missing":>9s}{"xor":>8s}')
    for r in rows:
        print(f'{r["view"]:24s}{r["extra"]:8d}{r["missing"]:9d}{100 * r["xor"]:7.1f}%')
    main_ = [r for r in rows if r['kind'] == 'main']
    me = np.mean([r['extra'] for r in main_]); mx = np.mean([r['xor'] for r in main_])
    print(f'\n主環平均: extra {me:.0f} px, xor {100 * mx:.1f}%（{a.region}）')
    if a.accept:
        level, mean, worst = acceptance(rows)
        print(f'[{level}] 成品與原圖剪影: {len(rows)} 張全身圖平均不一致 {100 * mean:.1f}%'
              f'（應 ≤ {100 * ACCEPT_PASS:.0f}%，> {100 * ACCEPT_FAIL:.0f}% 判 FAIL；完美照片 5.6–6.6%）')
        for v, x in worst:
            print(f'[WARN] {v}: 不一致 {100 * x:.1f}%（單張應 ≤ {100 * VIEW_WARN:.0f}%）→ 先看這張照片的第 10 / 10d / 10e 項')
        nf, nw = int(level == 'FAIL'), int(level == 'WARN') + len(worst)
        npass = int(level == 'PASS') + len(rows) - len(worst)          # every full-body view counted as one item
        parts = None
        if a.glb and a.photos:                       # the same model, part by part: hair, skin, each garment
            import part_compare
            print('\n成品與原圖的差異，依關節分區（先對整個人物做差異，再看差異落在頭、軀幹、上臂、前臂、手、大腿、小腿、腳的哪一區）')
            try:
                parts = part_compare.compare(a.work, a.photos, a.glb, a.parts_picture)
            except Exception as error:               # a model the comparison cannot read is a finding, not a pass
                print(f'[WARN] 分區差異: 沒有做成（{error}）')
                nw += 1
            else:
                for line in part_compare.lines(parts):
                    print(line)
                if parts.get('first'):               # not everything at once: the few that differ most
                    print('  → 這一輪先修（差最多的幾個）：' + '、'.join(parts['first']) + '；修完重跑，再看其餘的')
                nf += sum(r['level'] == 'FAIL' for r in parts['views']); nw += sum(r['level'] == 'WARN' for r in parts['views'])
                npass += sum(r['level'] == 'PASS' for r in parts['views'])
        print(f'\n總結: {nf} 個 FAIL, {nw} 個 WARN, {npass} 個 PASS，共 {nf + nw + npass} 項')
        if a.json:
            json.dump(dict(level=level, mean=mean, rows=rows, parts=parts), open(a.json, 'w'), indent=1, ensure_ascii=False)
        sys.exit(1 if nf else 0)
    if a.json:
        json.dump(dict(rows=rows), open(a.json, 'w'), indent=1)
    sys.exit(1 if me > a.max_extra else 0)


if __name__ == '__main__':
    main()
