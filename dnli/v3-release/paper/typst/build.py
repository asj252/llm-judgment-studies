"""Strict Markdown-to-Typst conversion for the English DNLI manuscript."""
from pathlib import Path
import json
import re
import subprocess
import shutil

HERE = Path(__file__).resolve().parent
PAPER = HERE.parent
SOURCES = ['abstract-arxiv', 'intro-related', 'methods', 'results', 'discussion']
TABLE_LABELS = {5: 'tab-hyp', 1: 'tab-sample', 2: 'tab-tests',
                3: 'tab-type', 4: 'tab-readings', 6: 'tab-extension-sample',
                7: 'tab-extension-tests', 8: 'tab-spread',
                9: 'tab-api-formal', 10: 'tab-api-dev', 11: 'tab-ablation'}
TITLE = 'Hearsay or Fact? How Framing and Elicitation Shape LLM Probability Updates'

def reference_map():
    mapping = {}
    for line in (PAPER / 'references-map.md').read_text(encoding='utf-8').splitlines():
        if not line.startswith('|'):
            continue
        cells = [c.strip() for c in line.strip('|').split('|')]
        key = re.search(r'`([a-z][a-z0-9]+)`', cells[2]) if len(cells) > 2 else None
        if key:
            for alias in cells[0].split(' ' + chr(0xff0f) + ' '):
                mapping[alias] = key[1]
        elif cells and cells[0].startswith('[') and len(cells) > 1:
            mapping[cells[0].strip('[]')] = cells[1]
    mapping['Srikanth & Rudinger 2025'] = 'srikanth2025nli'
    mapping['Imran et al. 2025'] = 'imran2025bayes'
    return mapping

MAP = reference_map()
BIB_KEYS = set(re.findall(r'@\w+\s*\{\s*([^,]+),', (PAPER / 'references.bib').read_text(encoding='utf-8')))
USED = set()
AUDIT = []

def citation(markers, narrative=False):
    keys = []
    for marker in markers:
        marker = marker.strip()
        if marker not in MAP:
            raise ValueError(f'Unmapped citation: {marker}')
        key = MAP[marker]
        if key not in BIB_KEYS:
            raise ValueError(f'Missing BibTeX key: {key}')
        USED.add(key)
        AUDIT.append({'marker': marker, 'key': key})
        keys.append(key)
    return ' '.join('#cite(<' + k + '>, form: "prose")' if narrative else '@' + k for k in keys)

def escape(text):
    return re.sub(r'([\\#@$\[\]<>_*`])', r'\\\1', text)

def inline(text):
    saved = []
    def hold(value):
        saved.append(value)
        return '\x00' + str(len(saved)-1) + '\x00'
    text = re.sub(r'`([^`]+)`', lambda m: hold('#raw(' + json.dumps(m[1], ensure_ascii=False) + ')'), text)
    # The map explicitly supplies the author-year alias; use the adjacent author.
    text = re.sub(r'Pornpitakpan \[2004\]', lambda m: hold(citation(['Pornpitakpan 2004'], True)), text)
    def bracket(m):
        value = m[1]
        if re.search(r'\b(?:19|20)\d{2}[a-z]?\b|\b\d{4}\.\d{4,5}\b', value):
            return hold(citation(value.split(';')))
        return m[0]
    text = re.sub(r'\[([^\]\n]+)\]', bracket, text)
    def parens(m):
        value = m[1]
        pieces = [x.strip() for x in value.split(';')]
        matches = [x for x in pieces if re.search(r',\s*(?:19|20)\d{2}[a-z]?$', x)]
        if not matches:
            return m[0]
        if len(matches) == len(pieces):
            return hold(citation(matches))
        return '(' + '; '.join(hold(citation([x], True)) if x in matches else x for x in pieces) + ')'
    text = re.sub(r'\(([^()\n]+)\)', parens, text)
    text = re.sub(r'\bFigure ([123])\b', lambda m: hold('@fig' + m[1]), text)
    text = re.sub(r'\bTable (1[01]|[1-9])\b', lambda m: hold('@' + TABLE_LABELS[int(m[1])]), text)
    text = re.sub(r'\*\*(.+?)\*\*', lambda m: hold('#strong[' + inline(m[1]) + ']'), text)
    text = re.sub(r'(?<!\*)\*([^*]+)\*(?!\*)', lambda m: hold('#emph[' + inline(m[1]) + ']'), text)
    text = escape(text)
    return re.sub(r'\x00(\d+)\x00', lambda m: saved[int(m[1])], text)

def source(name):
    text = (PAPER / 'en' / (name + '-en.md')).read_text(encoding='utf-8')
    text = re.sub(r'\A\s*<!--.*?-->\s*', '', text, flags=re.S)
    if name == 'intro-related':
        text = text[text.index('## 1 Introduction'):]
    return text

