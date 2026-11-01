"""S0: pinned data/source validation. Never repair research materials."""
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ROOT, sha256, write_text

COMMIT = "938ef893c3368f3a597e6add2cfebdad02fddebf"
HASHES = {
    "imperfectiveNLI.json": "ddd01d06b18b9bab24abb5bc92a8eb740bb145123658fa9a10bd86e38b4bdb5a",
    "run_inference.py.txt": "5b0fb856ed3ebc0d384ba97887fc3948a09c3269db99572e977d4196ec541880",
}
SOURCE_LINES = {
    6: "from transformers import AutoModelForCausalLM, AutoTokenizer",
    116: "return tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)",
    131: "do_sample=False, # Greedy decoding for reproducibility",
    192: 'parser.add_argument("--max_new_tokens", type=int, default=512, help="Max tokens to generate")',
}
LICENSE = "we release the ImperfectiveNLI dataset under the Creative Commons Attribution-NonCommercial 4.0 International License (CC BY-NC 4.0). This license explicitly permits the distribution and use of the dataset for research purposes."
FIELDS = {"id", "group", "verb_class", "verb", "premise", "hypothesis", "label"}


def verify_sources(data_dir=ROOT / "data"):
    data_dir = Path(data_dir)
    for name, expected in HASHES.items():
        actual = sha256(data_dir / name)
        if actual != expected:
            raise ValueError(f"STOP: sha256 mismatch: {name}: {actual} != {expected}")
    lines = (data_dir / "run_inference.py.txt").read_text(encoding="utf-8").splitlines()
    for number, expected in SOURCE_LINES.items():
        if lines[number - 1].lstrip() != expected:
            raise ValueError(f"STOP: source line {number} mismatch")
    return {n: lines[n - 1] for n in SOURCE_LINES}


def load_items(path=ROOT / "data" / "imperfectiveNLI.json"):
    items = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(items, list) or len(items) != 400:
        raise ValueError("STOP: expected 400 items")
    by_id = {}
    labels = {"A": "False", "B": "True", "C": "Unknown", "D": "True"}
    for item in items:
        if set(item) != FIELDS or not all(isinstance(v, str) for v in item.values()):
            raise ValueError(f"STOP: invalid fields/types: {item!r}")
        match = re.fullmatch(r"([ABCD])_(\d{3})", item["id"])
        if not match or not 1 <= int(match[2]) <= 100:
            raise ValueError(f"STOP: invalid id: {item['id']}")
        if item["id"] in by_id or not item["group"].startswith(match[1] + "_") or item["label"] != labels[match[1]]:
            raise ValueError(f"STOP: duplicate/group/label: {item['id']}")
        by_id[item["id"]] = item
    if len({i["group"] for i in items}) != 4 or Counter(i["id"][0] for i in items) != Counter(dict.fromkeys("ABCD", 100)):
        raise ValueError("STOP: group counts")
    for k in range(1, 101):
        for left, right in (("A", "C"), ("B", "D")):
            a, b = (by_id[f"{g}_{k:03d}"] for g in (left, right))
            if a["verb"] != b["verb"] or a["hypothesis"] != b["hypothesis"]:
                raise ValueError(f"STOP: pair verb/hypothesis: {a['id']}")
            if not a["premise"].startswith(b["premise"].removesuffix(".")):
                raise ValueError(f"STOP: pair premise: {a['id']}")
    return items


def main():
    lines = verify_sources()
    items = load_items()
    text = "# 数据与来源核对（S0）\n\n"
    text += f"来源仓库：https://github.com/boleima/ImperfectiveParadox\n\n固定 commit：`{COMMIT}`；取得日期：2026-10-26。\n\n"
    text += "\n".join(f"- `{name}`：sha256 `{value}`" for name, value in HASHES.items()) + "\n\n"
    text += "授权原句（arXiv 2601.09373 v3，Artifact Usage；d 于 2026-10-26 核实）：\n\n> " + LICENSE + "\n\n"
    text += "仓库无 LICENSE 文件（GitHub API license=null，2026-10-26）。本次离线沿用已取得的副本，未重新查询网络。材料仅供本地研究，不再分发；data/ 与 raw/ 不进入 git。\n\n"
    text += "固定源码逐字抄录（保留原行首空白）：\n\n"
    for n, line in lines.items():
        text += f"第 {n} 行：\n\n```python\n{line}\n```\n\n"
    text += "核对结果：400 条，四组各 100 条；字段、题号、标签及 A/C、B/D 配对全部符合任务书。\n"
    write_text(ROOT / "data-provenance.md", text)
    print(f"S0 PASS: hashes, source lines, structure, labels, pairs; {len(items)} items")


if __name__ == "__main__":
    main()
