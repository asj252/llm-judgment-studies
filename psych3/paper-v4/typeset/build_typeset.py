#!/usr/bin/env python3
"""Deterministic frozen Markdown -> single-column AutoTeX delivery. No network."""
import gzip
import hashlib
import io
import json
import re
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parent
SOURCE = ROOT.parent / 'source-text'
FIGURES = ['fig1_confirmatory.png','fig2_status_quo_default_advice.png','fig3_format_differences.png','fig4_stage2c_crossover.pdf','fig_5tasks_mcv_comparison.pdf','fig_act3_3mechanisms.pdf']
FROZEN = {'manuscript.md':'134df54ae40904cdb8f12f9dd3f3239b4ff054b12b2b0435a45186e6e420c5ec','manuscript_zh.md':'3c0f67fd61c9375de14d772d3a4e58caa202d642145f93a8226a1a5c56466f65','appendices.md':'4530c15713ceceab64bdedc2fd0c7095644470a94a8eee4899d67923a1cb18e3','references.bib':'8b9e544a3108a16228e7085fc24c97c70121e4829ef7d0c282d1e4dd029488fe'}
CAPTIONS = {5: 'Figure 5. Task-specific descriptive comparisons across Stage 1 Formal, Stage 1 Dev, Stage 2B, and Stage 2C slices (all panels: lower is better). Subpanels retain distinct vertical scales, units (`|mean AI|`, `LnMAE`, `pp`, `%`), and denominators separated by dashed boundaries; missing bars indicate combinations not run in that slice rather than zero or imputed values. Protocol labels map to concrete stage-specific arms in `story_figures_ledger.json`: (1) in the Stage 1 Formal Flash hindsight slice (`D-lo / T / W`, paired $n=89$, $|\\text{mean } b|$ in `pp`), the bar plotted under legend slot `T` (`Direct-CoT`) represents the frozen Flash-high direct reasoning-budget configuration ($3.99\\text{ pp}$, contrasted against Flash-low direct `D-lo` at $1.96\\text{ pp}$ and Flash-high multi `W` at $0.54\\text{ pp}$), which is a reasoning-budget configuration contrast rather than an explicit chain-of-thought prompt intervention; (2) the bottom two panels in row B (`Stage 2B A`, $n=4$/arm) are narrative Bayesian prior-anchor proxies rather than ProbCOPA hindsight reconstruction trials, and the Stage 2C panels in row D (`incomplete %` and `order violation %`, $n=350$/org) are multi-candidate structural format diagnostics rather than conjunction probability trials; (3) every `MCU` (`V2`) bar shown here (Stage 1 Dev `A_ln` $n=10$, Stage 2B `multi_free`/`multi`, and Stage 2C `multi_repeat`) is a same-generation equal-weight readout computed from the corresponding weighted multi-candidate output, not an independent unweighted prompt arm (prompt-level weight elicitation is isolated separately in post-cohort Suite P2-A, Table 5); and (4) `Baseline MCW` denotes Stage 1 `ASK_MULTI`, Stage 2B distinct-candidate `multi_free`/`multi`, or Stage 2C repeat-allowed `multi_repeat`, whereas upgraded green bars denote slice-specific variants—Stage 1 D joint presentation (`Joint + MCW`), Stage 2B point-first ascending without repeat (`1p5_asc`), Stage 2B prime-scale distinct multi (`M=13 multi`), or Stage 2C combined point-first ascending with repeats (`1p5_asc_repeat`)—not a single uniform protocol across stages.', 6: 'Figure 6. Exploratory protocol-manipulation comparisons across ordering (left), repeat allowance and weighting readouts (middle), and non-decimal response scales (right; all panels: lower is better). The embedded panel banners “Mechanism 1–3” are descriptive, hypothesis-generating groupings of observable prompt manipulations and do not identify internal cognitive, attentional, or neural causal mechanisms, which remain unmeasured hypotheses (Section 6). Each subpanel retains its own stage, model, sample size ($n=4$ or $6$ in Stage 2B; $n=32$ or $70$ in Stage 2C; $n=48$ in Stage 1 Dev C), and native metric (`MAE pp`, `incomplete %`, `echo %`, or anchor `shift pp`), without forming a common cross-task score. Across all panels, `MCU` (`V2`) bars are same-generation equal-weight readouts from weighted multi-candidate responses (`multi_free`, `multi`, `multi_repeat`, or Stage 1 Dev `ASK_MULTI`) rather than separate unweighted prompts; `MCW-Asc` in Stage 2B Block A denotes `1p5_asc` (distinct candidates), whereas only Stage 2C uses the combined `1p5_asc_repeat` protocol.'}  # Filled with the task's exact approved Figure 5/6 captions below.
UNICODE = {'—':'---','–':'--','−':r'\ensuremath{-}','×':r'\ensuremath{\times}','→':r'\ensuremath{\rightarrow}','“':'``','”':"''",'’':"'",'Δ':r'\ensuremath{\Delta}','δ':r'\ensuremath{\delta}','§':r'\S{}','≤':r'\ensuremath{\leq}','≥':r'\ensuremath{\geq}','±':r'\ensuremath{\pm}','½':r'\ensuremath{\frac{1}{2}}','Σ':r'\ensuremath{\Sigma}','ₖ':r'\ensuremath{_k}','α':r'\ensuremath{\alpha}'}
ESC = {'\\':r'\textbackslash{}','{':r'\{','}':r'\}','$':r'\$','&':r'\&','#':r'\#','%':r'\%','_':r'\_','~':r'\textasciitilde{}','^':r'\textasciicircum{}'}
def escape(s):
    out=''.join(UNICODE.get(c,ESC.get(c,c)) + (r'\allowbreak{}' if c in '/_,:-' else '') for c in s)
    out=re.sub(r'(?<![a-zA-Z0-9])([0-9a-f]{64})(?![a-zA-Z0-9])',r'\\seqsplit{\1}',out)
    return out

