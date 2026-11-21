# Surface Ties and Stereotype Updating Across Language Model Readouts: A Multi-Channel Measurement Study

An-Sheng Jhang · Dongguan University of Technology · ansheng.jhang@gmail.com

[SSRN 7736298](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=7736298) · [public dataset (Hugging Face)](https://huggingface.co/datasets/anshengjhang/stereotype-readouts-formal)

This GitHub companion provides code, stimuli and derived summaries. `paper/paper.pdf` is the immutable SSRN 7736298 submission snapshot; its historical availability statements describe the submission date. The GitHub companion is public upon publication of this staged tree. The companion HF dataset is pending author license sign-off and upload, although the author has authorized CC-BY-4.0 redistribution of the 11 formal files (44,640 records). The 24 development records are excluded.

Python 3.11+; no Python packages required. TeX Live with pdflatex and bibtex is optional for PDF reproduction. Download the HF `data/` directory after publication, then run from a clean directory containing this companion:

```bash
python3 -X utf8 -B code/reproduce_tie_and_nontie.py --data-dir data --stimuli stimuli/formal_stimuli.json --out-dir reproduced
python3 -X utf8 -B code/reproduce_paper_pdf.py --paper-dir paper --out-dir rebuilt-paper
```

The summaries contain descriptive readout comparisons, not causal identification of a latent mechanism. The legacy evaluator exposes the original statistical routines; the reproduction entry point handles the formal scale and channel extraction.

```bibtex
@misc{jhang2026surfaceties,
  author = {An-Sheng Jhang},
  title = {Surface Ties and Stereotype Updating Across Language Model Readouts: A Multi-Channel Measurement Study},
  year = {2026},
  howpublished = {SSRN 7736298},
  url = {https://papers.ssrn.com/sol3/papers.cfm?abstract_id=7736298}
}
```
