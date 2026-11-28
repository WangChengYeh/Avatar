"""guides.py（先給輪廓再畫，docs/papers/11-guides-first.md）: the outlines a stage is drawn on come from the photos
already drawn, perfect photos follow every one of them, and a photo that does not is named"""
import os
import shutil

import cv2
import numpy as np

import guides as g
import next_step as ns


def setup_module():
    os.environ['NEXT_STEP_OFFLINE'] = '1'
    ns.code_changed_since = lambda commit: False
    ns.orders = lambda: {}                         # Claude's live orders (body3d/orders.json) are not part of these tests


def some(src, dst, names=None):
    os.makedirs(dst, exist_ok=True)
    for n in names or g.ALL:
        shutil.copyfile(os.path.join(str(src), n + '.jpg'), os.path.join(dst, n + '.jpg'))
    return str(dst)


def moved(path, dx=0, dy=0):
    """the same picture with the figure moved (white comes in at the edge): a photo drawn off its outline"""
    im = cv2.imread(path)
    M = np.float32([[1, 0, dx], [0, 1, dy]])
    cv2.imwrite(path, cv2.warpAffine(im, M, im.shape[1::-1], borderValue=(255, 255, 255)), [cv2.IMWRITE_JPEG_QUALITY, 95])


def test_perfect_photos_follow_every_line(synth_set):
    P = g.Photos(str(synth_set))
    for key, _, _ in g.STAGES:
        bad = [r for r in g.check_stage(P, key) if r['level'] != 'PASS']
        assert not bad, bad
    flips = [r['value'] for r in g.check_stage(P, 'level_b') if r['item'] == '翻轉的輪廓']
    heads = [r['value'] for r in g.check_stage(P, 'heads') if r['item'] == '和全身照的頭同一個輪廓']
    assert len(flips) == 3 and max(flips) < 1.0 and len(heads) == 8 and max(heads) < 2.0   # the outlines are exact
    assert g.status(str(synth_set))['stage'] is None


