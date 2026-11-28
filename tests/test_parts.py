"""gate 4, part by part (part_compare.py): the pieces a figure is made of, compared one by one. Made-up pictures;
the whole path (GLB, cameras, photos) runs in the end-to-end tests of test_run_all.py"""
import cv2
import numpy as np

import part_compare as pc

SKIN, HAIR, TOP = (150, 175, 215), (35, 50, 70), (140, 110, 190)          # BGR


def head(bun=True, shift=0, hair=HAIR):
    """a head seen from the side: a face, hair over the top and back, a bun"""
    im = np.full((pc.SIZE, pc.SIZE, 3), 255, np.uint8)
    cv2.ellipse(im, (500 + shift, 520), (230, 290), 0, 0, 360, SKIN, -1)
    cv2.ellipse(im, (540 + shift, 430), (240, 230), 0, 180, 400, hair, -1)
    if bun:
        cv2.circle(im, (800 + shift, 520), 85, hair, -1)
    cv2.rectangle(im, (420 + shift, 800), (640 + shift, 1000), TOP, -1)
    return im, (im.sum(2) < 765)


def split(a, b):
    cen, fam = pc.palette([a, b])
    return pc.parts(a[0], a[1], cen, fam), pc.parts(b[0], b[1], cen, fam), fam


def worst(La, Lb, fam):
    tot = (La > 0).sum()
    return max(100 * pc.differs(La == k, Lb == k) / tot for k in range(1, fam.max() + 2))


def test_shades_of_one_thing_are_one_part_and_hair_is_not_skin():
    """light and shade of the skin are one part; dark hair and fair skin of about the same hue are two, also with a
    middle shade between them (Gemini avatar_001: hair L 47, shadow L 110, skin L 178, all near a 136 b 141)"""
    lab = lambda L, a, b: (L / 2, a, b)
    cen = np.array([lab(47, 136, 139), lab(178, 134, 144), lab(150, 135, 143), lab(110, 138, 140), lab(73, 128, 125),
                    lab(144, 147, 133)], np.float32)
    fam = pc.families(cen)
    assert fam[1] == fam[2], 'two shades of skin'
    assert fam[0] != fam[1], 'hair and skin chained into one part'
    assert len({fam[4], fam[5], fam[0], fam[1]}) == 4, 'the garments are parts of their own'


def test_the_same_picture_differs_by_nothing_and_a_few_pixels_are_forgiven():
    a = head()
    La, Lb, fam = split(a, head())
    assert worst(La, Lb, fam) == 0
    La, Lb, fam = split(a, head(shift=3))                    # the whole head 3 px off: inside the tolerance
    assert worst(La, Lb, fam) < 0.5


def test_a_missing_bun_shows_in_the_hair_and_only_there():
    """Gemini avatar_001 v018: the bun became a cone. The outline of the whole figure hardly moved"""
    a, b = head(), head(bun=False)
    La, Lb, fam = split(a, b)
    tot = (La > 0).sum()
    per = {k: 100 * pc.differs(La == k, Lb == k) / tot for k in range(1, fam.max() + 2)}
    hair = max(per, key=per.get)
    assert per[hair] > 100 * pc.LEVEL_FAIL, per
    assert all(v < 0.5 for k, v in per.items() if k != hair), per


def test_a_part_in_the_wrong_colour_differs():
    """a patch of the wrong colour inside the outline (an earring baked onto the jaw, hair painted grey): the
    outline is the same, the part is not"""
    a, b = head(), head(hair=(120, 120, 125))
    La, Lb, fam = split(a, b)
    assert worst(La, Lb, fam) > 100 * pc.HEAD_FAIL


