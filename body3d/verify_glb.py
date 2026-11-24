#!/usr/bin/env python3
"""
verify_glb.py — 用純 Python 驗證附骨架的人物 GLB（取代 three.js 檢查頁）

用法:
    python verify_glb.py model.glb [--expect-unlit] [--height 1.65] [--no-validator]

檢查（與 three.js 檢查頁相同的 17 項，外加格式檢查）:
  格式    GLB 標頭 / 區塊、JSON、BIN、accessor 範圍
  骨架    1 個 skin；22 根必要骨頭名稱；父子階層；Hips 為根；蒙皮網格節點是場景根節點
  蒙皮    每個 primitive 有 JOINTS_0 / WEIGHTS_0；索引 < 骨頭數；權重加總 = 1；最多 4 根骨頭；inverseBindMatrices 完整
  幾何    高度 ≈ 1.65 m、Y 朝上、腳在地面、Head 在上方、LeftHand 在 +X 且水平（T-pose）、腳尖朝 +Z
  材質    每個材質有 baseColorTexture，貼圖能解碼（尺寸）；--expect-unlit 時檢查 KHR_materials_unlit
  擺姿勢  以 numpy 做線性蒙皮（LBS）：LeftArm 繞世界 Z 軸往下轉 70°，左手指尖要往下移動；所有頂點為有限值
  頭部渲染 純 Python 把有貼圖的頭部從正面 / 左右 45° / 左右側面算繪成 512x512（--renders 資料夾可存圖），
         在皮膚區域找「又細又長的暗線」（比周圍皮膚暗很多、寬 ≤ 6 px、長 ≥ 5 cm，直的彎的都算）：
         貼圖黑條、對位錯開的接縫會被抓到；睫毛（~3 cm）、嘴線（~4.5 cm）、鼻孔較短，眉毛不夠黑，不算
  驗證器  若有 Node.js 與 npm 套件 gltf-validator，另外跑 Khronos glTF Validator（0 錯誤才算通過）

結束碼: 有 FAIL 回傳 1，否則 0。
需要: numpy、opencv-python（解碼貼圖）
"""
import argparse, json, os, shutil, struct, subprocess, sys, tempfile
import numpy as np

__version__ = '1.1.0'
REQ = ['Hips', 'Spine', 'Spine1', 'Spine2', 'Neck', 'Head', 'LeftShoulder', 'LeftArm', 'LeftForeArm', 'LeftHand',
       'RightShoulder', 'RightArm', 'RightForeArm', 'RightHand', 'LeftUpLeg', 'LeftLeg', 'LeftFoot', 'LeftToeBase',
       'RightUpLeg', 'RightLeg', 'RightFoot', 'RightToeBase']
PARENT = {'Spine': 'Hips', 'Spine1': 'Spine', 'Spine2': 'Spine1', 'Neck': 'Spine2', 'Head': 'Neck',
          'LeftShoulder': 'Spine2', 'LeftArm': 'LeftShoulder', 'LeftForeArm': 'LeftArm', 'LeftHand': 'LeftForeArm',
          'RightShoulder': 'Spine2', 'RightArm': 'RightShoulder', 'RightForeArm': 'RightArm', 'RightHand': 'RightForeArm',
          'LeftUpLeg': 'Hips', 'LeftLeg': 'LeftUpLeg', 'LeftFoot': 'LeftLeg', 'LeftToeBase': 'LeftFoot',
          'RightUpLeg': 'Hips', 'RightLeg': 'RightUpLeg', 'RightFoot': 'RightLeg', 'RightToeBase': 'RightFoot'}
COMP = {5120: np.int8, 5121: np.uint8, 5122: np.int16, 5123: np.uint16, 5125: np.uint32, 5126: np.float32}
NCOMP = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4, 'MAT4': 16}


class Report:
    def __init__(self):
        self.items = []

    def __call__(self, level, item, msg):
        self.items.append((level, item, msg))
        print(f'  [{level}] {item}: {msg}')

    def count(self, level):
        return sum(1 for i in self.items if i[0] == level)


