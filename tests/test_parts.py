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
    res = dict(views=[dict(view='head_090deg', kind='head', level='FAIL', worst='頭髮',
                           parts={'頭髮': [30.0, 22.0, 9.2], '皮膚': [60.0, 61.0, 1.0]})])
    line, = pc.lines(res)
    assert line.startswith('[FAIL] head_090deg 分塊比對: 頭髮 9.2%、皮膚 1.0%') and '「頭髮」' in line and '比照片小' in line
