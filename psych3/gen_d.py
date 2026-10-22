"""Generate Experiment D's 420 units; no model calls."""
import hashlib
import json
import random
from pathlib import Path

from prompts_d import ASKS, STATEMENTS, STRATA, load_items, render

ORDER_SEED, SPLIT_SEED, REPEAT_SEED = 20261430, 20261431, 20261432


def generate_items(items, order_seed=ORDER_SEED, split_seed=SPLIT_SEED, repeat_seed=REPEAT_SEED):
    """Separate RNG streams, traversing bank order and the explicit STRATA order."""
    split_rng, repeat_rng, order_rng = map(random.Random, (split_seed, repeat_seed, order_seed))
    profiles = [i["id"] for i in items if i["type"] == "P"]
    dev = set(split_rng.sample(profiles, 4))
    for stratum in STRATA:
        ids = [i["id"] for i in items if i.get("stratum") == stratum]
        dev.update(split_rng.sample(ids, 1))
    repeats = set(repeat_rng.sample([i for i in profiles if i not in dev], 4))
    for stratum in repeat_rng.sample(list(STRATA), 2):
        repeats.update(repeat_rng.sample([i["id"] for i in items
                                         if i.get("stratum") == stratum and i["id"] not in dev], 1))
    result = []
    for item in items:
        order = list(STATEMENTS)
        order_rng.shuffle(order)
        base = {"item_id": item["id"], "type": item["type"],
                "split": "dev" if item["id"] in dev else "formal", "repeat": item["id"] in repeats}
        if item["type"] == "W":
            base["stratum"] = item["stratum"]
        units = []
        for pres, stmt in [("S", s) for s in STATEMENTS] + [("J", None)]:
            for ask in ASKS:
                prompt = render(item, pres, ask, stmt=stmt, order=order if pres == "J" else None)
                unit = dict(base, unit=f"{item['id']}_{pres}_{stmt + '_' if stmt else ''}{ask}",
                            pres=pres, ask=ask, prompt=prompt,
                            prompt_sha256=hashlib.sha256(prompt.encode("utf-8")).hexdigest())
                if pres == "S":
                    unit["stmt"] = stmt
                else:
                    unit["order"] = list(order)
                units.append(unit)
        result.append(dict(base, units=units))
    return {"bank_version": "v0.2", "order_seed": order_seed, "split_seed": split_seed,
            "repeat_seed": repeat_seed, "cluster": "item_id", "dev_items": sorted(dev),
            "repeat_items": sorted(repeats), "items": result}


def _markdown(title, units):
    fence = chr(96) * 3
    lines = ["# " + title, ""]
    for unit in units:
        lines.extend(["## " + unit["unit"], "", fence + "text", unit["prompt"], fence, ""])
    return "\n".join(lines)


def preview(data):
    chosen = [next(i for i in data["items"] if i["type"] == t) for t in ("P", "W")]
    return _markdown("实验 D 完整题面预览（P、W 各一题，全部 10 个 unit）",
                     [u for i in chosen for u in i["units"]])


def all_items(data):
    return _markdown("实验 D 全部同页直接题面（42 题）",
                     [u for i in data["items"] for u in i["units"] if u["pres"] == "J" and u["ask"] == "direct"])


def main():
    root = Path(__file__).resolve().parent
    data = generate_items(load_items())
    for name, text in (("items_d.json", json.dumps(data, ensure_ascii=False, indent=2) + "\n"),
                       ("items_d_preview.md", preview(data)), ("items_d_all.md", all_items(data))):
        root.joinpath(name).write_text(text, encoding="utf-8")
        if chr(63) * 3 in root.joinpath(name).read_text(encoding="utf-8"):
            raise ValueError("Encoding check failed: " + name)
    print(f"Generated {len(data['items'])} items, {sum(len(i['units']) for i in data['items'])} units.")
    print("Dev: " + ", ".join(data["dev_items"]))
    print("Repeat (formal): " + ", ".join(data["repeat_items"]))


if __name__ == "__main__":
    main()
