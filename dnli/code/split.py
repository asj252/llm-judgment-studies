"""δ-SNLI 抽题（PLAN v0.7 第 2 节；brief-e-v07.md）。只用标准库；只读 data/，不改原始文件。

下列 150 对规则是 build_v1 的历史基线；build_v062 原位替换属性题；build 再续抽 120 对。
最终为 dev 30、formal A 120、formal B 120；原有题、选句与重复子集保持不变。

用法（一律 python -I -X utf8，工作目录不要设在 data/ 里）：
    python -I -X utf8 split.py <dnli_dir> [--out <dir>]
<dnli_dir> 为 connecting-dots/dnli。读取 data/defeasible-snli/{dev,test}.jsonl、download.json（核对数据哈希）、
read20_ids.json、human20_images.json；写出（默认写回 <dnli_dir>）：
    split.json             只放编号与簇（键、图片、用途、所选 S／W 的来源切分、行号、AssignmentIdAnon、候选数），进 git；
    raw/items_text.json    所选 270 对的原文（P、H、U_S、U_W），被 git 排除；
并把筛选流失打印为 JSON（也写进 split.json 的 attrition）。

规则（写死，见 RULE）：
1 dev＋test 合并为候选（行号为各自文件内 0 起的行号，记 split:line）。
2 先排除 UpdateTypeImpossible==true 的行；再按 (Premise, Hypothesis) 原文汇总；只取有效 S、W 都有的 P–H 对。
  核对：每对只有一个 SNLIPairId、一个图片，且不跨 dev／test。
3 簇＝图片（SNLIPairId 中 '#' 之前）。排除 read20_ids.json 的 snli 部分（10 个图片）与 human20_images.json（20 个图片）
  所在图片的全部 P–H 对。
4 键按 (Premise, Hypothesis) 排序；rng = random.Random(SEED)；rng.shuffle(键)；依次走，图片未被取过才取，取满 150 对；
  前 30 对为开发集（use=dev），后 120 对为正式集（use=formal）。于是各对来自不同图片，开发与正式按图片互斥。
5 按第 4 步的取用顺序，每对先 rng.choice(该对的 S 行，按 (split, line) 排序)，再 rng.choice(W 行，同样排序)。
6 重复子集：random.Random(REPEAT_SEED).sample(正式集的键排序后, 20)。
键＝SNLIPairId（官方编号；核对过与 P–H 一一对应）。
"""
import argparse
import hashlib
import json
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

SEED = 20261070
REPEAT_SEED = 20261071
N_DEV, N_FORMAL, N_REPEAT = 30, 120, 20
SPLITS = ("dev", "test")
SOURCE = "rudinger/defeasible-nli@c675ffc1b0eec5fa56287f08490da8ed43c1ecc5"
RULE = ("δ-SNLI dev+test merged (line = 0-based line in data/defeasible-snli/<split>.jsonl). Drop rows with "
        "UpdateTypeImpossible==true; group remaining rows by exact (Premise, Hypothesis); keep pairs with >=1 "
        "strengthener and >=1 weakener. Cluster = image = SNLIPairId before '#'. Drop pairs whose image is among "
        "the snli images of read20_ids.json or the images of human20_images.json. Sort keys by (Premise, "
        "Hypothesis); rng = random.Random(%d); rng.shuffle(keys); walk and keep a pair only if its image is not "
        "yet taken, until %d pairs; first %d = dev, next %d = formal. In that order, for each pair "
        "rng.choice(S rows sorted by (split, line)) then rng.choice(W rows sorted by (split, line)). Repeat "
        "subset = random.Random(%d).sample(sorted formal keys, %d). Key = SNLIPairId."
        % (SEED, N_DEV + N_FORMAL, N_DEV, N_FORMAL, REPEAT_SEED, N_REPEAT))
TYPE = {"S": "strengthener", "W": "weakener"}


def load(path, split):
    rows = []
    with open(path, encoding="utf-8") as f:
        for i, line in enumerate(f):
            if line.strip():
                r = json.loads(line)
                r["_line"], r["_split"] = i, split
                rows.append(r)
    return rows


