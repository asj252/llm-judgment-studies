"""Generate Experiment E materials without model calls."""
import hashlib
import json
from pathlib import Path

from prompts_e import load_items, render, units

PREVIEW_SPECS = (
    ("neutral", "direct", "中性 / 直接 (neutral, direct)"),
    ("status_T", "direct", "现状目标 / 直接 (status_T, direct)"),
    ("advisor_O", "multi", "顾问另一项 / 多估计 (advisor_O, multi)"),
)


def generate_items(items, repeat_ids=None):
    """Build complete item and unit records with prompt and sha256."""
    by_id = {item["id"]: item for item in items}
    grouped_units = {item["id"]: [] for item in items}

    for item_id, cell, ask, round_id in units(items, repeat_ids=repeat_ids):
        item = by_id[item_id]
        prompt = render(item, cell, ask)
        digest = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        grouped_units[item_id].append(
            {
                "unit_id": f"{item_id}|{cell}|{ask}|{round_id}",
                "id": item_id,
                "item_id": item_id,
                "cell": cell,
                "ask": ask,
                "round": round_id,
                "target": item["target"],
                "prompt": prompt,
                "sha256": digest,
                "prompt_sha256": digest,
            }
        )

    out_items = []
    for item in items:
        item_id = item["id"]
        out_items.append(
            {
                "id": item_id,
                "item_id": item_id,
                "domain": item["domain"],
                "name": item["name"],
                "context": item["context"],
                "option_P": item["option_P"],
                "option_Q": item["option_Q"],
                "target": item["target"],
                "units": grouped_units[item_id],
            }
        )

    return {
        "cluster": "item",
        "n_items": len(out_items),
        "n_units": sum(len(item["units"]) for item in out_items),
        "items": out_items,
    }


def preview(items):
    """Render three example prompts per item (neutral/direct, status_T/direct, advisor_O/multi)."""
    fence = chr(96) * 3
    lines = [
        "# 实验 E 题面预览",
        "",
        "40 题每题列出三个范例全文：中性直接（`neutral` / `direct`）、"
        "`status_T` 直接（`status_T` / `direct`）、`advisor_O` 多估计（`advisor_O` / `multi`）。",
        "",
    ]
    for item in items:
        lines.extend(
            [
                f"## {item['id']} ({item['domain']} — {item['name']}, target={item['target']})",
                "",
            ]
        )
        for cell, ask, label in PREVIEW_SPECS:
            lines.extend(
                [
                    f"### {label}",
                    "",
                    fence + "text",
                    render(item, cell, ask),
                    fence,
                    "",
                ]
            )
    return "\n".join(lines)


def main():
    root = Path(__file__).resolve().parent
    items = load_items()
    data = generate_items(items)
    root.joinpath("items_e.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    root.joinpath("items_e_preview.md").write_text(preview(items), encoding="utf-8")
    print(f"Generated {len(data['items'])} items, {data['n_units']} units.")


if __name__ == "__main__":
    main()