def load_glb(path):
    d = open(path, 'rb').read()
    magic, ver, length = struct.unpack('<4sII', d[:12])
    if magic != b'glTF' or ver != 2:
        raise ValueError(f'不是 glTF 2.0 GLB（magic={magic}, version={ver}）')
    if length != len(d):
        raise ValueError(f'GLB 標頭長度 {length} ≠ 檔案大小 {len(d)}')
    off, gl, bin_ = 12, None, None
    while off < len(d):
        clen, ctype = struct.unpack('<I4s', d[off:off + 8])
        chunk = d[off + 8:off + 8 + clen]
        if ctype == b'JSON':
            gl = json.loads(chunk.decode('utf-8').rstrip(' \x00'))
        elif ctype == b'BIN\x00':
            bin_ = chunk
        off += 8 + clen
    if gl is None:
        raise ValueError('沒有 JSON 區塊')
    return gl, bin_


def accessor(gl, bin_, idx):
    a = gl['accessors'][idx]
    bv = gl['bufferViews'][a['bufferView']]
    dt = np.dtype(COMP[a['componentType']])
    n = NCOMP[a['type']]
    start = bv.get('byteOffset', 0) + a.get('byteOffset', 0)
    stride = bv.get('byteStride', 0) or dt.itemsize * n
    count = a['count']
    if start + stride * (count - 1) + dt.itemsize * n > bv.get('byteOffset', 0) + bv['byteLength']:
        raise ValueError(f'accessor {idx} 超出 bufferView 範圍')
    raw = np.frombuffer(bin_, dtype=np.uint8, count=stride * (count - 1) + dt.itemsize * n, offset=start)
    rows = np.lib.stride_tricks.as_strided(raw, shape=(count, dt.itemsize * n), strides=(stride, 1))
    arr = np.ascontiguousarray(rows).view(dt).reshape(count, n)
    if a.get('normalized') and dt != np.float32:
        arr = arr.astype(np.float32) / np.iinfo(dt).max
    return arr


def trs_matrix(node):
    if 'matrix' in node:
        return np.array(node['matrix'], dtype=np.float64).reshape(4, 4).T
    t = np.array(node.get('translation', [0, 0, 0]), dtype=np.float64)
    x, y, z, w = node.get('rotation', [0, 0, 0, 1])
    s = np.array(node.get('scale', [1, 1, 1]), dtype=np.float64)
    R = np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                  [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                  [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])
    M = np.eye(4); M[:3, :3] = R * s[None, :]; M[:3, 3] = t
    return M


def world_matrices(gl, local=None):
    nodes = gl['nodes']
    parent = {}
    for i, nd in enumerate(nodes):
        for c in nd.get('children', []):
            parent[c] = i
    local = local or {i: trs_matrix(nd) for i, nd in enumerate(nodes)}
    W = {}

    def get(i):
        if i not in W:
            W[i] = local[i] if i not in parent else get(parent[i]) @ local[i]
        return W[i]
    for i in range(len(nodes)):
        get(i)
    return W, parent


def axis_rot(axis, deg):
    a = np.radians(deg); axis = np.asarray(axis, float) / np.linalg.norm(axis)
    K = np.array([[0, -axis[2], axis[1]], [axis[2], 0, -axis[0]], [-axis[1], axis[0], 0]])
    R = np.eye(3) + np.sin(a) * K + (1 - np.cos(a)) * K @ K
    M = np.eye(4); M[:3, :3] = R
    return M


