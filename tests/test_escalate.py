"""escalate.py (docs/Project-Loop.md): the issue body an executor sends to Claude"""
import json

import escalate


def test_auto_reason():
    g = lambda *f: dict(gates={f'{i + 1} x': dict(FAIL=v, WARN=0, PASS=1) for i, v in enumerate(f)})
    assert escalate.auto_reason([], dict(state='stopped'), g(0, 0)) == escalate.REASONS[3]          # program error
    assert escalate.auto_reason([dict(confidence='低')], {}, g(1)) == escalate.REASONS[0]
    assert escalate.auto_reason([], {}, g(0, 0, 0, 1)) == escalate.REASONS[2]                        # R17: only stage 4
    assert escalate.auto_reason([dict(confidence='高')], {}, g(2)) is None                            # fix it yourself


def test_body(tmp_path):
    json.dump(dict(gates={'1 照片檢查': dict(FAIL=2, WARN=3, PASS=9)}, deliverable=False), open(tmp_path / 'gates.json', 'w'))
    json.dump([dict(item='head 45° 臉部位置', owner='照片', confidence='高', cause='c', action='AI 修圖', path=['關卡 1'],
                    order=1, stage_name='階段 1 照片')], open(tmp_path / 'diagnosis.json', 'w'), ensure_ascii=False)
    (tmp_path / 'run_all.log').write_text('  [FAIL] head 45° 臉部位置: 8.9 mm\n', encoding='utf-8')
    b = escalate.body(str(tmp_path), 'Gemini', 'avatar-B', tried='重畫兩次')
    assert 'Gemini' in b and 'avatar-B' in b and '| 1 照片檢查 | 2 | 3 | 9 |' in b and '8.9 mm' in b and '重畫兩次' in b
