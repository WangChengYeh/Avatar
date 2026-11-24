"""verify_glb.py：好的 GLB 要通過；骨頭名稱錯、權重錯、材質錯要被抓出來"""
import json, struct
import numpy as np
import pytest
import verify_glb as vg
from conftest import run_py, lines


def rewrite_glb(src, dst, edit_json=None, edit_bin=None):
    gl, bin_ = vg.load_glb(src)
    if edit_json:
        edit_json(gl)
    bin_ = bytearray(bin_)
    if edit_bin:
        edit_bin(gl, bin_)
    js = json.dumps(gl, separators=(',', ':')).encode()
    js += b' ' * (-len(js) % 4)
    bin_ += b'\0' * (-len(bin_) % 4)
    body = struct.pack('<I4s', len(js), b'JSON') + js + struct.pack('<I4s', len(bin_), b'BIN\0') + bytes(bin_)
    open(dst, 'wb').write(struct.pack('<4sII', b'glTF', 2, 12 + len(body)) + body)


def verify(path, *extra):
    return run_py('verify_glb.py', path, '--no-validator', *extra)


def test_good_model_passes(model_glb):
    rc, out = verify(model_glb, '--expect-unlit')
    assert rc == 0, '\n'.join(lines(out, 'FAIL'))
    assert len(lines(out, 'PASS')) >= 18


def test_in_process_api(model_glb):
    rep = vg.verify(model_glb, expect_unlit=True, validator=False)
    assert rep.count('FAIL') == 0
    names = {i[1] for i in rep.items}
    for item in ('骨頭名稱', '骨頭階層', '權重加總', '擺姿勢', '面向 +Z', '材質 / 貼圖'):
        assert item in names


def test_renamed_bone_fails(model_glb, tmp_path):
    def ed(gl):
        for n in gl['nodes']:
            if n.get('name') == 'LeftForeArm':
                n['name'] = 'mixamorig:LeftForeArm'
    bad = tmp_path / 'renamed.glb'
    rewrite_glb(model_glb, bad, ed)
    rc, out = verify(bad)
    assert rc == 1
    assert any('LeftForeArm' in l for l in lines(out, 'FAIL'))


def test_wrong_parent_fails(model_glb, tmp_path):
    """把 LeftHand 從 LeftForeArm 移到 Spine2 底下"""
    def ed(gl):
        nm = {n.get('name'): i for i, n in enumerate(gl['nodes'])}
        fa, hand, sp = nm['LeftForeArm'], nm['LeftHand'], nm['Spine2']
        gl['nodes'][fa]['children'].remove(hand)
        gl['nodes'][sp].setdefault('children', []).append(hand)
    bad = tmp_path / 'parent.glb'
    rewrite_glb(model_glb, bad, ed)
    rc, out = verify(bad)
    assert rc == 1
    assert any('階層' in l and 'LeftHand' in l for l in lines(out, 'FAIL'))


def test_unnormalised_weights_fail(model_glb, tmp_path):
    def eb(gl, bin_):
        mesh = gl['meshes'][0]['primitives'][0]
        a = gl['accessors'][mesh['attributes']['WEIGHTS_0']]
        bv = gl['bufferViews'][a['bufferView']]
        off = bv.get('byteOffset', 0) + a.get('byteOffset', 0)
        w = np.frombuffer(bin_, np.float32, a['count'] * 4, off).copy()
        w[: 4 * 100] *= 0.5                                # first 100 vertices sum to 0.5
        bin_[off:off + w.nbytes] = w.tobytes()
    bad = tmp_path / 'weights.glb'
    rewrite_glb(model_glb, bad, edit_bin=eb)
    rc, out = verify(bad)
    assert rc == 1
    assert any('權重加總' in l and '100' in l for l in lines(out, 'FAIL'))


def test_missing_texture_fails(model_glb, tmp_path):
    def ed(gl):
        del gl['materials'][0]['pbrMetallicRoughness']['baseColorTexture']
    bad = tmp_path / 'notex.glb'
    rewrite_glb(model_glb, bad, ed)
    rc, out = verify(bad)
    assert rc == 1
    assert any('貼圖' in l for l in lines(out, 'FAIL'))