def run_validator(path, rep):
    node = shutil.which('node')
    if not node:
        rep('INFO', 'Khronos 驗證器', '找不到 Node.js，略過（安裝 Node.js 後 npm install gltf-validator）')
        return
    js = ("const fs=require('fs');let v;try{v=require('gltf-validator')}catch(e){console.log('NOPKG');process.exit(0)}"
          "v.validateBytes(new Uint8Array(fs.readFileSync(process.argv[1])),{maxIssues:50}).then(r=>{"
          "console.log(JSON.stringify({e:r.issues.numErrors,w:r.issues.numWarnings,"
          "m:r.issues.messages.filter(m=>m.severity<=1).map(m=>m.code+': '+m.message)}))})")
    here = os.path.dirname(os.path.abspath(__file__))
    env = dict(os.environ, NODE_PATH=os.pathsep.join([os.environ.get('GLTF_VALIDATOR_DIR', ''), os.path.join(here, 'node_modules'), os.path.join(here, '..', 'node_modules'), os.path.join(os.getcwd(), 'node_modules'),
                                                      os.environ.get('NODE_PATH', '')]))
    try:
        out = subprocess.run([node, '-e', js, path], capture_output=True, text=True, timeout=300, env=env).stdout.strip()
    except Exception as e:
        rep('WARN', 'Khronos 驗證器', f'執行失敗：{e}')
        return
    if out == 'NOPKG' or not out:
        rep('INFO', 'Khronos 驗證器', '找不到 npm 套件 gltf-validator，略過（在本資料夾 npm install gltf-validator）')
        return
    r = json.loads(out.splitlines()[-1])
    level = 'FAIL' if r['e'] else ('WARN' if r['w'] else 'PASS')
    rep(level, 'Khronos 驗證器', f"{r['e']} 個錯誤、{r['w']} 個警告" + ('；' + '；'.join(r['m'][:5]) if r['m'] else ''))