def image(pair_id):
    return pair_id.split("#", 1)[0]


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def check_data_hashes(base):
    """data/ 的两个文件须与 download.json 记录的 SHA-256 相同。"""
    dl = json.loads((base / "download.json").read_text(encoding="utf-8"))
    want = {f["local_path"].split("connecting-dots/dnli/", 1)[1]: f["sha256"] for f in dl["files"]}
    got = {}
    for sp in SPLITS:
        rel = "data/defeasible-snli/%s.jsonl" % sp
        h = sha256(base / rel)
        if want.get(rel) != h:
            raise SystemExit("STOP: %s hash %s != download.json %s" % (rel, h, want.get(rel)))
        got[rel] = h
    return got


def build_v1(base):
    """返回 (split 字典, 原文字典, 流失统计)。纯函数（只读文件）。"""
    base = Path(base)
    hashes = check_data_hashes(base)
    rows = []
    for sp in SPLITS:
        rows += load(base / "data" / "defeasible-snli" / ("%s.jsonl" % sp), sp)
    read20 = json.loads((base / "read20_ids.json").read_text(encoding="utf-8"))
    read20_imgs = sorted({image(it["pair_id"]) for it in read20["items"] if it["subset"] == "snli"})
    human20_imgs = sorted(json.loads((base / "human20_images.json").read_text(encoding="utf-8"))["images"])
    if len(read20_imgs) != 10 or len(human20_imgs) != 20:
        raise SystemExit("STOP: unexpected exclusion lists %d/%d" % (len(read20_imgs), len(human20_imgs)))

    ok = [r for r in rows if r["UpdateTypeImpossible"] is not True]
    groups_all, groups = defaultdict(list), defaultdict(list)
    for r in rows:
        groups_all[(r["Premise"], r["Hypothesis"])].append(r)
    for r in ok:
        groups[(r["Premise"], r["Hypothesis"])].append(r)
    has = {k: {t: sum(r["UpdateType"] == TYPE[t] for r in g) for t in TYPE} for k, g in groups.items()}
    elig = sorted(k for k in groups if has[k]["S"] and has[k]["W"])
    img_of, pid_of, split_of = {}, {}, {}
    for k in groups_all:
        g = groups_all[k]
        pids = {r["SNLIPairId"] for r in g}
        sps = {r["_split"] for r in g}
        if len(pids) != 1 or len(sps) != 1:
            raise SystemExit("STOP: P-H pair maps to %d SNLIPairIds / %d splits: %r" % (len(pids), len(sps), k))
        pid_of[k] = pids.pop()
        img_of[k] = image(pid_of[k])
        split_of[k] = sps.pop()
    if len(set(pid_of.values())) != len(pid_of):
        raise SystemExit("STOP: SNLIPairId is not one-to-one with (Premise, Hypothesis)")

    excl_read = set(read20_imgs)
    excl_human = set(human20_imgs)
    drop_read = [k for k in elig if img_of[k] in excl_read]
    drop_human = [k for k in elig if img_of[k] in excl_human and img_of[k] not in excl_read]
    pool = [k for k in elig if img_of[k] not in excl_read | excl_human]

    rng = random.Random(SEED)
    shuffled = list(pool)
    rng.shuffle(shuffled)
    chosen, taken, skipped_same_image = [], set(), 0
    for k in shuffled:
        if len(chosen) == N_DEV + N_FORMAL:
            break
        if img_of[k] in taken:
            skipped_same_image += 1
            continue
        chosen.append(k)
        taken.add(img_of[k])
    if len(chosen) != N_DEV + N_FORMAL:
        raise SystemExit("STOP: only %d pairs with distinct images" % len(chosen))

    items, text = [], {}
    for j, k in enumerate(chosen):
        sel = {}
        for t in ("S", "W"):
            cand = sorted((r for r in groups[k] if r["UpdateType"] == TYPE[t]),
                          key=lambda r: (SPLITS.index(r["_split"]), r["_line"]))
            r = rng.choice(cand)
            sel[t] = r
        key = pid_of[k]
        items.append({
            "key": key, "cluster": img_of[k], "use": "dev" if j < N_DEV else "formal", "order": j,
            "source_split": split_of[k],
            "S": {"id": "%s:%d" % (sel["S"]["_split"], sel["S"]["_line"]),
                  "AssignmentIdAnon": sel["S"]["AssignmentIdAnon"]},
            "W": {"id": "%s:%d" % (sel["W"]["_split"], sel["W"]["_line"]),
                  "AssignmentIdAnon": sel["W"]["AssignmentIdAnon"]},
            "n_S_cand": has[k]["S"], "n_W_cand": has[k]["W"],
            "n_S_impossible_dropped": sum(r["UpdateType"] == TYPE["S"] and r["UpdateTypeImpossible"] is True
                                          for r in groups_all[k]),
            "n_W_impossible_dropped": sum(r["UpdateType"] == TYPE["W"] and r["UpdateTypeImpossible"] is True
                                          for r in groups_all[k]),
        })
        text[key] = {"P": k[0], "H": k[1], "U_S": sel["S"]["Update"], "U_W": sel["W"]["Update"],
                     "S_id": items[-1]["S"]["id"], "W_id": items[-1]["W"]["id"]}
    formal_keys = sorted(it["key"] for it in items if it["use"] == "formal")
    repeat = sorted(random.Random(REPEAT_SEED).sample(formal_keys, N_REPEAT))

    lacking = [k for k in groups if not (has[k]["S"] and has[k]["W"])]
    attr = {
        "n_lines": dict(Counter(r["_split"] for r in rows)),
        "n_rows_impossible_dropped": dict(Counter(r["_split"] for r in rows if r["UpdateTypeImpossible"] is True)),
        "n_rows_possible": len(ok),
        "n_ph_pairs_all": len(groups_all),
        "n_ph_pairs_with_possible_rows": len(groups),
        "n_ph_pairs_lacking_S": sum(not has[k]["S"] for k in lacking),
        "n_ph_pairs_lacking_W": sum(not has[k]["W"] for k in lacking),
        "n_ph_pairs_S_and_W": len(elig),
        "n_ph_pairs_S_and_W_by_split": dict(Counter(split_of[k] for k in elig)),
        "n_images_among_eligible": len({img_of[k] for k in elig}),
        "n_images_spanning_dev_and_test": sum(
            1 for v in _img_splits(rows).values() if len(v) > 1),
        "n_pairs_dropped_read20_image": len(drop_read),
        "n_pairs_dropped_human20_image": len(drop_human),
        "n_pool_pairs": len(pool),
        "n_pool_images": len({img_of[k] for k in pool}),
        "n_pairs_skipped_image_taken_while_walking": skipped_same_image,
        "n_chosen": len(chosen),
        "n_chosen_by_source_split": dict(Counter(split_of[k] for k in chosen)),
        "candidate_counts_chosen": {
            "S": dict(sorted(Counter(it["n_S_cand"] for it in items).items())),
            "W": dict(sorted(Counter(it["n_W_cand"] for it in items).items()))},
        "candidate_counts_pool": {
            "S": dict(sorted(Counter(has[k]["S"] for k in pool).items())),
            "W": dict(sorted(Counter(has[k]["W"] for k in pool).items()))},
    }
    split = {"source": SOURCE, "data_sha256": hashes, "seed": SEED, "repeat_seed": REPEAT_SEED, "rule": RULE,
             "excluded_images": {"read20_snli": read20_imgs, "human20": human20_imgs},
             "n": {"dev": N_DEV, "formal": N_FORMAL, "repeat": N_REPEAT},
             "repeat_subset": repeat, "attrition": attr, "items": items}
    return split, text, attr


