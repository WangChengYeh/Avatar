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

__version__ = '1.0.0'


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


def main():
    ap = argparse.ArgumentParser(description=f'fit_report {__version__}')
    ap.add_argument('work'); ap.add_argument('--mesh', default='body33s.ply')
    ap.add_argument('--region', choices=['legs', 'body'], default='legs')
    ap.add_argument('--max-extra', type=float, default=600)
    a = ap.parse_args()
    rows = fit(a.work, a.mesh, a.region)
    print(f'{"視角":24s}{"extra":>8s}{"missing":>9s}{"xor":>8s}')
    for r in rows:
        print(f'{r["view"]:24s}{r["extra"]:8d}{r["missing"]:9d}{100 * r["xor"]:7.1f}%')
    main_ = [r for r in rows if r['kind'] == 'main']
    me = np.mean([r['extra'] for r in main_]); mx = np.mean([r['xor'] for r in main_])
    print(f'\n主環平均: extra {me:.0f} px, xor {100 * mx:.1f}%（{a.region}）')
    sys.exit(1 if me > a.max_extra else 0)


if __name__ == '__main__':
    main()
