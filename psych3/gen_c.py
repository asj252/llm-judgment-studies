"""Generate Experiment C materials without model calls."""
import hashlib
import json
import random
from pathlib import Path

from prompts_c import ACCURACY_SETS, ASKS, BASE_RATES, FORMATS, bayes, load_stories, render

SEED = 20261410


def generate_items(stories):
    """Split by story cluster, then enumerate the complete condition grid."""
    shuffled_ids = [story["id"] for story in stories]
    random.Random(SEED).shuffle(shuffled_ids)
    dev = set(shuffled_ids[:4])
    items = []
    for story in stories:
        for acc_set, (hit, fa) in ACCURACY_SETS.items():
            item_id = f"{story['id']}_{acc_set}"
            units = []
            for br in BASE_RATES:
                for format in FORMATS:
                    for ask in ASKS:
                        prompt = render(story, br, acc_set, format, ask)
                        units.append({
                            "unit_id": f"{item_id}_br{br}_{format}_{ask}",
                            "story": story["id"], "acc_set": acc_set,
                            "br": br, "format": format, "ask": ask,
                            "bayes": bayes(br, hit, fa),
                            "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
                        })
            items.append({"item_id": item_id, "story": story["id"],
                          "acc_set": acc_set,
                          "use": "dev" if story["id"] in dev else "formal",
                          "units": units})
    return {"seed": SEED, "cluster": "story",
            "dev_stories": sorted(dev),
            "formal_stories": sorted(set(shuffled_ids) - dev), "items": items}


def preview(stories):
    """Four format/accuracy examples, each at all three base rates."""
    story = stories[0]
    fence = chr(96) * 3
    lines = [
        "# 实验 C 完整题面预览",
        "",
        "每种格式、每组准确率各选一题，列出三个基率，共 12 个完整题面。",
        "问法均为 direct；multi 尾段由测试核对与 δ-NLI 逐字相同。",
        f"情境：{story['id']}。自然频率分母为 10,000。",
        "",
    ]
    for format in FORMATS:
        for acc_set in ACCURACY_SETS:
            lines.extend([f"## {format} / {acc_set}", ""])
            for br in BASE_RATES:
                lines.extend([f"### 基率 {br}%", "", fence + "text",
                              render(story, br, acc_set, format, "direct"), fence, ""])
    return "\n".join(lines)


def all_stories(stories):
    """One complete probability/A/10%/direct prompt per story for review."""
    fence = chr(96) * 3
    lines = [
        "# 实验 C 全部情境复读题面",
        "",
        "24 个情境各列一个完整题面；均为机率格式、A 组、基率 10%、直接问法。",
        "供 a 与用户逐一复读。",
        "",
    ]
    for story in stories:
        lines.extend([f"## {story['id']}", "", fence + "text",
                      render(story, 10, "A", "probability", "direct"), fence, ""])
    return "\n".join(lines)


def main():
    root = Path(__file__).resolve().parent
    stories = load_stories()
    data = generate_items(stories)
    root.joinpath("items_c.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    root.joinpath("items_c_preview.md").write_text(preview(stories), encoding="utf-8")
    root.joinpath("items_c_all_stories.md").write_text(all_stories(stories), encoding="utf-8")
    print(f"Generated {len(data['items'])} items, "
          f"{sum(len(item['units']) for item in data['items'])} units.")
    print("Dev stories: " + ", ".join(data["dev_stories"]))


if __name__ == "__main__":
    main()