# 冻结的初筛词表；只筛 H 与已选 S/W，不筛 P 或未选候选句。
ATTRIBUTE_WORDS = (
    "white", "black", "african", "african american", "caucasian", "hispanic", "latino", "latina",
    "asian", "native american", "indian", "arab", "arabic", "japanese", "chinese", "korean",
    "american", "british", "english", "french", "german", "spanish", "mexican", "canadian",
    "italian", "russian", "irish", "scottish", "australian", "brazilian", "jewish", "jew",
    "european", "african-american", "native-american", "middle eastern", "pacific islander",
    "latinx", "indigenous", "biracial", "multiracial", "mixed race", "white american", "black american",
    "taiwanese", "vietnamese", "thai", "indonesian", "malaysian", "filipino", "pakistani", "bangladeshi",
    "nepali", "sri lankan", "iranian", "iraqi", "israeli", "palestinian", "syrian", "lebanese", "saudi",
    "turkish", "greek", "portuguese", "dutch", "belgian", "swiss", "austrian", "polish", "ukrainian",
    "swedish", "norwegian", "danish", "finnish", "icelandic", "welsh", "romanian", "hungarian",
    "cuban", "puerto rican", "colombian", "peruvian", "chilean", "argentinian", "venezuelan",
    "egyptian", "moroccan", "nigerian", "kenyan", "ethiopian", "south african", "ghanaian",
    "mormon", "orthodox", "atheist", "agnostic", "jain", "taoist", "shinto",
    "muslim", "islamic", "christian", "catholic", "protestant", "buddhist", "hindu", "sikh",
    "race", "racial", "ethnicity", "ethnic", "nationality", "religion", "religious",
)
PERSON_WORDS = ("person", "people", "man", "men", "woman", "women", "boy", "boys", "girl", "girls",
                "child", "children", "baby", "babies", "kid", "kids", "gentleman", "lady", "ladies",
                "player", "players", "worker", "workers", "family", "families", "couple", "couples")