def test_parts_get_names_and_the_report_says_which_one():
    front = head(bun=False); back_im = front[0].copy(); back_im[front[0].sum(2) < 765] = HAIR
    cv2.rectangle(back_im, (420, 800), (640, 1000), TOP, -1)
    back = (back_im, back_im.sum(2) < 765)
    body = np.full((pc.SIZE, pc.SIZE, 3), 255, np.uint8)
    cv2.circle(body, (512, 130), 60, SKIN, -1); cv2.ellipse(body, (512, 105), (62, 50), 0, 180, 360, HAIR, -1)
    cv2.rectangle(body, (430, 200), (594, 380), TOP, -1); cv2.rectangle(body, (440, 380), (584, 900), (60, 60, 60), -1)
    cv2.rectangle(body, (150, 210), (430, 250), SKIN, -1); cv2.rectangle(body, (594, 210), (874, 250), SKIN, -1)
    bm = body.sum(2) < 765
    cen, fam = pc.palette([front, back, (body, bm)])
    L = lambda p: pc.parts(p[0], p[1], cen, fam)
    nm = pc.names(cen, fam, L(front), L(back), L((body, bm)))
    assert {'皮膚', '頭髮', '上身的衣物', '下身的衣物'} <= set(nm), nm          # (blurred edges may add a colour of their own)


def test_a_head_is_two_parts_and_the_worst_views_are_marked_first():
    """a close-up is split into its dark and its light part only (hair, skin): with more colours the light in the
    hair became a part of its own or joined a garment, and the numbers moved with the grouping (Gemini avatar_001:
    16 % for a "garment" above the shoulders). And not everything at once: the few views that differ most, each
    against its own limit, are marked as the ones to fix this round"""
    a = head()
    cen, fam = pc.palette([a], colours=2)
    assert len(cen) == 2 and cen[0, 0] < cen[1, 0] and list(fam) == [0, 1]             # the darker one first: the hair
    L = pc.parts(a[0], a[1], cen, fam)
    assert set(np.unique(L)) == {0, 1, 2}
    res = dict(views=[
        dict(view='head_315deg', kind='head', level='FAIL', worst='頭', value=14.0, first=True, differs=12.6,
             regions={'頭': [92.0, 14.0, '皮膚', 12.9], '軀幹': [8.0, 3.0, '', 0.2]}),
        dict(view='04_135deg_back_left', kind='main', level='FAIL', worst='軀幹', value=4.1, first=False, differs=7.0,
             regions={'軀幹': [46.0, 9.0, '上身的衣物', 4.1], '頭': [11.0, 19.0, '頭髮', 2.1], '左腳': [1.5, 33.0, '皮膚', 0.5]}),
        dict(view='01_000deg_front', kind='main', level='WARN', worst='軀幹', value=1.7, first=False, differs=2.4,
             regions={'軀幹': [47.0, 3.0, '皮膚', 1.7]})])
    first, later, warn = pc.lines(res)
    assert first.startswith('[FAIL] head_315deg 分區差異: 頭 14%') and '主要是皮膚' in first and '【這一輪先修】' in first
    assert '軀幹 4.1%（該區的 9%）、頭 2.1%（該區的 19%）' in later and '【這一輪先修】的那幾個' in later
    assert warn.startswith('[WARN] 01_000deg_front') and '這一輪' not in warn


JOINTS = {k: np.array(v, float) for k, v in dict(
    Hips=(0, 0.92, 0), Spine=(0, 1.02, 0), Spine1=(0, 1.12, 0), Spine2=(0, 1.22, 0), Neck=(0, 1.36, -0.02), Head=(0, 1.45, 0),
    LeftShoulder=(0.05, 1.36, 0), LeftArm=(0.17, 1.38, 0), LeftForeArm=(0.42, 1.38, 0), LeftHand=(0.65, 1.38, 0),
    RightShoulder=(-0.05, 1.36, 0), RightArm=(-0.17, 1.38, 0), RightForeArm=(-0.42, 1.38, 0), RightHand=(-0.65, 1.38, 0),
    LeftUpLeg=(0.09, 0.88, 0), LeftLeg=(0.09, 0.48, 0), LeftFoot=(0.09, 0.08, 0), LeftToeBase=(0.09, 0.02, 0.12),
    RightUpLeg=(-0.09, 0.88, 0), RightLeg=(-0.09, 0.48, 0), RightFoot=(-0.09, 0.08, 0), RightToeBase=(-0.09, 0.02, 0.12)).items()}


