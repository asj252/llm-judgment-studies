"""Strict Markdown-to-Typst conversion for the English DNLI manuscript."""
from pathlib import Path
import json
import re
import subprocess

HERE = Path(__file__).resolve().parent
PAPER = HERE.parent
SOURCES = ['abstract-arxiv', 'intro-related', 'methods', 'results', 'discussion']
TABLE_LABELS = {5: 'tab-hyp', 1: 'tab-sample', 2: 'tab-tests',
                3: 'tab-type', 4: 'tab-readings'}
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
    text = re.sub(r'\bTable ([1-5])\b', lambda m: hold('@' + TABLE_LABELS[int(m[1])]), text)
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
              3: '(1.4fr, 1fr, 1fr, 1fr, 1fr)', 4: '(1.2fr, .85fr, 1.2fr, 1.2fr, 1.2fr)'}
    header = 'table.header(' + ', '.join('[' + inline(c) + ']' for c in rows[0]) + '),'
    cells = '\n'.join(', '.join('[' + inline(c) + ']' for c in row) + ',' for row in rows[1:])
    # Keep captions, data and notes together; the largest table fits on one page.
    result = '#block(breakable: false)[\n#figure(\n  kind: table,\n  caption: [' + inline(title) + '],\n  supplement: [Table],\n  { set text(size: ' + ('7.5' if number == 2 else '8') + 'pt); table(\ncolumns: ' + widths.get(number, '(' + ', '.join(['1fr'] * n) + ')') + ',\ninset: 4pt,\nstroke: .35pt + luma(65%),\n' + header + '\n' + cells + '\n) },\n) <' + TABLE_LABELS[number] + '>\n'
    notes = '\n'.join(line for line in lines[1:] if line and not line.startswith('|'))
    if notes:
        result += '#text(size: 8pt)[' + inline(notes) + ']\n'
    return result + ']\n'

FIGURES = {
  1: ('fig1_movement', 'Directional movement s by configuration, presentation and elicitation (descriptive 95% cluster-bootstrap intervals).'),
  2: ('fig2_endpoints', 'Endpoint rate (reported value ≤ 5 or ≥ 95) by condition and elicitation.'),
  3: ('fig3_readings', 'Multi-estimate readings minus direct elicitation, stated condition (exploratory, not pre-specified).'),
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
            if i+1 >= len(chunks) or not chunks[i+1].startswith('|'):
                raise ValueError('Table caption without data')
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

def generate():
    USED.clear(); AUDIT.clear()
    abstract = re.sub(r'^## Abstract\s*', '', source(SOURCES[0]))
    (HERE / 'abstract.typ').write_text(convert(abstract), encoding='utf-8')
    body = '\n'.join(convert(source(name), results=name == 'results') for name in SOURCES[1:])
    (HERE / 'body.typ').write_text(body, encoding='utf-8')
    audit = {'citations': AUDIT, 'used_keys': sorted(USED), 'unused_keys': sorted(BIB_KEYS-USED)}
    (HERE / 'citation-audit.json').write_text(json.dumps(audit, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')
    return audit

def compile_pdf():
    run = subprocess.run(['typst', 'compile', '--root', str(PAPER), 'main.typ', 'dnli-arxiv.pdf'], cwd=HERE, capture_output=True, text=True, encoding='utf-8')
    (HERE / 'compile.log').write_text(run.stdout + run.stderr, encoding='utf-8')
    if run.returncode or run.stderr:
        raise RuntimeError(run.stdout + run.stderr)
    return run

if __name__ == '__main__':
    audit = generate()
    compile_pdf()
    print('Build successful, without warnings.')
    print('Unused BibTeX keys:', ', '.join(audit['unused_keys']) or '(none)')