_ATTR = "(?:" + "|".join(re.escape(w) for w in sorted(ATTRIBUTE_WORDS, key=len, reverse=True)) + ")"
_NONCOLOR_ATTR = "(?:" + "|".join(re.escape(w) for w in sorted(set(ATTRIBUTE_WORDS)-{"white","black"}, key=len, reverse=True)) + ")"
_PERSON = "(?:" + "|".join(PERSON_WORDS) + ")"
_ATTRIBUTE_PATTERN = re.compile(
    r"\b" + _ATTR + r"\s+(?:(?:young|old|little|adult|male|female)\s+)?" + _PERSON + r"\b"
    + r"|\b(?:is|are|was|were|be|being)\s+(?:(?:a|an|the)\s+)?" + _NONCOLOR_ATTR + r"\b"
    + r"|\b(?:" + _PERSON + r"|he|she|they|someone|somebody)\b[^.!?;\n]{0,100}\b(?:is|are|was|were)\s+(?:white|black)\b"
    + r"|\b(?:race|racial|ethnicity|ethnic|nationality|religion|religious)\b", re.I)


def sensitive_hits(item):
    return {field: sorted({m.group(0) for m in _ATTRIBUTE_PATTERN.finditer(item[field])})
            for field in ("H", "U_S", "U_W") if _ATTRIBUTE_PATTERN.search(item[field])}


class SensitiveReviewRequired(Exception):
    def __init__(self, pending):
        self.pending = pending
        super().__init__("STOP: protected-attribute candidates need a's decisions: "
                         + ", ".join(pending))