def inline(s):
    # Protect mathematics, citations and links before escaping ordinary text.
    pattern=r'\$[^$\n]+\$|\[@[^\]]+\]|\[[^\]]+\]\([^)]+\)|`[^`]+`|\*\*.+?\*\*|\*[^*]+\*'
    out=[];pos=0
    for m in re.finditer(pattern,s):
        out.append(escape(s[pos:m.start()]));t=m.group()
        if t.startswith('$'):
            for c,v in UNICODE.items():t=t.replace(c,v)
            out.append(t)
        elif t.startswith('[@'):out.append(r'\citep{'+','.join(re.findall(r'@([\w-]+)',t))+'}')
        elif t.startswith('['):
            label,url=re.match(r'\[([^]]+)\]\(([^)]+)\)',t).groups()
            if re.match('https?://',url):out.append(r'\href{'+url+'}{'+inline(label)+'}')
            else:out.append(inline(label))
        elif t.startswith('`'):out.append(r'\texttt{'+escape(t[1:-1])+'}')
        elif t.startswith('**'):out.append(r'\textbf{'+inline(t[2:-2])+'}')
        else:out.append(r'\emph{'+inline(t[1:-1])+'}')
        pos=m.end()
    out.append(escape(s[pos:]));return ''.join(out)

def blocks(text):
    lines=text.splitlines();i=0
    while i<len(lines):
        line=lines[i]
        if not line.strip():i+=1;continue
        start=i+1
        if line.startswith('```'):
            j=i+1
            while not lines[j].startswith('```'):j+=1
            yield start,'code','\n'.join(lines[i+1:j]);i=j+1
        elif line.startswith('|'):
            j=i+1
            while j<len(lines) and lines[j].startswith('|'):j+=1
            yield start,'table','\n'.join(lines[i:j]);i=j
        else:
            j=i+1
            while j<len(lines) and lines[j].strip() and not lines[j].startswith(('```','|')):j+=1
            yield start,'text','\n'.join(lines[i:j]);i=j

def table_tex(text):
    rows=[[c.strip() for c in l.strip('|').split('|')] for l in text.splitlines()]
    rows.pop(1);n=len(rows[0])
    weights=[]
    for col in zip(*rows):
        lengths=sorted(len(re.sub(r'[`*$]','',c)) for c in col)
        weights.append(max(8,len(rows[0][len(weights)])*1.6,min(75,lengths[int(.85*(len(lengths)-1))])))
    if n==2 and max(weights)>30:weights=[max(weights[0],55),max(weights[1],25)]
    total=sum(weights);available=169-(n*2*1.3)
    spec=''.join(r'>{\raggedright\arraybackslash}p{'+f'{available*w/total:.3f}mm'+'}' for w in weights)
    def row(cells):return ' & '.join(inline(c) for c in cells)+r' \\'
    head=row(rows[0])
    return '\n'.join([r'\begingroup\scriptsize\setlength{\tabcolsep}{1.3mm}\setlength{\LTpre}{4pt}\setlength{\LTpost}{6pt}',r'\begin{longtable}{'+spec+'}',r'\toprule',head,r'\midrule\endfirsthead',r'\toprule',head,r'\midrule\endhead',r'\bottomrule\endfoot']+[row(r) for r in rows[1:]]+[r'\end{longtable}',r'\endgroup'])