def test_the_front_photo_alone_gives_the_next_four_their_lines(synth_set, tmp_path):
    photos = some(synth_set, tmp_path / 'photos', [g.FULL[0]])
    st = g.make(photos, str(tmp_path / 'guides'))
    assert st['stage'] == 2 and set(st['draw']) == {g.FULL[a] for a in (180, 45, 90, 135)} and not st['redo']
    P = g.Photos(photos); L = g.front_lines(P.mask(g.FULL[0]))
    # the back view: the front outline flipped, as a filled shape
    back = cv2.imread(os.path.join(str(tmp_path / 'guides'), st['files'][g.FULL[180]]))
    line = (np.abs(back.astype(int) - g.BLUE).sum(2) < 90).astype(np.uint8)       # the blue outline, filled in
    cnt, _ = cv2.findContours(line, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    shape = cv2.erode(cv2.drawContours(np.zeros_like(line), cnt, -1, 1, -1), np.ones((5, 5), np.uint8)) > 0   # the line is 4 px
    assert g.differ(shape, P.mask(g.FULL[0])[:, ::-1]) < 1.5
    # the 45 degree view: the hand tips at cos 45 of the front photo's, the arms' edges at the front photo's rows
    d45 = cv2.imread(os.path.join(str(tmp_path / 'guides'), st['files'][g.FULL[45]]))
    grey = np.abs(d45.astype(int) - g.GREY).sum(2) < 40
    col = int(round(L['cx'] + np.cos(np.radians(45)) * (L['tip_r'] - L['cx'])))
    assert grey[:, col].sum() > 0.4 * grey.shape[0] and grey[int(round(L['arm_top']))].sum() > 0.4 * grey.shape[1]
    assert not grey[:, int(L['tip_r'])].sum() > 0.4 * grey.shape[0]             # not the front photo's own tip
    # the side view: no arm lines, a box for the hand seen end-on
    d90 = cv2.imread(os.path.join(str(tmp_path / 'guides'), st['files'][g.FULL[90]]))
    assert (np.abs(d90.astype(int) - g.ORANGE).sum(2) < 40).sum() > 200
    text = open(st['guides'], encoding='utf-8').read()
    assert '照著畫' in text and '不能留下任何線' in text


def test_a_level_photo_off_its_flipped_outline_is_named(synth_set, tmp_path):
    photos = some(synth_set, tmp_path / 'photos')
    moved(os.path.join(photos, g.FULL[225] + '.jpg'), dx=45)                       # 4 cm to the side
    st = g.make(photos, str(tmp_path / 'guides'))
    assert st['stage'] == 3 and st['redo'] == [g.FULL[225]] and st['draw'] == [g.FULL[225]]
    items = {r['item'] for r in st['results'] if r['level'] == 'FAIL'}
    assert items == {'翻轉的輪廓'}
    guide = cv2.imread(os.path.join(str(tmp_path / 'guides'), st['files'][g.FULL[225]]))
    assert (np.abs(guide.astype(int) - g.BLUE).sum(2) < 40).sum() > 2000          # the outline to redraw it on
    assert '沒有照著線' in open(st['guides'], encoding='utf-8').read()


def test_a_diagonal_with_its_arms_at_another_height_is_named(synth_set, tmp_path):
    """ChatGPT avatar_001 R63-R83 (#130): the level diagonals' arms 1-1.4 cm higher than the front photo's"""
    photos = some(synth_set, tmp_path / 'photos', [g.FULL[a] for a in (0, 180, 45, 90, 135)])
    P = g.Photos(photos); L = g.front_lines(P.mask(g.FULL[0]))
    p = os.path.join(photos, g.FULL[45] + '.jpg'); im = cv2.imread(p)
    up = int(round(0.014 * L['s'])); a, b = int(L['arm_top']) - 3 * up, int(L['arm_bot']) + 3 * up
    arms = im[a:b].copy(); cx = int(L['cx']); half = int(0.22 * L['s'])
    for sl in (slice(0, cx - half), slice(cx + half, im.shape[1])):                 # the arms only, not the torso
        im[a:b, sl] = 255; im[a - up:b - up, sl] = arms[:, sl]
    cv2.imwrite(p, im, [cv2.IMWRITE_JPEG_QUALITY, 95])
    st = g.status(photos)
    bad = {r['item'] for r in st['results'] if r['level'] == 'FAIL'}
    assert st['stage'] == 2 and st['redo'] == [g.FULL[45]] and bad == {'手臂上緣的高度', '手臂下緣的高度'}


def test_a_closeup_framed_elsewhere_or_of_another_head_is_named(synth_set, tmp_path):
    photos = some(synth_set, tmp_path / 'photos')
    moved(os.path.join(photos, 'head_090deg.jpg'), dy=-200)                       # ChatGPT R83: the head 5 cm too high
    shutil.copyfile(os.path.join(photos, 'head_000deg.jpg'), os.path.join(photos, 'head_135deg.jpg'))   # another outline
    st = g.make(photos, str(tmp_path / 'guides'))
    assert st['stage'] == 4 and st['redo'] == ['head_090deg', 'head_135deg']
    by = {}
    for r in st['results']:
        if r['level'] == 'FAIL':
            by.setdefault(r['photo'], set()).add(r['item'])
    assert by['head_090deg'] == {'頭在畫面裡的高度'}                               # its shape is right once aligned
    assert '和全身照的頭同一個輪廓' in by['head_135deg']
    # the base picture: the full-body photo's head enlarged, framed as the close-up should be
    base = cv2.imread(os.path.join(str(tmp_path / 'guides'), st['files']['head_090deg']))
    good = g.Photos(str(synth_set)).mask('head_090deg')
    r = g.head_rows(good)
    assert g.differ((g.ct.segment(base)[0] > 0)[r], good[r]) < 3.0


def test_three_tries_then_the_photo_is_let_through(synth_set, tmp_path):
    photos = some(synth_set, tmp_path / 'photos'); out = str(tmp_path / 'guides')
    p = os.path.join(photos, g.FULL[225] + '.jpg')
    for i, dx in enumerate((45, 50, 55)):
        shutil.copyfile(os.path.join(str(synth_set), g.FULL[225] + '.jpg'), p); moved(p, dx=dx)
        st = g.make(photos, out)
        if i < g.MAX_TRIES - 1:
            assert st['stage'] == 3 and g.make(photos, out)['stage'] == 3          # asking again is not another try
    # let through: gate 1 is the judge from here. The next stage goes on from the photo as it is (its close-up is
    # measured against it)
    assert st['stage'] == 4 and st['waived'] == [g.FULL[225]] and st['redo'] == ['head_225deg']


def test_a_new_avatar_is_drawn_stage_by_stage(synth_set, tmp_path):
    ws = tmp_path / 'avatar' / 'gemini' / 'avatar_009'; ws.mkdir(parents=True); state = {}
    go = lambda: ns.decide(str(ws), 'avatar_009', 'Gemini', 'avatar_009', None, state)
    r = go()
    assert r['state'] == 'DRAW' and '第 1 段' in r['why']
    photos = str(ws / 'v001' / 'photos')
    seen = []
    for key, title, names in g.STAGES:
        some(synth_set, photos, names)
        r = go(); seen.append(r['state'])
        if key != g.STAGES[-1][0]:
            nxt = g.STAGES[[k for k, _, _ in g.STAGES].index(key) + 1]
            assert r['state'] == 'DRAW' and nxt[1] in r['why'] and all(n in r['steps'][0] for n in nxt[2]), r
            assert all(os.path.exists(ws / 'v001' / 'guides' / f'{n}_guide.png') for n in nxt[2])
    assert seen[-1] == 'RUN' and 'v001/output' in r['steps'][0]                   # all six drawn: the four gates


def test_claudes_order_moves_an_avatar_to_stages(synth_set, tmp_path, monkeypatch):
    import json
    ws = tmp_path / 'avatar' / 'chatgpt' / 'avatar_001'; v1 = ws / 'v001'
    some(synth_set, str(v1 / 'photos')); (v1 / 'output').mkdir()
    moved(str(v1 / 'photos' / 'head_090deg.jpg'), dy=-200)
    json.dump(dict(gates={'1 照片檢查': dict(FAIL=4, WARN=0, PASS=9)}, deliverable=False, code=dict(commit='abc1234')),
              open(v1 / 'output' / 'gates.json', 'w'))
    (v1 / 'output' / 'run_all.log').write_text('  [FAIL] 45° 全視角外殼覆蓋: x\n', encoding='utf-8')
    state = dict(waiting=dict(kind='issue', number=130, code='x'))
    monkeypatch.setattr(ns, 'orders', lambda: {'chatgpt/avatar_001': dict(do='staged', id='t1', issue=130, why='理由。')})
    go = lambda: ns.decide(str(ws), 'avatar_001', 'ChatGPT', 'avatar_001', None, state)
    r = go()
    assert r['state'] == 'DRAW' and 'v002' in r['steps'][0] and 'cp ' in r['steps'][0] and '理由' in r['why']
    assert state['waiting'] is None and state['report_to'] == dict(kind='issue', number=130)
    assert go()['steps'][0] == r['steps'][0]                                      # not copied yet: asked again
    some(v1 / 'photos', str(ws / 'v002' / 'photos'))
    r = go()
    assert r['state'] == 'DRAW' and '第 4 段' in r['why'] and 'head_090deg（頭在畫面裡的高度）' in r['why']
    assert 'head_090deg' in r['steps'][0] and 'head_045deg' not in r['steps'][0]  # the photos that follow are kept
    shutil.copyfile(os.path.join(str(synth_set), 'head_090deg.jpg'), ws / 'v002' / 'photos' / 'head_090deg.jpg')
    r = go()
    assert r['state'] == 'RUN' and 'v002/output' in r['steps'][0]


def test_an_empty_newest_version_is_filled_from_the_last_one_never_started_over(synth_set, tmp_path):
    """the copy into the new version did not happen (v002/photos is empty): asking for "the front photo" again would
    make a new person; the photos are copied from v001"""
    import json
    ws = tmp_path / 'avatar' / 'gemini' / 'avatar_001'; v1 = ws / 'v001'
    some(synth_set, str(v1 / 'photos')); (v1 / 'output').mkdir()
    json.dump(dict(gates={'4 最終驗收': dict(FAIL=7, WARN=0, PASS=9)}, deliverable=False, code=dict(commit='abc1234')),
              open(v1 / 'output' / 'gates.json', 'w'))
    (ws / 'v002' / 'photos').mkdir(parents=True)
    state = dict(staged=dict(order='t1', version=2))
    r = ns.decide(str(ws), 'avatar_001', 'Gemini', 'avatar_001', None, state)
    assert r['state'] == 'DRAW' and 'cp ' in r['steps'][0] and 'v001/photos' in r['steps'][0] and 'v002/photos' in r['steps'][0]
    assert '第 1 段' not in r['why'] and '01_000deg_front' not in r['steps'][0]


def test_a_photo_let_through_stays_let_through_in_the_next_version(synth_set, tmp_path):
    """a retouch round opens a new version with the photos copied: the three tries do not start again"""
    ws = tmp_path / 'avatar' / 'gemini' / 'avatar_009'
    p1 = some(synth_set, str(ws / 'v001' / 'photos')); bad = os.path.join(p1, g.FULL[225] + '.jpg')
    for dx in (45, 50, 55):
        shutil.copyfile(os.path.join(str(synth_set), g.FULL[225] + '.jpg'), bad); moved(bad, dx=dx)
        ns.draw_step(str(ws), 1, p1, 'me')
    p2 = some(p1, str(ws / 'v002' / 'photos'))
    r = ns.draw_step(str(ws), 2, p2, 'me')
    assert r is None or g.FULL[225] not in r['steps'][0], r                       # not asked for again
    assert os.path.exists(ws / 'stage_log.json') and not os.path.exists(ws / 'v002' / 'guides' / 'stage_log.json')


def test_the_arm_is_the_first_run_from_the_top_of_a_column(synth_set):
    """a hip or thigh that reaches under the arm in a diagonal view is not the arm's lower edge"""
    P = g.Photos(str(synth_set)); L = g.front_lines(P.mask(g.FULL[0]))
    m = P.mask(g.FULL[45]).copy(); c = np.cos(np.radians(45))
    clean = g.arm_band(m, L, c)
    a, b = int(L['cx'] + 0.22 * L['s'] * c), int(L['cx'] + 0.60 * L['s'] * c)
    m[int(clean[1] + 0.05 * L['s']):L['floor'], a:b] = True                       # a block under one arm, 5 cm below it
    assert np.allclose(g.arm_band(m, L, c), clean, atol=1.0)


def test_the_33_are_counted_by_name(synth_set, tmp_path):
    assert set(ns.ALL33) == set(g.ALL) and len(ns.ALL33) == 33
    ws = tmp_path / 'avatar' / 'gemini' / 'avatar_009'
    photos = some(synth_set, str(ws / 'v001' / 'photos'), [n for n in g.ALL if n != 'top'])
    shutil.copyfile(os.path.join(photos, g.FULL[0] + '.jpg'), os.path.join(photos, 'extra.jpg'))   # 33 files, 32 of the spec
    r = ns.decide(str(ws), 'avatar_009', 'Gemini', 'avatar_009', None, {})
    assert r['state'] == 'DRAW' and '第 5 段' in r['why'] and 'top' in r['steps'][0]