def verify(path, expect_unlit=False, height=1.65, validator=True, render_dir=None):
    rep = Report()
    print(f'verify_glb {__version__}: {path}')
    # ---- format
    try:
        gl, bin_ = load_glb(path)
    except Exception as e:
        rep('FAIL', '格式', str(e)); return rep
    rep('PASS', '格式', f"glTF {gl['asset'].get('version')}，產生器 {gl['asset'].get('generator', '?')}，BIN {len(bin_ or b'')/1e6:.1f} MB")
    nodes = gl['nodes']
    # ---- skeleton
    skins = gl.get('skins', [])
    if len(skins) != 1:
        rep('FAIL', '骨架', f'skin 數量 {len(skins)}（應為 1）'); return rep
    skin = skins[0]
    joint_nodes = skin['joints']
    names = [nodes[j].get('name', '') for j in joint_nodes]
    missing = [n for n in REQ if n not in names]; extra = [n for n in names if n not in REQ]
    rep('FAIL' if missing else 'PASS', '骨頭名稱', f'缺少 {", ".join(missing)}' if missing else
        '22 根必要骨頭都在' + (f'；額外 {", ".join(extra)}' if extra else '，沒有多餘骨頭'))
    W, parent = world_matrices(gl)
    idx = {nodes[j].get('name'): j for j in joint_nodes}
    bad = [n for n in REQ if n in idx and PARENT.get(n) and nodes[parent.get(idx[n], -1)].get('name') != PARENT[n]] if not missing else REQ
    rep('FAIL' if bad else 'PASS', '骨頭階層', ('父子關係錯誤：' + ', '.join(bad)) if bad else '父子關係全部正確')
    if missing:
        return rep
    hp = parent.get(idx['Hips'])
    rep('PASS' if hp is None or hp not in joint_nodes else 'FAIL', '根骨',
        f"Hips 的父節點：{nodes[hp].get('name') if hp is not None else '(場景根)'}（非骨頭）")
    mesh_nodes = [i for i, nd in enumerate(nodes) if 'mesh' in nd]
    skinned = [i for i in mesh_nodes if 'skin' in nodes[i]]
    rep('PASS' if skinned and len(skinned) == len(mesh_nodes) else 'FAIL', '蒙皮網格', f'{len(skinned)} / {len(mesh_nodes)} 個網格節點有 skin')
    nonroot = [nodes[i].get('name') for i in skinned if i in parent]
    rep('WARN' if nonroot else 'PASS', '蒙皮網格為根節點', f'{nonroot} 有父節點（glTF 驗證器警告 NODE_SKINNED_MESH_NON_ROOT）' if nonroot else '是場景根節點')
    ibm = accessor(gl, bin_, skin['inverseBindMatrices']).reshape(-1, 4, 4).transpose(0, 2, 1) if 'inverseBindMatrices' in skin else None
    rep('PASS' if ibm is not None and len(ibm) == len(joint_nodes) else 'FAIL', '綁定矩陣',
        f'inverseBindMatrices {0 if ibm is None else len(ibm)} 個 / 骨頭 {len(joint_nodes)} 根')
    # ---- skinning data
    prims = []
    for i in skinned:
        mesh = gl['meshes'][nodes[i]['mesh']]
        for p in mesh['primitives']:
            at = p['attributes']
            if 'JOINTS_0' not in at or 'WEIGHTS_0' not in at:
                rep('FAIL', '蒙皮資料', f"{mesh.get('name')} 缺 JOINTS_0 / WEIGHTS_0"); continue
            prims.append(dict(pos=accessor(gl, bin_, at['POSITION']).astype(np.float64),
                              j=accessor(gl, bin_, at['JOINTS_0']).astype(np.int64),
                              w=accessor(gl, bin_, at['WEIGHTS_0']).astype(np.float64),
                              node=i, extra=[k for k in at if k.startswith('JOINTS_') and k != 'JOINTS_0'], mat=p.get('material'),
                              uv=accessor(gl, bin_, at['TEXCOORD_0']).astype(np.float64) if 'TEXCOORD_0' in at else None,
                              tri=accessor(gl, bin_, p['indices']).reshape(-1, 3).astype(np.int64) if 'indices' in p else None))
    if not prims:
        return rep
    nv = sum(len(p['pos']) for p in prims)
    badj = sum(int(((p['j'] >= len(joint_nodes)) & (p['w'] > 0)).sum()) for p in prims)
    rep('FAIL' if badj else 'PASS', '骨骼索引', f'{badj} 個超出範圍' if badj else f'{nv} 個頂點的索引都在 0..{len(joint_nodes) - 1}')
    sums = np.concatenate([p['w'].sum(1) for p in prims])
    unnorm = int((np.abs(sums - 1) > 0.01).sum())
    maxinf = max(int((p['w'] > 0).sum(1).max()) for p in prims)
    rep('FAIL' if unnorm else 'PASS', '權重加總', f'{unnorm} 個頂點加總 ≠ 1' if unnorm else
        f'所有頂點權重加總 = 1；每個頂點最多 {maxinf} 根骨頭影響' + ('（有 JOINTS_1，超過 4 根）' if any(p['extra'] for p in prims) else ''))
    # ---- rest-pose geometry (world space, skinned with the rest skeleton)
    def skin_positions(Wm, split=False):
        out = []
        for p in prims:
            mesh_w = Wm[p['node']] if p['node'] in Wm else np.eye(4)
            J = np.stack([Wm[jn] @ ibm[k] for k, jn in enumerate(joint_nodes)])          # (nj, 4, 4)
            P = np.c_[p['pos'], np.ones(len(p['pos']))]
            acc = np.zeros((len(P), 4))
            for c in range(4):
                acc += p['w'][:, c:c + 1] * np.einsum('nij,nj->ni', J[p['j'][:, c]], P)
            out.append(acc[:, :3])
        return out if split else np.concatenate(out)
    rest = skin_positions(W)
    lo, hi = rest.min(0), rest.max(0); size = hi - lo
    rep('PASS' if abs(size[1] - height) < 0.05 * height else 'WARN', '尺寸', f'高 {size[1]:.3f} m、寬 {size[0]:.3f} m、厚 {size[2]:.3f} m（Y 朝上）')
    rep('PASS' if abs(lo[1]) < 0.03 else 'WARN', '腳在地面', f'最低點 y = {lo[1]:.3f} m')
    jp = {nodes[j]['name']: W[j][:3, 3] for j in joint_nodes}
    rep('PASS' if jp['Head'][1] > 0.75 * size[1] else 'FAIL', '直立', f"Head 骨在 y = {jp['Head'][1]:.3f} m")
    horiz = abs(jp['LeftHand'][1] - jp['LeftArm'][1]) < 0.08
    rep('PASS' if jp['LeftHand'][0] > 0.3 and horiz else 'WARN', 'T-pose 與左右',
        f"LeftHand x = {jp['LeftHand'][0]:.3f}（左手在 +X），{'手臂水平' if horiz else '手臂不水平'}")
    rep('PASS' if jp['LeftToeBase'][2] > jp['LeftFoot'][2] else 'FAIL', '面向 +Z',
        f"腳尖 z {jp['LeftToeBase'][2]:.3f} > 腳踝 z {jp['LeftFoot'][2]:.3f}")
    # ---- materials / textures
    mats = gl.get('materials', [])
    unlit = [m.get('name') for m in mats if 'KHR_materials_unlit' in m.get('extensions', {})]
    tex_info = []; ok_tex = True
    try:
        import cv2
    except ImportError:
        cv2 = None
    for m in mats:
        bct = m.get('pbrMetallicRoughness', {}).get('baseColorTexture')
        if bct is None:
            ok_tex = False; tex_info.append(f"{m.get('name')}: 無貼圖"); continue
        img = gl['images'][gl['textures'][bct['index']]['source']]
        bv = gl['bufferViews'][img['bufferView']]
        data = np.frombuffer(bin_, np.uint8, bv['byteLength'], bv.get('byteOffset', 0))
        if cv2 is not None:
            dec = cv2.imdecode(data, cv2.IMREAD_COLOR)
            if dec is None:
                ok_tex = False; tex_info.append(f"{m.get('name')}: 貼圖無法解碼"); continue
            tex_info.append(f"{m.get('name')}: {dec.shape[1]}x{dec.shape[0]} {img.get('mimeType', '')}")
        else:
            tex_info.append(f"{m.get('name')}: {img.get('mimeType', '')}")
    rep('PASS' if ok_tex and mats else 'FAIL', '材質 / 貼圖', '；'.join(tex_info) or '沒有材質')
    if expect_unlit:
        rep('PASS' if len(unlit) == len(mats) else 'FAIL', '無光照材質', f'{len(unlit)} / {len(mats)} 個材質有 KHR_materials_unlit')
    # ---- pose test: LeftArm down 70 deg about the world Z axis at the shoulder
    local = {i: trs_matrix(nd) for i, nd in enumerate(nodes)}
    la = idx['LeftArm']
    pivot = W[la][:3, 3]
    T = np.eye(4); T[:3, 3] = pivot; Ti = np.eye(4); Ti[:3, 3] = -pivot
    Wp = W[parent[la]]
    local[la] = np.linalg.inv(Wp) @ (T @ axis_rot([0, 0, 1], -70) @ Ti) @ W[la]
    W2, _ = world_matrices(gl, local)
    posed = skin_positions(W2)
    tip = int(np.argmax(rest[:, 0]))
    d = posed[tip] - rest[tip]
    finite = bool(np.isfinite(posed).all())
    rep('PASS' if np.linalg.norm(d) > 0.2 and d[1] < -0.1 else 'FAIL', '擺姿勢',
        f'LeftArm 往下轉 70° 後，左手指尖從 ({rest[tip, 0]:.2f}, {rest[tip, 1]:.2f}) 移到 ({posed[tip, 0]:.2f}, {posed[tip, 1]:.2f})，移動 {np.linalg.norm(d):.2f} m')
    moved_other = np.linalg.norm(posed - rest, axis=1)
    foot = int(np.argmin(rest[:, 1]))
    rep('PASS' if moved_other[foot] < 1e-4 else 'FAIL', '只有手臂動', f'腳底頂點移動 {moved_other[foot] * 1000:.2f} mm（應為 0）')
    rep('PASS' if finite else 'FAIL', '數值', '變形後所有頂點都是有限數值' if finite else '變形後出現 NaN / Inf')
    # ---- textured head renders: long straight dark lines on the skin (texture stripes, misregistered seams)
    if cv2 is not None:
        texs = {}
        for k, m in enumerate(mats):
            bct = m.get('pbrMetallicRoughness', {}).get('baseColorTexture')
            if bct is not None:
                img = gl['images'][gl['textures'][bct['index']]['source']]
                bv = gl['bufferViews'][img['bufferView']]
                texs[k] = cv2.imdecode(np.frombuffer(bin_, np.uint8, bv['byteLength'], bv.get('byteOffset', 0)), cv2.IMREAD_COLOR)
        parts = skin_positions(W, split=True)
        neck_y = jp['Neck'][1]
        lines_px, imgs = head_stripe_check(prims, parts, texs, neck_y)
        if render_dir:
            os.makedirs(render_dir, exist_ok=True)
            for nm, im in imgs.items():
                cv2.imwrite(os.path.join(render_dir, f'head_{nm}.png'), im)
        worst = max(lines_px.values()) if lines_px else 0
        lvl = 'PASS' if worst <= STRIPE_WARN else 'WARN' if worst <= STRIPE_FAIL else 'FAIL'
        rep(lvl, '頭部貼圖條紋', '皮膚上又細又長的暗線（像素）：' + '、'.join(f'{k} {v}' for k, v in lines_px.items()) +
            f'（應 ≤ {STRIPE_WARN}，> {STRIPE_FAIL} 判 FAIL）' + (f'；渲染圖 {render_dir}' if render_dir else '') +
            ('' if lvl == 'PASS' else ' → 頭部貼圖有黑條 / 接縫：看渲染圖位置，檢查對應的頭部特寫照片與烘焙'))
    if validator:
        run_validator(path, rep)
    return rep