def table(block):
    lines = block.splitlines()
    caption = re.fullmatch(r'\*\*Table (\d+)\. (.*)\*\*', lines[0])
    number, title = int(caption[1]), caption[2]
    rows = [line.strip().strip('|').split('|') for line in lines if line.startswith('|')]
    rows = [[cell.strip() for cell in row] for row in rows]
    rows.pop(1)
    n = len(rows[0])
    widths = {1: '(1.7fr, .5fr, .7fr, .6fr, .6fr, 1.3fr, .9fr)',
              2: '(.85fr, 1.55fr, .45fr, .65fr, 1.05fr, .65fr, .65fr, 2.15fr)',
              3: '(1.4fr, 1fr, 1fr, 1fr, 1fr)', 4: '(1.2fr, .85fr, 1.15fr, 1.15fr, 1.15fr, 1.15fr)',
              6: '(1.7fr, .5fr, .7fr, .6fr, .6fr, 1.3fr, .9fr)',
              7: '(1.15fr, 1.55fr, .65fr, 1.05fr, .65fr, .65fr, 2.15fr)',
              8: '(1.9fr, .6fr, 1.1fr, 1.4fr, 1.2fr)',
              9: '(1.7fr, .6fr, 1fr, 1fr, 1fr, 1fr, 1.4fr)',
              10: '(2.4fr, .6fr, .55fr, .55fr, .55fr, 1fr, 1fr)',
              11: '(1.1fr, .8fr, 1.3fr, 1fr, 1fr, .8fr, 1fr)'}
    if number in (9, 10, 11):
        widths[number] = '(' + ', '.join(['auto'] * n) + ')'
    def cell(c):
        content = inline(c)
        return '[#box(height: 10pt, baseline: 2pt)[' + content + ']]' if number in (9, 10, 11) else '[' + content + ']'
    header = 'table.header(' + ', '.join(cell(c) for c in rows[0]) + '),'
    cells = '\n'.join(', '.join(cell(c) for c in row) + ',' for row in rows[1:])
    # Keep captions, data and notes together; the largest table fits on one page.
    result = '#block(breakable: false)[\n#figure(\n  kind: table,\n  caption: [' + inline(title) + '],\n  supplement: [Table],\n  { set text(size: ' + ('7.5' if number in (8, 9, 10, 11) else '7.5' if number in (2, 7) else '8') + 'pt); table(\ncolumns: ' + widths.get(number, '(' + ', '.join(['1fr'] * n) + ')') + ',\ninset: ' + '4pt' + ',\nstroke: .35pt + luma(65%),\n' + header + '\n' + cells + '\n) },\n) <' + TABLE_LABELS[number] + '>\n'
    notes = '\n'.join(line for line in lines[1:] if line and not line.startswith('|'))
    if notes:
        result += '#text(size: 8pt)[' + inline(notes) + ']\n'
    result += ']\n'
    if number in (9, 10, 11):
        # Wide tables retain readable type and each numeric field on one line.
        result = '#page(width: 297mm, height: 210mm, margin: (x: 12mm, y: 15mm))[\n' + result + ']\n'
    return result

FIGURES = {
  1: ('fig1_movement', 'Directional movement s by configuration, presentation and elicitation (descriptive 95% cluster-bootstrap intervals). Original three configurations and four extension configurations are separated; each extension uses only 120 Block-A pairs.'),
  2: ('fig2_endpoints', 'Endpoint rate (reported value ≤ 5 or ≥ 95) by condition and elicitation. The original three configurations are in the upper row; the four extensions are in the lower row and each uses only 120 Block-A pairs.'),
  3: ('fig3_readings', 'Multi-estimate readings minus direct elicitation, stated condition (exploratory, not pre-specified; complete stated pairs n = 240 for Qwen3 (thinking off), n = 238 for OLMo-2, n = 120 Block-A pairs for codex; descriptive 95% cluster-bootstrap intervals, B = 2,000, seed 20261490; maximum-weight ties in top-weighted candidate are averaged, and weighted median uses the lower weighted median).'),
}

def figure(number):
    stem, caption = FIGURES[number]
    # Typst 0.14.2 does not accept PDF as an image format. Supplied PNGs are used.
    return '#figure(image("../figures/en/' + stem + '.png", width: 100%), caption: [' + inline(caption) + ']) <fig' + str(number) + '>\n'