PUBLIC = r'Public Stage 1 preregistration and v2 study materials: \url{https://github.com/asj252/llm-judgment-studies}. \hyperref[sec:appendices]{Appendices A--I} (included in this document) preserve original evidence and provide Stage 2 and P1/P2 reproduction details. The \hyperref[sec:references]{References} section retains all 70 bibliography entries.'
CROSS = {842:r'The protocol and parsing evidence appears in \hyperref[sec:5.2]{Section 5.2}, Figure 4, Table 3 and Figures 5--6; source excerpts appear in \hyperref[sec:I.11]{Section I.11}.',950:r'The protocol and pooled effects appear in \hyperref[sec:5.3.1]{Section 5.3.1} and Table 4; see also Sections I.6, I.8 and I.10.',996:r'The protocol and pooled results appear in \hyperref[sec:5.3.2]{Section 5.3.2} and Table 5; see also Sections I.5, I.7 and I.9.'}

def document():
    en=(SOURCE/'manuscript.md').read_text(encoding='utf-8');ap=(SOURCE/'appendices.md').read_text(encoding='utf-8')
    out=[PREAMBLE];pending=None
    moved=next(b for b in blocks(en) if b[0]==464)
    def emit(origin,start,kind,text):
        nonlocal pending
        if kind=='code':body=r'\begin{Verbatim}[fontsize=\scriptsize,breaklines=true,breakanywhere=true]'+'\n'+text+'\n'+r'\end{Verbatim}'
        elif kind=='table':body=table_tex(text)
        elif text.startswith('!['):
            number={181:1,213:2,217:3,263:4,338:5,340:6}[start]
            if number<5:pending=number;return
            body=r'\clearpage\begin{center}\includegraphics[width=\linewidth,height=.68\textheight,keepaspectratio]{figures/'+FIGURES[number-1]+r'}\end{center}'+'\n'+inline(CAPTIONS[number])+r'\par\clearpage'
        elif pending:
            body=r'\clearpage\begin{center}\includegraphics[width=\linewidth,height=.70\textheight,keepaspectratio]{figures/'+FIGURES[pending-1]+r'}\end{center}'+'\n'+inline(text)+r'\par\clearpage';pending=None
        elif origin=='M' and start==37:body=PUBLIC
        elif text.startswith('#'):
            h=re.match(r'^(#+) (.*)',text);level=len(h[1]);title=h[2]
            if origin=='M' and level==1:body=r'\title{'+inline(title)+r'}\author{An-Sheng Jhang\\Dongguan University of Technology}\date{}\maketitle'
            else:
                cmd={1:'section',2:'section',3:'subsection',4:'subsubsection'}[level]
                if title.startswith(('Appendix ','English paper')):prefix=r'\clearpage'
                else:prefix=''
                title=re.sub(r'^\d+(?:\.\d+)*\s+','',title) if origin=='M' else title
                star='*' if origin=='A' or title in ['Abstract','AI Tool Disclosure and Bibliographic Note'] or level==4 and start==82 else ''
                body=prefix+('\\setcounter{subsection}{2}' if origin=='M' and start==49 else '')+'\\'+cmd+star+'{'+inline(title)+'}'
                if origin=='M' and start in [237,344,385]:body+=r'\label{sec:'+{237:'5.2',344:'5.3.1',385:'5.3.2'}[start]+'}'
                if title.startswith('Appendix A.'):body+=r'\label{sec:appendices}'
                if title.startswith('I.11 '):body+=r'\label{sec:I.11}'
                if origin=='A' and start in CROSS:body+='\n'+CROSS[start]
        else:body=inline(text)+r'\par'
        if origin=='M' and start==22:body=inline('Table 1. Study-wide execution and evaluation accounting across all five stages (31,672 planned/admitted evaluation units; 32,184 planned/admitted calls excluding retries).')+r'\par'+'\n'+body
        if origin=='M' and start==443:body=inline('Table 6. Conditional protocol recommendations and evidence boundaries across task structures.')+r'\par'+'\n'+body
        out.extend([f'% BEGIN {origin}:{start} {kind}',body,f'% END {origin}:{start}'])
        if origin=='M' and start==383:
            out.append(inline('P1 Block B operational string-matching counts across response scales and cue formats (identical to Appendix I.10).')+r'\par')
            emit('M',*moved)
    for b in blocks(en):
        if b[0] not in [3,464]:emit('M',*b)
    out.append(r'\clearpage\phantomsection\label{sec:references}\nocite{*}\bibliographystyle{plainnat}\bibliography{references}')
    for b in blocks(ap):
        if not any(lo<=b[0]<=hi for lo,hi in [(844,947),(952,991),(998,1044)]):emit('A',*b)
    out.append(r'\end{document}')
    return '\n\n'.join(out)+'\n'