def test_expect_unlit_fails_on_lit(model_glb, tmp_path):
    def ed(gl):
        for m in gl['materials']:
            m.pop('extensions', None)
        gl.pop('extensionsUsed', None)
    lit = tmp_path / 'lit.glb'
    rewrite_glb(model_glb, lit, ed)
    assert verify(lit)[0] == 0
    rc, out = verify(lit, '--expect-unlit')
    assert rc == 1 and any('KHR_materials_unlit' in l for l in lines(out, 'FAIL'))
    # glb_unlit.py 修好它
    fixed = tmp_path / 'fixed.glb'
    rc, _ = run_py('steps/glb_unlit.py', lit, fixed)
    assert rc == 0 and verify(fixed, '--expect-unlit')[0] == 0


def test_not_a_glb_fails(tmp_path):
    p = tmp_path / 'x.glb'; p.write_bytes(b'not a glb file at all')
    rc, out = verify(p)
    assert rc == 1 and lines(out, 'FAIL')


def test_trs_matches_axis_rotation():
    """四元數 → 矩陣 與 軸角旋轉一致（擺姿勢測試的數學基礎）"""
    a = np.radians(37); ax = np.array([0.3, -0.5, 0.8]); ax /= np.linalg.norm(ax)
    q = list(ax * np.sin(a / 2)) + [np.cos(a / 2)]
    M = vg.trs_matrix({'rotation': q, 'translation': [1, 2, 3]})
    R = vg.axis_rot(ax, 37)
    assert np.allclose(M[:3, :3], R[:3, :3], atol=1e-9) and np.allclose(M[:3, 3], [1, 2, 3])



def add_head_stripes(src, dst, width=24, step=175):
    """複製 GLB，在 Head 貼圖畫黑色直線（審查第 3 項的做法：24 px 寬、間距 175 px）"""
    import cv2
    gl, bin_ = vg.load_glb(src)
    views = gl['bufferViews']
    blobs = [bin_[v.get('byteOffset', 0):v.get('byteOffset', 0) + v['byteLength']] for v in views]
    mi = [i for i, m in enumerate(gl['materials']) if m.get('name') == 'Head'][0]
    img = gl['images'][gl['textures'][gl['materials'][mi]['pbrMetallicRoughness']['baseColorTexture']['index']]['source']]
    tex = cv2.imdecode(np.frombuffer(blobs[img['bufferView']], np.uint8), cv2.IMREAD_COLOR)
    for x in range(0, tex.shape[1], step):
        tex[:, x:x + width] = 0
    blobs[img['bufferView']] = cv2.imencode('.jpg', tex, [cv2.IMWRITE_JPEG_QUALITY, 92])[1].tobytes()
    out = bytearray()
    for v, b in zip(views, blobs):
        out += b'\0' * (-len(out) % 4); v['byteOffset'] = len(out); v['byteLength'] = len(b); out += b
    out += b'\0' * (-len(out) % 4); gl['buffers'][0]['byteLength'] = len(out)
    js = json.dumps(gl, separators=(',', ':')).encode(); js += b' ' * (-len(js) % 4)
    body = struct.pack('<I4s', len(js), b'JSON') + js + struct.pack('<I4s', len(out), b'BIN\0') + bytes(out)
    open(dst, 'wb').write(struct.pack('<4sII', b'glTF', 2, 12 + len(body)) + body)


def test_head_stripes_fail_and_normal_texture_passes(model_glb, tmp_path):
    """審查第 3 項：頭部貼圖加黑條要 FAIL；正常貼圖（含睫毛、鼻孔等暗細節）要 PASS"""
    rc, out = verify(model_glb, '--renders', tmp_path / 'ok')
    assert any('頭部貼圖條紋' in l for l in lines(out, 'PASS')), out[-1500:]
    bad = tmp_path / 'striped.glb'
    add_head_stripes(model_glb, bad)
    rc, out = verify(bad, '--renders', tmp_path / 'bad')
    assert rc == 1 and any('頭部貼圖條紋' in l for l in lines(out, 'FAIL'))
    assert (tmp_path / 'bad' / 'head_front.png').exists()