def test_every_piece_of_the_surface_belongs_to_the_bone_it_lies_nearest_to():
    """the difference is split by the regions the model's joints give (the user: difference over the whole body
    first, then by joint). The side of the chest is the torso although the shoulder joint is nearer; the jaw is
    the head although the head joint sits above it"""
    pts = {'頭': [(0, 1.60, 0.02), (0, 1.43, 0.08)], '軀幹': [(0.15, 1.30, 0), (0, 1.0, 0.10), (0.10, 0.95, 0)],
           '左上臂': [(0.30, 1.38, 0.02)], '左前臂': [(0.55, 1.40, 0)], '右上臂': [(-0.30, 1.36, 0)],
           '左大腿': [(0.10, 0.70, 0.05)], '左小腿': [(0.09, 0.30, -0.03)], '左腳': [(0.09, 0.03, 0.08)], '右腳': [(-0.09, 0.03, 0.10)]}
    V, F, want = [], [], []
    for name, ps in pts.items():
        for p_ in ps:
            i = len(V); V += [p_, (p_[0] + 0.002, p_[1], p_[2]), (p_[0], p_[1] + 0.002, p_[2])]; F.append((i, i + 1, i + 2)); want.append(name)
    got = pc.face_regions(np.array(V, float), np.array(F), JOINTS)
    assert [pc.REGIONS[g][0] for g in got] == want
    assert pc.face_regions(np.array(V, float), np.array(F), {'Head': JOINTS['Head']}) is None      # no skeleton to speak of


def test_joints_are_read_from_the_model_file(tmp_path):
    """a GLB's skeleton: node transforms multiplied down the tree; 'mixamorig:' in a bone's name is dropped"""
    import json as js
    import struct
    doc = dict(scenes=[dict(nodes=[0])], nodes=[
        dict(name='Armature', translation=[0, 0.1, 0], children=[1]),
        dict(name='mixamorig:Hips', translation=[0, 0.9, 0], rotation=[0, 0, 0.7071068, 0.7071068], children=[2]),   # 90 deg about z
        dict(name='mixamorig:Spine', translation=[0.2, 0, 0]),
        dict(name='not a bone', translation=[5, 5, 5])], skins=[dict(joints=[1, 2])])
    blob = js.dumps(doc).encode(); blob += b' ' * (-len(blob) % 4)
    path = tmp_path / 'm.glb'
    path.write_bytes(struct.pack('<4sII', b'glTF', 2, 12 + 8 + len(blob)) + struct.pack('<I4s', len(blob), b'JSON') + blob)
    J = pc.glb_joints(str(path))
    assert set(J) == {'Hips', 'Spine'}
    assert np.allclose(J['Hips'], (0, 1.0, 0)) and np.allclose(J['Spine'], (0, 1.2, 0), atol=1e-5)     # x of the child turned up


def test_a_pixel_only_the_photo_has_takes_the_nearest_region():
    V = np.array([(0, 1.5, 0), (0.05, 1.5, 0), (0, 1.55, 0), (0.3, 1.38, 0), (0.35, 1.38, 0), (0.3, 1.43, 0)], float)
    F = np.array([(0, 1, 2), (3, 4, 5)]); region = np.array([0, 3])                       # a bit of head, a bit of upper arm
    cam = dict(phi=0.0, th=0.0, s=1000.0, cu=512.0, cv=1900.0)
    model = pc.render(V, F, np.zeros((2, 3), np.uint8), cam, pc.SIZE, pc.SIZE)[1]
    photo = np.zeros_like(model); photo[300:420, 480:600] = True; photo[440:540, 780:880] = True      # each drawn larger
    R = pc.region_map(V, F, region, cam, photo, model, pc.SIZE)
    assert set(np.unique(R)) == {0, 1, 4}
    assert (R[300:420, 480:600] == 1).all() and (R[440:540, 780:880] == 4).all() and R[900, 100] == 0
