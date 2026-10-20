"""Build integration tests and strict converter regression checks."""
import json
import re
import subprocess
import unittest
import importlib.util
from pathlib import Path

# Resolve this converter explicitly; the installed PyPA package is also named build.
spec = importlib.util.spec_from_file_location('dnli_typst_build', Path(__file__).with_name('build.py'))
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)

class BuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.audit = build.generate()
        cls.compilation = build.compile_pdf()
        cls.body = (build.HERE / 'body.typ').read_text(encoding='utf-8')
        cls.abstract = (build.HERE / 'abstract.typ').read_text(encoding='utf-8')
        cls.pdf = build.HERE / 'dnli-arxiv.pdf'
        result = subprocess.run(['pdftotext', '-enc', 'UTF-8', str(cls.pdf), '-'], capture_output=True, check=True)
        cls.pdftext = re.sub(r'\u00ad\s*', '', result.stdout.decode('utf-8'))

    def test_all_reference_markers_and_keys(self):
        self.assertTrue(self.audit['citations'])
        for item in self.audit['citations']:
            self.assertEqual(build.MAP[item['marker']], item['key'])
            self.assertIn(item['key'], build.BIB_KEYS)
        self.assertNotRegex(self.body, r'\\\[[^\]\n]*(?:et al\.|&)[^\]\n]*\d{4}')
        self.assertNotRegex(self.body, r'(?:et al\.,|Pavlick,|Marneffe,)\s*20\d{2}')
        print('Unused BibTeX keys:', ', '.join(self.audit['unused_keys']) or '(none)')

    def test_unknown_citations_fail(self):
        for marker in ['[Unknown et al. 2025]', '[9999.12345]', '(Unknown et al., 2025)', '[Rudinger et al. 2020; Unknown 2025]']:
            with self.subTest(marker=marker), self.assertRaises(ValueError):
                build.inline(marker)
        with self.assertRaises(ValueError):
            build.citation(['Unmapped 2025'])

    def test_literal_brackets_and_styles(self):
        for literal in ['[0.95, 1.05]', '[uncertainty expression]', '[Here is something else you learned: U]']:
            self.assertIn(build.escape(literal), build.inline(literal))
        self.assertEqual(build.inline('*s*'), '#emph[s]')
        self.assertIn('#strong[bold]', build.inline('**bold**'))
        self.assertEqual(build.inline('`a_b`'), '#raw("a_b")')
        self.assertIn('@rudinger2020thinking', build.inline('[Rudinger et al. 2020]'))
        self.assertIn('form: "prose"', build.inline('Pornpitakpan [2004]'))

    def test_figures_tables_and_placement(self):
        for i in range(1,4):
            self.assertEqual(self.body.count(f'<fig{i}>'), 1)
            self.assertIn(f'@fig{i}', self.body)
        labels = ['tab-hyp', 'tab-sample', 'tab-tests', 'tab-type', 'tab-readings',
                  'tab-extension-sample', 'tab-extension-tests', 'tab-spread']
        self.assertEqual(re.findall(r'<(tab-[a-z-]+)>', self.body), labels)
        for number, label in build.TABLE_LABELS.items():
            self.assertEqual(build.inline(f'Table {number}'), f'@{label}')
        self.assertNotIn('#counter(figure.where(kind: table)).update', self.body)
        self.assertNotRegex(self.body + self.abstract, r'\bTable\s+\d+\b')
        h42 = self.body.index('== Directional sensitivity (H1)')
        h43 = self.body.index('== Reporting wording (H2)')
        self.assertTrue(h42 < self.body.index('<tab-tests>') < self.body.index('<fig1>') < h43)
        self.assertTrue(self.body.index('#strong[Endpoints (H4a).]') < self.body.index('<fig2>') < self.body.index('#strong[Directional sensitivity (H4b).]'))
        self.assertTrue(self.body.index('<tab-readings>') < self.body.index('<fig3>') < self.body.index('== Robustness'))
        result = subprocess.run(['typst','query','--root',str(build.PAPER),'main.typ','figure','--field','kind'], cwd=build.HERE, capture_output=True, check=True, text=True)
        kinds = json.loads(result.stdout)
        self.assertEqual(kinds.count('image'),3)
        self.assertEqual(kinds.count('table'),8)
        self.assertEqual(re.findall(r'Table\s+(\d+):', self.pdftext), [str(i) for i in range(1, 9)])

    def test_extension_tables_and_captions(self):
        for number, columns in [(6, 7), (7, 7)]:
            block = next(b for b in build.blocks(build.source('results')) if b.startswith(f'**Table {number}.'))
            converted = build.table(block)
            widths = re.search(r'columns: \(([^)]+)\)', converted)[1].split(',')
            self.assertEqual(len(widths), columns)
            self.assertIn('breakable: false', converted)
            self.assertIn('set text(size: 7.5pt)' if number == 7 else 'set text(size: 8pt)', converted)
        for number in (1, 2):
            self.assertIn('120 Block-A pairs', build.FIGURES[number][1])
        # Every table's caption and final row must occur on the same PDF page.
        pages = self.pdftext.split('\f')
        for label, last in [('Table 6:', '19.1 s'),
                            ('Table 7:', 'No unit was missing, so no worst-case imputation was needed.')]:
            page = next(p for p in pages if label in p)
            self.assertIn(last, page)

    def test_condensed_abstract(self):
        expected = build.convert(re.sub(r'^## Abstract\s*', '', build.source('abstract-arxiv')))
        self.assertEqual(self.abstract, expected)
        self.assertNotEqual(self.abstract, build.convert(re.sub(r'^## Abstract\s*', '', build.source('abstract'))))
        self.assertIn('Because δ-NLI annotates only direction', ' '.join(self.pdftext.split()))

    def test_unnumbered_model_configuration_table(self):
        models = self.body.split('== Models tested', 1)[1].split('== Parsing', 1)[0]
        self.assertIn('#table(', models)
        self.assertNotIn('#figure(', models)
        self.assertNotIn('|---|', models)
        for model in ['Qwen3-8B', 'OLMo-2-1124-7B-Instruct', 'gpt-6.1-sol']:
            self.assertIn(model, models)
            self.assertIn(model, self.pdftext)

    def test_bibliography_dates(self):
        self.assertNotRegex(self.pdftext, r'\(\s*\d{4}[a-z]?\s*,\s*\)')
        compact = ' '.join(self.pdftext.split())
        self.assertIn('Wang, V., & Stengel-Eskin, E. (2026).', compact)
        self.assertNotRegex((build.PAPER / 'references.bib').read_text(encoding='utf-8'), r'(?im)^\s*month\s*=')

    def test_prompt_template_lines(self):
        # Avoid Poppler's column inference for the aligned presentation labels.
        result = subprocess.run(['pdftotext', '-raw', '-enc', 'UTF-8', str(self.pdf), '-'],
                                capture_output=True, check=True)
        text = result.stdout.decode('utf-8')
        prompt = text.split('Here is a situation: P', 1)[1].split('Prior items omit', 1)[0]
        expected = [
            '[Here is something else you learned: U] (stated)',
            '[Someone said that u] (reported)',
            'Using common sense, how likely is it that the following statement is true?',
            'Statement: H', '(elicitation-specific ending)',
            'Do not use any tools; answer directly.',
        ]
        self.assertEqual([' '.join(line.split()) for line in prompt.splitlines() if line.strip()], expected)
        self.assertNotRegex(text, r'(?m)^\s*>')
        raw = re.search(r'#raw\(("(?:[^"\\]|\\.)*"), block: true\)', self.body)
        self.assertIsNotNone(raw)
        lines = json.loads(raw[1]).splitlines()
        self.assertEqual([i for i, line in enumerate(lines) if not line], [3, 6, 8])
        self.assertEqual(lines[1].index('(stated)'), lines[2].index('(reported)'))
        self.assertNotIn('\u3000', raw[1])
        converted = build.convert('> First?\n>\n> [second]\n\nFollowing paragraph.')
        self.assertIn(json.dumps('First?\n\n[second]'), converted)
        self.assertIn('Following paragraph.', converted)

    def test_bibliography_full_authors_and_punctuation(self):
        text = ' '.join(self.pdftext.split())
        references = text.split('References', 1)[1]
        self.assertIn('Wang, A., Ma, W., & Liu, Y. (2025b).', references)
        self.assertIn('Wang, L., Jiang, Z., Liu, A., & Van Durme, B. (2025a).', references)
        self.assertNotRegex(references, r'Wang, [AL]\. et al\.')
        self.assertIn('de Marneffe, M.-C., Simons, M., & Tonhauser, J. (2019).', references)
        self.assertNotIn('Marneffe, M.-C. de', references)
        self.assertNotIn('?.', references)
        self.assertNotIn('``Wisdom', references)
        self.assertIn('Wang et al., 2025a', text.split('References', 1)[0])
        self.assertIn('Wang et al., 2025b', text.split('References', 1)[0])

    def test_compile_pdf_title_and_author(self):
        self.assertEqual(self.compilation.returncode,0)
        self.assertEqual(self.compilation.stderr,'')
        self.assertGreater(self.pdf.stat().st_size, 10000)
        compact = ' '.join(self.pdftext.split())
        self.assertEqual(build.TITLE, 'Hearsay or Fact? How Framing and Elicitation Shape LLM Probability Updates')
        self.assertIn(build.TITLE,compact)
        self.assertIn('An-Sheng Jhang',compact)
        self.assertIn('Dongguan University of Technology',compact)
        self.assertIn('ansheng.jhang@gmail.com',compact)
        self.assertNotIn('Tentative title',compact)
        self.assertNotIn('<!-- source',self.body+self.abstract)

    def test_source_numbers_and_unicode(self):
        sources = '\n'.join(build.source(n) for n in build.SOURCES)
        for number in ['18.6','20.0','25.3','2.0','4.8','5.4','\u22127.9','\u221213.7','\u22122.5']:
            self.assertIn(number,sources)
            self.assertIn(number,self.body)
            self.assertIn(number,self.pdftext)
        for symbol in ['\u2264','\u2265','\u2212','\u00d7','\u03b4']:
            if symbol in sources:
                self.assertIn(symbol,self.body+self.abstract)
                self.assertIn(symbol,self.pdftext)
        for heading in re.findall(r'^#{2,}\s+(\d+(?:\.\d+)*)\s+(.+)$',sources,re.M):
            self.assertIn(heading[0]+' '+heading[1], ' '.join(self.pdftext.split()))

if __name__ == '__main__':
    unittest.main()