def build_v062(base):
    """v0.6：重建 v1 后就地补抽，保留其余题、选句、用途、顺序与重复位置。"""
    base = Path(base)
    result, text, attr = build_v1(base)
    decisions = json.loads((base / "sensitive_decisions.json").read_text(encoding="utf-8"))["decisions"]
    pending = {}
    def excluded(key, item):
        hits = sensitive_hits(item)
        if key in decisions:
            return decisions[key]["exclude"]
        if hits:
            pending[key] = dict(item, hits=hits)
        return False
    removed = [it for it in result["items"] if excluded(it["key"], text[it["key"]])]
    screened = [it["key"] for it in result["items"] if sensitive_hits(text[it["key"]])]
    if pending:
        raise SensitiveReviewRequired(pending)
    rows = [r for sp in SPLITS for r in load(base / "data" / "defeasible-snli" / (sp + ".jsonl"), sp)]
    groups = defaultdict(list)
    for r in rows:
        if r["UpdateTypeImpossible"] is not True:
            groups[(r["Premise"], r["Hypothesis"])].append(r)
    excluded_images = set(result["excluded_images"]["read20_snli"] + result["excluded_images"]["human20"])
    pool = sorted(k for k, g in groups.items() if image(g[0]["SNLIPairId"]) not in excluded_images
                  and {r["UpdateType"] for r in g} >= set(TYPE.values()))
    random.Random(SEED).shuffle(pool)
    last = next(i for i, k in enumerate(pool) if groups[k][0]["SNLIPairId"] == result["items"][-1]["key"])
    taken = {it["cluster"] for it in result["items"]}
    replacements = []
    cursor = iter(pool[last + 1:])
    for old in removed:
        for k in cursor:
            g = groups[k]
            key = g[0]["SNLIPairId"]
            if image(key) in taken:
                continue
            rng = random.Random(key)
            sel = {t: rng.choice(sorted((r for r in g if r["UpdateType"] == TYPE[t]),
                                       key=lambda r: (SPLITS.index(r["_split"]), r["_line"]))) for t in ("S", "W")}
            new_text = {"P": k[0], "H": k[1], "U_S": sel["S"]["Update"], "U_W": sel["W"]["Update"],
                        **{t + "_id": "%s:%d" % (sel[t]["_split"], sel[t]["_line"]) for t in ("S", "W")}}
            if excluded(key, new_text):
                continue
            if pending:
                raise SensitiveReviewRequired(pending)
            new = {"key": key, "cluster": image(key), "use": old["use"], "order": old["order"],
                   "source_split": g[0]["_split"]}
            for t in ("S", "W"):
                new[t] = {"id": new_text[t + "_id"], "AssignmentIdAnon": sel[t]["AssignmentIdAnon"]}
                new["n_%s_cand" % t] = sum(r["UpdateType"] == TYPE[t] for r in g)
                new["n_%s_impossible_dropped" % t] = sum(r["SNLIPairId"] == key and r["UpdateType"] == TYPE[t]
                                                        and r["UpdateTypeImpossible"] is True for r in rows)
            result["items"][old["order"]] = new
            text.pop(old["key"])
            text[key] = new_text
            result["repeat_subset"] = [key if x == old["key"] else x for x in result["repeat_subset"]]
            taken.add(image(key))
            replacements.append({"excluded": old["key"], "replacement": key, "order": old["order"],
                                 "use": old["use"], "inherits_repeat": key in result["repeat_subset"]})
            break
        else:
            raise SystemExit("STOP: replacement pool exhausted")
    result["rule"] += (" v0.6: screen H and selected S/W with ATTRIBUTE_WORDS/PERSON_WORDS; a's frozen "
                       "sensitive_decisions.json decides hits. Replace excluded pairs in original slot order from "
                       "the remaining original shuffled pool, skipping taken images; replacement choices use "
                       "random.Random(SNLIPairId). All retained items and selections stay unchanged; replacements "
                       "inherit use/order/repeat positions; undecided hits stop before writing.")
    result["sensitive_decisions_sha256"] = sha256(base / "sensitive_decisions.json")
    attr["protected_attribute_replacements"] = replacements
    attr["n_protected_attribute_excluded"] = len(removed)
    attr["protected_attribute_screened_v1"] = screened
    attr["protected_attribute_decisions_file"] = "sensitive_decisions.json"
    attr["n_chosen_by_source_split"] = dict(Counter(it["source_split"] for it in result["items"]))
    attr["candidate_counts_chosen"] = {t: dict(sorted(Counter(it["n_%s_cand" % t] for it in result["items"]).items()))
                                        for t in ("S", "W")}
    return result, text, attr