STRIPE_WARN, STRIPE_FAIL = 60, 200        # pixels of thin, long dark lines on the skin per 512 px head render
HEAD_VIEWS = {'front': 0, 'left45': 45, 'right45': -45, 'left90': 90, 'right90': -90}


def head_stripe_check(prims, parts, texs, neck_y, size=512, seg=70):
    """render the textured head (point splatting + z-buffer) from 5 views and measure long straight dark lines on
    the skin. Returns ({view: pixels}, {view: image})."""
    import cv2
    rng = np.random.default_rng(0)
    pts, cols = [], []
    for p, P in zip(prims, parts):
        if p['tri'] is None or p['uv'] is None or p['mat'] not in texs:
            continue
        tri = p['tri']; keep = (P[tri][:, :, 1] > neck_y - 0.02).all(1) & (np.abs(P[tri][:, :, 0]) < 0.15).all(1)   # head, not the T-pose arms
        tri = tri[keep]
        if not len(tri):
            continue
        tex = texs[p['mat']]; th_, tw_ = tex.shape[:2]
        A, B, C = P[tri[:, 0]], P[tri[:, 1]], P[tri[:, 2]]
        area = 0.5 * np.linalg.norm(np.cross(B - A, C - A), axis=1)
        nsamp = np.clip((area / area.sum() * 1_500_000).astype(int), 1, 400)
        ti = np.repeat(np.arange(len(tri)), nsamp)
        r1, r2 = rng.random(len(ti)), rng.random(len(ti)); sq = np.sqrt(r1)
        b0, b1, b2 = 1 - sq, sq * (1 - r2), sq * r2
        t3 = tri[ti]
        pts.append(b0[:, None] * P[t3[:, 0]] + b1[:, None] * P[t3[:, 1]] + b2[:, None] * P[t3[:, 2]])
        uvp = b0[:, None] * p['uv'][t3[:, 0]] + b1[:, None] * p['uv'][t3[:, 1]] + b2[:, None] * p['uv'][t3[:, 2]]
        cols.append(tex[np.clip((uvp[:, 1] * th_).astype(int), 0, th_ - 1), np.clip((uvp[:, 0] * tw_).astype(int), 0, tw_ - 1)])
    if not pts:
        return {}, {}
    X = np.concatenate(pts); Cc = np.concatenate(cols)
    ctr = (X.min(0) + X.max(0)) / 2; ext = (X.max(0) - X.min(0)).max()
    out, imgs = {}, {}
    for nm, ph in HEAD_VIEWS.items():
        a_ = np.radians(ph)
        r = np.array([np.cos(a_), 0, -np.sin(a_)]); f = np.array([np.sin(a_), 0, np.cos(a_)])
        s_ = 0.92 * size / ext
        cx = ((X - ctr) @ r * s_ + size / 2).astype(int); cy = (size / 2 - (X[:, 1] - ctr[1]) * s_).astype(int)
        ok = (cx >= 0) & (cx < size) & (cy >= 0) & (cy < size)
        pix = cy[ok] * size + cx[ok]; dep = (X[ok] @ f)
        order = np.lexsort((-dep, pix)); pix_s = pix[order]
        first = np.r_[True, pix_s[1:] != pix_s[:-1]]
        img = np.full((size * size, 3), 255, np.uint8); fill = np.zeros(size * size, np.uint8)
        img[pix_s[first]] = Cc[ok][order][first]; fill[pix_s[first]] = 1
        img = img.reshape(size, size, 3); fill = fill.reshape(size, size)
        sil = cv2.morphologyEx(fill, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
        holes = (sil > 0) & (fill == 0)
        if holes.any():                                      # close the small gaps between splats
            img = np.where(holes[..., None], cv2.medianBlur(img, 5), img)
        img[sil == 0] = 255
        imgs[nm] = img
        # long straight dark lines on the skin
        L = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)[..., 0].astype(np.int16)
        med = cv2.medianBlur(img, 31)
        hsv = cv2.cvtColor(med, cv2.COLOR_BGR2HSV)
        skin = ((hsv[..., 0] < 25) | (hsv[..., 0] > 165)) & (hsv[..., 1] > 12) & (hsv[..., 1] < 180) & (hsv[..., 2] > 110)
        skin &= cv2.erode(sil, np.ones((9, 9), np.uint8)) > 0
        Lmed = cv2.cvtColor(med, cv2.COLOR_BGR2LAB)[..., 0].astype(np.int16)
        dark = ((L < Lmed - 60) & (L < 70) & skin).astype(np.uint8)
        # thin and long dark structures (a straight texture line is curved once it wraps around the head):
        # mean width <= 6 px and length >= 5 cm. Lashes (~3 cm), the mouth line (~4.5 cm) and nostrils are shorter.
        min_len = 0.05 * s_
        n_, lb, st, _ = cv2.connectedComponentsWithStats(dark, connectivity=8)
        longl = np.zeros_like(dark)
        for q in range(1, n_):
            x_, y_, w_, h_, area = st[q]
            if area < 10:
                continue
            comp = (lb[y_:y_ + h_, x_:x_ + w_] == q).astype(np.uint8)
            length = np.hypot(w_, h_)
            width = 2 * cv2.distanceTransform(comp, cv2.DIST_L2, 3).max()
            if length >= min_len and width <= 6 and area >= 2 * min_len:   # thin everywhere, long, not a speck
                longl[y_:y_ + h_, x_:x_ + w_] |= comp
        out[nm] = int(longl.sum())
        if out[nm]:
            imgs[nm] = img.copy(); imgs[nm][longl > 0] = (0, 0, 255)
    return out, imgs


def main():
    ap = argparse.ArgumentParser(description=f'verify_glb {__version__}')
    ap.add_argument('glb')
    ap.add_argument('--expect-unlit', action='store_true')
    ap.add_argument('--height', type=float, default=1.65)
    ap.add_argument('--no-validator', action='store_true')
    ap.add_argument('--renders', help='把頭部渲染圖存到這個資料夾（條紋會標紅）')
    ap.add_argument('--version', action='version', version=f'verify_glb {__version__}')
    a = ap.parse_args()
    rep = verify(a.glb, a.expect_unlit, a.height, not a.no_validator, a.renders)
    nF, nW = rep.count('FAIL'), rep.count('WARN')
    print(f'\n總結: {nF} 個 FAIL, {nW} 個 WARN, {rep.count("PASS")} 個 PASS')
    sys.exit(1 if nF else 0)


if __name__ == '__main__':
    main()
