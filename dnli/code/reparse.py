"""离线重解析已有输出（PLAN v0.6 §4）。不发调用，不改历史会话、结果或指纹。

用法：python -X utf8 -B reparse.py
每次尝试的 v1/v2 解析对照写 raw/reparse_v2.json；控制台只打印格式计数。
原会话纳入与材料指纹仍有效约束：本文件的输出仅作诊断，不能直接纳入主分析。
"""
import json
from collections import Counter, defaultdict
from pathlib import Path
import parse
import run

HERE = Path(__file__).resolve().parent


def parse_attempt(ask, text, truncated=False):
    if truncated:
        return {"v1":{"ok":False,"error":"truncated"}, "v2":{"ok":False,"error":"truncated"}}
    v1 = parse.parse_direct_v1 if ask == "direct" else parse.parse_multi_v1
    return {"v1":v1(text), "v2":parse.PARSERS[ask](text)}


def reparse(base=HERE):
    base = Path(base)
    rows = []
    counts = defaultdict(Counter)
    for cfg in run.CONFIGS:
        raw = base / "raw" / ("run_dev_" + cfg)
        paths = raw.glob("*.last.txt") if cfg == "codex" else raw.glob("*.json")
        for path in sorted(paths):
            tag = path.name.removesuffix(".last.txt" if cfg == "codex" else ".json")
            ask = next((a for a in run.ASKS if "_"+a+"_" in tag), None)
            if ask is None:
                continue
            if cfg == "codex":
                text = path.read_text(encoding="utf-8")
                truncated = False
            else:
                d = json.loads(path.read_text(encoding="utf-8"))
                if "text" not in d:
                    continue
                text, truncated = d["text"], d.get("truncated",False)
            parsed = parse_attempt(ask,text,truncated)
            rows.append({"config":cfg,"tag":tag,"ask":ask,"source":str(path.relative_to(base)),**parsed})
            c = counts[cfg+"|"+ask]
            c["attempts"] += 1
            c["first_attempts"] += tag.endswith("__a0")
            for ver in ("v1","v2"):
                c[ver+"_ok"] += parsed[ver]["ok"]
                if tag.endswith("__a0"):
                    c[ver+"_first_ok"] += parsed[ver]["ok"]
            if parsed["v2"].get("weight_sum_in_tolerance") is not None:
                c["weight_sum_known"] += 1
                c["weight_sum_in_tolerance"] += parsed["v2"]["weight_sum_in_tolerance"]
    out = {"mode":"diagnostic", "parse_version":parse.PARSE_VERSION,
           "note":"Counts are raw attempts, including excluded old items and invalid sessions; not the planned-unit smoke report.",
           "counts":dict(counts), "attempts":rows}
    (base/"raw"/"reparse_v2.json").write_text(json.dumps(out,ensure_ascii=False,indent=1)+"\n",encoding="utf-8",newline="\n")
    return out


if __name__ == "__main__":
    print(json.dumps(reparse()["counts"],ensure_ascii=False,indent=1))
