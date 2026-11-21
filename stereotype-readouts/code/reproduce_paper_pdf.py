#!/usr/bin/env python3
"""Compile the submission snapshot using TeX Live in an external temporary directory."""
import argparse
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--paper-dir',type=Path,required=True)
    ap.add_argument('--out-dir',type=Path,required=True)
    a=ap.parse_args()
    with tempfile.TemporaryDirectory(prefix='paper-release-') as td:
        d=Path(td)
        for n in ['paper.tex','tables_generated.tex','references.bib']: shutil.copyfile(a.paper_dir/n,d/n)
        shutil.copytree(a.paper_dir/'figures',d/'figures')
        env={**os.environ,'SOURCE_DATE_EPOCH':'1795219200','FORCE_SOURCE_DATE':'1','TZ':'UTC'}
        for cmd in [['pdflatex','-interaction=nonstopmode','-halt-on-error','paper.tex'],['bibtex','paper']]+[['pdflatex','-interaction=nonstopmode','-halt-on-error','paper.tex']]*2:
            p=subprocess.run(cmd,cwd=d,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
            if p.returncode: raise RuntimeError(p.stdout.decode('utf-8',errors='replace')[-6000:])
        log=(d/'paper.log').read_text(encoding='utf-8')
        if re.search(r'(^!|Undefined|undefined|Overfull \\hbox)',log,re.M): raise ValueError('Unclean compilation log')
        a.out_dir.mkdir(parents=True,exist_ok=True)
        for n in ['paper.pdf','paper.bbl']: shutil.copyfile(d/n,a.out_dir/n)
    print('PASS: PDF compiled; 0 error / 0 undefined / 0 Overfull hbox')
if __name__=='__main__': main()
