"""技術報告（docs/papers/，Claude 的持續任務：docs/Project-Loop.md）的格式檢查。只讀檔，不需要 Jekyll。"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / 'docs'
PAPERS = sorted((DOCS / 'papers').glob('[0-9][0-9]-*.md'))
STATES = {'solved', 'mitigated', 'open', 'concluded'}
PARTS = ('原先的演算法', '遇到的問題', '新的做法', '結果')
KEYS = ('layout', 'number', 'title', 'subtitle', 'summary', 'date_text', 'version', 'state', 'status', 'abstract')


def split(path):
    """(front matter text, body) of one paper"""
    m = re.match(r'---\n(.*?)\n---\n(.*)', path.read_text(encoding='utf-8'), re.S)
    assert m, f'{path.name}: 沒有 front matter'
    return m.group(1), m.group(2)


def top(front, key):
    """a top-level scalar of the front matter (the papers keep these on one line)"""
    m = re.search(rf'^{key}:[ \t]*(.*)$', front, re.M)
    return m.group(1).strip() if m else None


def test_there_are_papers_and_a_site():
    assert len(PAPERS) >= 10
    for f in ('_config.yml', 'index.md', 'glossary.md', '_layouts/default.html', '_layouts/paper.html',
              '_includes/chart.html', 'assets/paper.css'):
        assert (DOCS / f).is_file(), f


def test_front_matter():
    numbers = []
    for p in PAPERS:
        front, _ = split(p)
        for k in KEYS:
            assert top(front, k) is not None, f'{p.name}: front matter 缺 {k}'
        assert top(front, 'layout') == 'paper', p.name
        assert top(front, 'state') in STATES, f'{p.name}: state 要是 {sorted(STATES)} 之一'
        n = int(top(front, 'number'))
        assert p.name.startswith(f'{n:02d}-'), f'{p.name}: 檔名開頭要是 number'
        numbers.append(n)
    assert numbers == list(range(1, len(PAPERS) + 1)), f'number 要從 1 連號：{numbers}'


def test_charts_and_figures_exist():
    for p in PAPERS:
        front, body = split(p)
        for cid in re.findall(r'\{%\s*include chart\.html id="([^"]+)"\s*%\}', body):
            assert re.search(rf'^  {re.escape(cid)}:\s*$', front, re.M), f'{p.name}: charts 裡沒有 {cid}'
        for fig in re.findall(r'\{%\s*include (figs/[^\s%]+)\s*%\}', body):
            f = DOCS / '_includes' / fig
            assert f.is_file(), f'{p.name}: 找不到 {fig}'
            svg = f.read_text(encoding='utf-8')
            assert '<svg' in svg and 'aria-label=' in svg and '<figcaption>' in svg, f'{fig}: 要有 svg、aria-label、figcaption'
        figs = [int(n) for n in re.findall(r'^    n: (\d+)$', front, re.M)]
        figs += [int(n) for fig in re.findall(r'\{%\s*include (figs/[^\s%]+)\s*%\}', body)
                 for n in re.findall(r'<strong>圖 (\d+)</strong>', (DOCS / '_includes' / fig).read_text(encoding='utf-8'))]
        assert sorted(figs) == list(range(1, len(figs) + 1)), f'{p.name}: 圖的編號要從 1 連號、不重複：{sorted(figs)}'


def test_revised_papers_follow_the_format():
    """改寫過的篇（revised: true）：每一顆雷四段齊全、有示意圖、有「還沒解決的」"""
    revised = [p for p in PAPERS if top(split(p)[0], 'revised') == 'true']
    assert revised, '至少第 5 篇是新格式'
    for p in revised:
        _, body = split(p)
        counts = [len(re.findall(rf'^### {part}\s*$', body, re.M)) for part in PARTS]
        assert counts[0] >= 1 and len(set(counts)) == 1, f'{p.name}: 每一顆雷都要有四段 {PARTS}，現在是 {counts}'
        assert re.search(r'\{%\s*include figs/', body), f'{p.name}: 要有示意圖'
        front = split(p)[0]
        learn = re.search(r'^learn:\n((?:  - .+\n)+)', front + '\n', re.M)
        assert learn and len(learn.group(1).strip().splitlines()) >= 3, f'{p.name}: 要有「看完會知道」（learn，至少 3 條）'
        assert re.search(r'^## 還沒解決的', body, re.M), f'{p.name}: 要有「還沒解決的」'
        assert re.search(r'^## 參考', body, re.M), f'{p.name}: 要有「參考」'


def test_no_photos_or_drive_links():
    files = PAPERS + [DOCS / 'index.md'] + sorted((DOCS / '_includes').rglob('*.html'))
    for f in files:
        text = f.read_text(encoding='utf-8')
        for bad in ('drive.google.com', 'docs.google.com', 'drive.usercontent', '<img', '<image', '!['):
            assert bad not in text, f'{f.relative_to(ROOT)}: 不能有 {bad}（不放照片與雲端硬碟連結）'


def test_handoff_tracks_every_paper():
    """交接清單的「持續任務」一節列了每一篇，格式欄和檔案一致"""
    text = (DOCS / 'Handoff.md').read_text(encoding='utf-8')
    m = re.search(r'^## 持續任務：技術報告\n(.*?)(?=^## )', text, re.S | re.M)
    assert m, '交接清單要有「持續任務：技術報告」一節'
    rows = {int(n): fmt for n, fmt in re.findall(r'^\| (\d+) \| [^|]+ \| ([^|]+) \|', m.group(1), re.M)}
    for p in PAPERS:
        front, _ = split(p)
        n = int(top(front, 'number'))
        assert n in rows, f'交接清單「持續任務」少了第 {n} 篇'
        new = top(front, 'revised') == 'true'
        assert rows[n].strip().startswith('新' if new else '舊'), f'第 {n} 篇：交接清單寫「{rows[n].strip()}」，檔案是{"新" if new else "舊"}格式'