def blocks(text):
    """Group captions, Markdown table and its following parenthetical note."""
    chunks = re.split(r'\n\s*\n', text.strip())
    result = []
    i = 0
    while i < len(chunks):
        chunk = chunks[i]
        if re.match(r'\*\*Table \d+\.', chunk):
            if '\n|' in chunk:
                pass
            elif i+1 >= len(chunks) or not chunks[i+1].startswith('|'):
                raise ValueError('Table caption without data')
            else:
                chunk += '\n' + chunks[i+1]; i += 1
            if i+1 < len(chunks) and chunks[i+1].startswith('('):
                chunk += '\n' + chunks[i+1]; i += 1
        result.append(chunk)
        i += 1
    return result

def convert(text, results=False):
    chunks = blocks(text)
    if results:
        index = next(i for i, b in enumerate(chunks) if b.startswith('**Table 2.'))
        tab2 = chunks.pop(index)
        index = next(i for i, b in enumerate(chunks) if b.startswith('### 4.2 '))
        chunks.insert(index+1, tab2)
    out = []
    section = None
    first_paragraph = False
    for block in chunks:
        heading = re.fullmatch(r'(#{2,})\s+(.*)', block)
        if heading:
            title = re.sub(r'^\d+(?:\.\d+)*\s+', '', heading[2])
            out.append('=' * (len(heading[1])-1) + ' ' + inline(title))
            section = heading[2].split()[0]
            first_paragraph = True
        elif block.startswith('>'):
            # Keep quoted prompt lines (including empty `>` lines) literal.
            lines = [re.sub(r'^> ?', '', line).replace('\u3000', ' ') for line in block.splitlines()]
            # Align the alternative presentation labels in the monospace block.
            labelled = [re.fullmatch(r'(.*?)\s+\((stated|reported)\)', line) for line in lines]
            width = max((len(m[1]) for m in labelled if m), default=0)
            lines = [m[1].ljust(width + 2) + '(' + m[2] + ')' if m else line
                     for line, m in zip(lines, labelled)]
            out.append('#block(breakable: false)[\n#set text(size: 9pt)\n#raw(' +
                       json.dumps('\n'.join(lines), ensure_ascii=False) + ', block: true)\n]')
        elif block.startswith('**Table '):
            out.append(table(block))
            if block.startswith('**Table 4.'):
                out.append(figure(3))
        elif block.startswith('|'):
            # The model configuration table has no caption or source number.
            rows = [[cell.strip() for cell in line.strip('|').split('|')]
                    for line in block.splitlines()]
            rows.pop(1)
            header = 'table.header(' + ', '.join('[' + inline(c) + ']' for c in rows[0]) + '),'
            cells = '\n'.join(', '.join('[' + inline(c) + ']' for c in row) + ',' for row in rows[1:])
            out.append('#block(breakable: false)[\n#set text(size: 8pt)\n'
                       '#table(columns: (1fr, 1.7fr, 1.4fr, 2fr), inset: 4pt, '
                       'stroke: .35pt + luma(65%),\n' + header + '\n' + cells + '\n)\n]')
        else:
            lines = block.splitlines()
            if all(re.match(r'(?:- |\d+\. )', line) for line in lines):
                out.append('\n'.join(('- ' if line.startswith('- ') else '+ ') + inline(re.sub(r'^(?:- |\d+\. )', '', line)) for line in lines))
            else:
                out.append(inline(' '.join(lines)))
            if results and section == '4.2' and first_paragraph:
                out.append(figure(1))
            if results and section == '4.4' and block.startswith('**Endpoints (H4a).**'):
                out.append(figure(2))
            first_paragraph = False
    return '\n\n'.join(out) + '\n'