def build(base):
    """v0.7：保留 v0.6.2 的 150 对，从其消费游标继续补抽 block B。"""
    base = Path(base)
    result, text, attr = build_v062(base)
    v1, _, _ = build_v1(base)
    rows = [r for sp in SPLITS for r in load(base / 'data/defeasible-snli' / (sp + '.jsonl'), sp)]
    groups = defaultdict(list)
    for r in rows:
        if r['UpdateTypeImpossible'] is not True:
            groups[(r['Premise'], r['Hypothesis'])].append(r)
    blocked = set(result['excluded_images']['read20_snli'] + result['excluded_images']['human20'])
    pool = sorted(k for k, g in groups.items() if image(g[0]['SNLIPairId']) not in blocked
                  and {r['UpdateType'] for r in g} >= set(TYPE.values()))
    random.Random(SEED).shuffle(pool)
    consumed = {it['key'] for it in v1['items'] + result['items']}
    last = max(i for i, k in enumerate(pool) if groups[k][0]['SNLIPairId'] in consumed)
    taken = {it['cluster'] for it in v1['items'] + result['items']}
    decisions = json.loads((base / 'sensitive_decisions.json').read_text(encoding='utf-8'))['decisions']
    speech = json.loads((base / 'speech_updates.json').read_text(encoding='utf-8'))
    reviewed_speech = set(speech['update_ids']) | set(speech.get('reviewed_not_included', []))
    speech_pattern = re.compile(r'\b(?:comments?|says?|said|saying|asks?|asked|asking|tells?|told|telling|yells?|yelled|yelling|overheard|shouts?|shouted|shouting|speaks?|speaking|talks?|talking|whispers?|whispered|replies?|replied|exclaims?|exclaimed|states?|stated|instructions|nagging|called|refers?)\b|["“”]', re.I)
    skipped, screened, excluded, added, pending, pending_speech = 0, [], [], [], {}, []
    for i in range(last + 1, len(pool)):
        k, g = pool[i], groups[pool[i]]
        key = g[0]['SNLIPairId']
        if image(key) in taken:
            skipped += 1
            continue
        rng = random.Random(key)
        sel = {t: rng.choice(sorted((r for r in g if r['UpdateType'] == TYPE[t]),
                                   key=lambda r: (SPLITS.index(r['_split']), r['_line']))) for t in ('S', 'W')}
        nt = {'P': k[0], 'H': k[1], **{'U_' + t: sel[t]['Update'] for t in ('S', 'W')},
              **{t + '_id': '%s:%d' % (sel[t]['_split'], sel[t]['_line']) for t in ('S', 'W')}}
        hits = sensitive_hits(nt)
        if hits:
            screened.append(key)
        if key in decisions and decisions[key]['exclude']:
            excluded.append(key)
            continue
        if hits and key not in decisions:
            pending[key] = dict(nt, hits=hits)
        for t in ('S', 'W'):
            uid = nt[t + '_id']
            if uid not in reviewed_speech and speech_pattern.search(nt['U_' + t]):
                pending_speech.append({'key': key, 'type': t, 'id': uid, 'update': nt['U_' + t]})
        it = {'key': key, 'cluster': image(key), 'use': 'formal', 'formal_block': 'B',
              'order': 150 + len(added), 'source_split': g[0]['_split']}
        for t in ('S', 'W'):
            it[t] = {'id': nt[t + '_id'], 'AssignmentIdAnon': sel[t]['AssignmentIdAnon']}
            it['n_%s_cand' % t] = sum(r['UpdateType'] == TYPE[t] for r in g)
            it['n_%s_impossible_dropped' % t] = sum(r['SNLIPairId'] == key and r['UpdateType'] == TYPE[t]
                                                    and r['UpdateTypeImpossible'] is True for r in rows)
        added.append(it)
        text[key] = nt
        taken.add(image(key))
        if len(added) == 120:
            break
    if pending:
        raise SensitiveReviewRequired(pending)
    if pending_speech:
        raise SpeechReviewRequired(pending_speech)
    if len(added) != 120:
        raise SystemExit('STOP: extension pool exhausted')
    for it in result['items']:
        if it['use'] == 'formal':
            it['formal_block'] = 'A'
    result['items'].extend(added)
    result['n']['formal'] = 240
    result['n']['formal_blocks'] = {'A': 120, 'B': 120}
    result['rule'] += (' v0.7: continue after all v0.6 replacements; select 120 further formal pairs as block B, '
                       'using random.Random(SNLIPairId) for updates; original formal pairs are block A; '
                       'local configs use A+B, codex uses A; repeat subset unchanged.')
    attr['extension_v07'] = {'start_cursor_0based': last + 1, 'end_cursor_0based': i,
        'remaining_unwalked_pairs': len(pool) - i - 1, 'skipped_image_taken': skipped,
        'screened_keys': screened, 'excluded_keys': excluded, 'n_added': len(added)}
    attr['n_chosen'] = len(result['items'])
    attr['n_chosen_by_source_split'] = dict(Counter(it['source_split'] for it in result['items']))
    attr['candidate_counts_chosen'] = {t: dict(sorted(Counter(it['n_%s_cand' % t] for it in result['items']).items()))
                                      for t in ('S', 'W')}
    return result, text, attr


class SpeechReviewRequired(Exception):
    def __init__(self, pending):
        self.pending = pending
        super().__init__("STOP: speech candidates need a's decisions: " + ', '.join(it['id'] for it in pending))


def _img_splits(rows):
    d = defaultdict(set)
    for r in rows:
        d[image(r["SNLIPairId"])].add(r["_split"])
    return d


def dump(path, obj):
    Path(path).write_text(json.dumps(obj, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("base")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    out = Path(a.out or a.base)
    split, text, attr = build(Path(a.base))
    (out / "raw").mkdir(parents=True, exist_ok=True)
    dump(out / "split.json", split)
    dump(out / "raw" / "items_text.json", text)
    print(json.dumps(attr, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    sys.exit(main())