PREAMBLE = r'''\pdfoutput=1
\pdfinfoomitdate=1
\pdftrailerid{}
\pdfsuppressptexinfo=15
\documentclass[11pt,a4paper]{article}
\usepackage[a4paper,margin=20mm]{geometry}
\usepackage[T1]{fontenc}
\usepackage[utf8]{inputenc}
\usepackage{lmodern,microtype,amsmath,amssymb,booktabs,longtable,array,graphicx}
\usepackage[table]{xcolor}
\usepackage[round]{natbib}
\usepackage{fvextra,upquote,seqsplit,xurl}
\usepackage[hypertexnames=false,colorlinks=true,linkcolor=blue!60!black,citecolor=blue!60!black,urlcolor=blue!60!black]{hyperref}
\DeclareUnicodeCharacter{00D7}{\ensuremath{\times}}
\DeclareUnicodeCharacter{2013}{--}
\DeclareUnicodeCharacter{2212}{\ensuremath{-}}
\setlength{\emergencystretch}{3em}
\setlength{\parindent}{0pt}
\setlength{\parskip}{5pt}
\setcounter{secnumdepth}{3}
\sloppy
\begin{document}'''

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def info(p):return {'bytes':p.stat().st_size,'sha256':sha(p)}
def write(name,s): (ROOT/name).write_text(s,encoding='utf-8')
def dump(name,obj):write(name,json.dumps(obj,ensure_ascii=True,indent=2,sort_keys=True)+'\n')
def env(d):return {'PATH':'/usr/bin:/bin','HOME':str(d),'TMPDIR':str(d),'SOURCE_DATE_EPOCH':'0'}
def run(cmd,d):
    r=subprocess.run(cmd,cwd=d,env=env(d),stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    if r.returncode:raise RuntimeError(r.stdout.decode('utf-8',errors='replace')[-6000:])

def compile_pdf():
    with tempfile.TemporaryDirectory(prefix='psych3-bib-') as td:
        d=Path(td)
        shutil.copyfile(ROOT/'paper.tex',d/'paper.tex');shutil.copyfile(ROOT/'references.bib',d/'references.bib');shutil.copytree(ROOT/'figures',d/'figures')
        run(['pdflatex','-interaction=nonstopmode','-halt-on-error','paper.tex'],d);run(['bibtex','paper'],d)
        shutil.copyfile(d/'paper.bbl',ROOT/'paper.bbl')
    with tempfile.TemporaryDirectory(prefix='psych3-autotex-') as td:
        d=Path(td)
        for name in ['paper.tex','paper.bbl']:
            shutil.copyfile(ROOT/name,d/name)
        shutil.copytree(ROOT/'figures',d/'figures')
        for _ in range(2):run(['pdflatex','-recorder','-interaction=nonstopmode','-halt-on-error','paper.tex'],d)
        log=(d/'paper.log').read_text(encoding='utf-8')
        if re.search(r'Undefined control sequence|Citation .* undefined|Reference .* undefined|There were undefined references|Missing character:',log):raise AssertionError('TeX warnings: unresolved reference or missing glyph')
        excess=[float(x) for x in re.findall(r'Overfull \\hbox \(([\d.]+)pt too wide\)',log)]
        if any(x>10 for x in excess):raise AssertionError('Overfull hbox >10pt: '+str(sorted(excess,reverse=True)[:20]))
        shutil.copyfile(d/'paper.pdf',ROOT/'paper.pdf')

def main():
    for name,digest in FROZEN.items():assert sha(SOURCE/name)==digest,name
    for name in FIGURES[3:]:
        src=ROOT.parent/'figures'/('story/'+name if name.startswith(('fig_5','fig_act')) else name)
        shutil.copyfile(src,ROOT/'figures'/name);assert sha(src)==sha(ROOT/'figures'/name)
    shutil.copyfile(SOURCE/'references.bib',ROOT/'references.bib')
    write('paper.tex',document());compile_pdf()
    names=['paper.tex','paper.bbl']+['figures/'+x for x in FIGURES]
    with (ROOT/'arxiv-v4-source.tar.gz').open('wb') as raw:
        with gzip.GzipFile(filename='',fileobj=raw,mode='wb',mtime=0) as gz:
            with tarfile.open(fileobj=gz,mode='w') as tar:
                for name in names:
                    data=(ROOT/name).read_bytes();entry=tarfile.TarInfo(name);entry.size=len(data);entry.mode=0o644;entry.mtime=0;entry.uid=entry.gid=0;entry.uname=entry.gname='';tar.addfile(entry,io.BytesIO(data))
    en=(SOURCE/'manuscript.md').read_text(encoding='utf-8').splitlines()
    title=en[0][2:];abstract=en[7].replace('×','x').replace('–','-')
    pages=int(re.search(r'Pages:\s+(\d+)',subprocess.check_output(['pdfinfo',str(ROOT/'paper.pdf')],text=True))[1])
    comments=f'{pages} pages, 6 figures, Appendices A-I; expands the six-configuration Stage 1 cohort with exploratory Stage 2B/2C crossover and preregistered post-cohort formal suites P1 and P2'
    for name,text in [('title',title),('abstract',abstract),('comments',comments)]:text.encode('ascii');write(name+'.txt',text+'\n')
    files=['paper.tex','paper.bbl','paper.pdf','arxiv-v4-source.tar.gz','title.txt','abstract.txt','comments.txt']
    dump('metadata.json',{'submission_type':'new_or_replace_see_submission_summary','existing_arxiv_identifier':None,'title':title,'abstract':abstract,'comments':comments,'primary_category':'cs.CL','cross_list':['cs.AI'],'license':'arXiv.org perpetual, non-exclusive license 1.0','author':{'name':'An-Sheng Jhang','affiliation':'Dongguan University of Technology'},'pages':pages,'files':{f:info(ROOT/f) for f in files}})
    summary='''Conditional submission instructions - verify the actual author account status first.
(a) Already publicly announced on arXiv: Use Replace (Add a new version) on the existing arXiv identifier, upload arxiv-v4-source.tar.gz (TeX source submission), verify AutoTeX compilation preview, and update Abstract and Comments.
(b) Submitted / on hold (not yet announced): Use Unsubmit / Update in the arXiv dashboard before announcement freeze cutoff to replace the source package and metadata without creating a duplicate submission.
(c) Never submitted to arXiv: Use New submission, upload arxiv-v4-source.tar.gz, and enter the metadata fields below.
Local v2/v3/v4 package labels do not establish an existing public arXiv version or identifier. Local preparation only; not uploaded or submitted. No arXiv ID, ORCID, email, DOI, or submission receipt is invented.
Primary: cs.CL; Cross-list: cs.AI
License: arXiv.org perpetual, non-exclusive license 1.0
Author: An-Sheng Jhang (Dongguan University of Technology)
'''
    summary+='Title: '+title+'\nAbstract: '+abstract+'\nComments: '+comments+'\n'
    summary+='File inventory excludes this SUBMISSION_SUMMARY_ASCII.txt and the final manifest_typeset.json.\n'
    for name in sorted(['build_typeset.py','references.bib','metadata.json']+files+['figures/'+f for f in FIGURES]):summary+=f'{name} {info(ROOT/name)["bytes"]} bytes SHA-256 {sha(ROOT/name)}\n'
    write('SUBMISSION_SUMMARY_ASCII.txt',summary)
    paths=sorted(p for p in ROOT.rglob('*') if p.is_file() and p.name!='manifest_typeset.json')
    assert len(paths)==17,[str(p) for p in paths]
    dump('manifest_typeset.json',{str(p.relative_to(ROOT)):info(p) for p in paths})
    print(f'Built {pages} pages; 18 delivery files; SHA-256 {sha(ROOT/"paper.pdf")}')
if __name__=='__main__':main()