def generate_table4_readouts():
    """Archive all 28 contrasts and their frozen bootstrap provenance."""
    import statistics, sys
    repo = PAPER.parents[2]
    sys.path.insert(0, str(repo / "connecting-dots/dnli"))
    sys.path.insert(0, str(repo / "connecting-dots/dnli/paper"))
    import analysis, make_figures

    fig_data = json.loads((repo / "connecting-dots/dnli/paper/figures/en/figure_data.json").read_text(encoding="utf-8"))
    fig3_map = {(r["config"], r["reading"]): r for r in fig_data["fig3"]}

    configs_spec = [
        ("qwen3-off", "Qwen3 (thinking off)", 240),
        ("olmo2", "OLMo-2", 238),
        ("codex", "codex", 120),
        ("agy:gpt-oss-120b-medium", "gpt-oss-120b", 120),
        ("agy:claude-sonnet-5-5-medium", "claude-sonnet-5.5", 120),
        ("agy:gemini-3.8-flash-low", "gemini-3.8-flash (low)", 120),
        ("agy:gemini-3.8-flash-high", "gemini-3.8-flash (high)", 120),
    ]
    expected_cfgs = [c[0] for c in configs_spec]
    FIG3_RULE = "0-based sorted order statistics xs[49] and xs[1949] via make_figures.compute_data() shared np.random.default_rng(20261490)"
    FIG3_SRC = "paper/figures/en/figure_data.json:fig3"
    BOOT_RULE = "0-based sorted order statistics xs[125] and xs[4874] via random.Random(20261090) in dnli/analysis.py:boot_values and order_interval"
    BOOT_SRC = "dnli/analysis.py:boot_values(B=5000,seed=20261090)"

    # Independently compute authoritative ground truth from frozen source files
    auth_rows = {}
    for cfg, label, exp_n in configs_spec:
        records = make_figures.load_records(cfg)
        keys = sorted({u[0] for u in records})
        complete_keys = [
            k for k in keys
            if all((k, "stated", u, a) in records for u in ("S", "W") for a in ("direct", "multi"))
        ]
        assert len(complete_keys) == exp_n
        pairs = {k: {"cluster": records[(k, "stated", "S", "direct")]["cluster"]} for k in complete_keys}
        stated_sd = statistics.fmean(
            float(records[u]["result"]["weighted_sd"])
            for u in sorted(records)
            if u[1] == "stated" and u[3] == "multi"
        )
        rd = {}
        for rname in ("mean", "unweighted", "top", "median"):
            if cfg in ("qwen3-off", "olmo2", "codex") and rname in ("mean", "top", "median"):
                f3 = fig3_map[(cfg, rname)]
                rd[rname] = {
                    "point": float(f3["point"]), "low": float(f3["low"]), "high": float(f3["high"]),
                    "B": 2000, "seed": 20261490, "index_rule": FIG3_RULE, "source": FIG3_SRC,
                }
            else:
                diffs = {}
                for k in complete_keys:
                    rs_d = records[(k, "stated", "S", "direct")]
                    rw_d = records[(k, "stated", "W", "direct")]
                    rs_m = records[(k, "stated", "S", "multi")]
                    rw_m = records[(k, "stated", "W", "multi")]
                    s_d = (float(rs_d["result"]["value"]) - float(rw_d["result"]["value"])) / 2.0
                    if rname == "unweighted":
                        v_s = statistics.fmean(float(x) for x in rs_m["result"]["estimates"])
                        v_w = statistics.fmean(float(x) for x in rw_m["result"]["estimates"])
                    else:
                        v_s = make_figures.read_value(rs_m, rname)
                        v_w = make_figures.read_value(rw_m, rname)
                    diffs[k] = (v_s - v_w) / 2.0 - s_d
                pt = statistics.fmean(diffs.values())
                reps = analysis.boot_values(diffs, pairs, B=5000, seed=20261090)
                lo, hi = analysis.order_interval(reps, 0.05)
                rd[rname] = {
                    "point": float(pt), "low": float(lo), "high": float(hi),
                    "B": 5000, "seed": 20261090, "index_rule": BOOT_RULE, "source": BOOT_SRC,
                }
        auth_rows[cfg] = {
            "config": cfg, "label": label, "n_stated_pairs": exp_n, "n_clusters": exp_n,
            "stated_sd": stated_sd, "readings": rd,
        }
    data = {"description": "Stated multi-estimate minus direct movement; frozen source readouts and bootstrap provenance", "configs_expected": expected_cfgs, "rows": list(auth_rows.values())}
    (HERE / "table4_readouts.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

def generate():
    generate_table4_readouts()
    USED.clear(); AUDIT.clear()
    abstract = re.sub(r'^## Abstract\s*', '', source(SOURCES[0]))
    (HERE / 'abstract.typ').write_text(convert(abstract), encoding='utf-8')
    body = '\n'.join(convert(source(name), results=name == 'results') for name in SOURCES[1:])
    (HERE / 'body.typ').write_text(body, encoding='utf-8')
    audit = {'citations': AUDIT, 'used_keys': sorted(USED), 'unused_keys': sorted(BIB_KEYS-USED)}
    (HERE / 'citation-audit.json').write_text(json.dumps(audit, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')
    return audit

def compile_pdf():
    run = subprocess.run([shutil.which('typst') or 'typst', 'compile', '--root', str(PAPER), 'main.typ', 'dnli-arxiv.pdf'], cwd=HERE, capture_output=True, text=True, encoding='utf-8')
    (HERE / 'compile.log').write_text(run.stdout + run.stderr, encoding='utf-8')
    if run.returncode or run.stderr:
        raise RuntimeError(run.stdout + run.stderr)
    return run

if __name__ == '__main__':
    audit = generate()
    compile_pdf()
    print('Build successful, without warnings.')
    print('Unused BibTeX keys:', ', '.join(audit['unused_keys']) or '(none)')
