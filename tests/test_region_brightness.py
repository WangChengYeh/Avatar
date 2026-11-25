import csv

import cv2
import numpy as np

from check_turnaround import photo_region_lightness, report_region_lightness


def avatar(feet_l=173):
    lab = np.full((320, 240, 3), (255, 128, 128), dtype=np.uint8)
    lab[20:49, 101:139] = (65, 139, 144)       # hair
    lab[49:84, 101:139] = (178, 136, 145)      # face/neck
    lab[84:113, 38:202] = (178, 136, 145)      # arms
    lab[102:151, 91:149] = (128, 148, 137)     # top
    lab[151:165, 91:149] = (178, 136, 145)     # skin
    lab[165:268, 91:117] = (62, 131, 125)      # pants
    lab[165:268, 123:149] = (62, 131, 125)
    lab[268:300, 87:117] = (feet_l, 136, 145)   # feet
    lab[268:300, 123:153] = (feet_l, 136, 145)
    return cv2.cvtColor(lab, cv2.COLOR_LAB2BGR), lab[..., 0] < 255


def test_opencv_segments_different_avatar_materials():
    im, mask = avatar()
    _, labels, stats = photo_region_lightness(im, mask, 'main')
    assert set(stats) == {'feet', 'top', 'pants', 'hair', 'skin'}
    assert not labels[~mask].any()
    assert len(np.unique([labels[280, 105], labels[125, 110], labels[210, 105],
                          labels[31, 120], labels[98, 80]])) == 5
    assert stats['feet'][0] > stats['pants'][0] + 80


def test_only_the_dimmed_region_warns_and_hidden_feet_are_unmeasured(tmp_path, capsys):
    reference, mask = avatar()
    dark, _ = avatar(feet_l=140)
    views = {a: dict(name=f'level_{a}.jpg', im=reference, m=mask) for a in (0, 45, 90, 135)}
    report_region_lightness(views, {'low20': {0: dict(name='dim.jpg', im=dark, m=mask)},
                                  'top': {0: dict(name='top.jpg', im=reference, m=mask)}}, tmp_path)
    output = capsys.readouterr().out
    assert '[WARN] dim.jpg 分區亮度' in output
    assert '[FAIL]' not in output
    with (tmp_path / 'region_brightness.csv').open(encoding='utf-8-sig', newline='') as stream:
        rows = {(r['image'], r['region']): r for r in csv.DictReader(stream)}
    assert rows['dim.jpg', 'feet']['status'] == 'WARN'
    assert float(rows['dim.jpg', 'feet']['delta_l']) < -30
    assert all(rows['dim.jpg', region]['status'] == 'PASS' for region in ('top', 'pants', 'hair', 'skin'))
    assert rows['top.jpg', 'feet']['status'] == 'NOT_MEASURED'
    assert (tmp_path / 'dim_regions.png').is_file()
