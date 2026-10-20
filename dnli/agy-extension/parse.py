# Copied from ../dnli/parse.py; only this provenance comment added; v2 rules unchanged.
"""解析 v2（PLAN v0.6.2 §4）：直接取最后字段（无值失败）、多估计取末组、正权重和归一。
下列旧规则说明仅对应保留的 parse_direct_v1 / parse_multi_v1。

原解析（PLAN v0.2 第 4 节；任务书第 4 步）。只用标准库，纯函数。

来源：复制自 ../suppression/parse.py。直接问法的规则（parse_direct＝原 parse_e1）逐字沿用；删去 E2；新增多估计问法 parse_multi。

直接问法：只认最终答案里的 `Probability: NN%`（规则同原文件，摘要如下）。
- 先去掉 thinking：文字里若有 `</think>`，只取最后一个 `</think>` 之后；有未闭合的 `<think>` 判失败（thinking_unterminated）。
- 字段 = 词 probability（大小写不敏感，前后可有 markdown 的 * 或 _）后接半角或全角冒号；恰好 1 个，0 个 no_field，多个 multiple_fields。
- 值：同一行、跳过空白与 * _，`[-+]?数字[.数字]` 紧接 `%`（中间至多一个空格）；无 % → no_percent；写法不完整 → malformed；
  越出 [0, 100] → out_of_range；% 之后同一行再有数字或 % → range_or_extra_number。

多估计问法（PLAN 第 4 节；c 第一轮阻断 6）：
- 先去掉 thinking（同上）。
- 估计字段 = 词 estimate（大小写不敏感，前后可有 * _）＋空白＋编号 k＋（可有 * _）＋半角或全角冒号；可在行内任意位置。
  一行里有 2 个以上估计字段 → multiple_estimate_fields_in_line。
- 估计行恰好 5 行，编号恰好是 1–5 各一次（顺序不限）：行数不是 5 → n_estimates_k（k 为实际行数；含整张表写了两遍的情况）；
  编号重复 → duplicate_index；编号不在 1–5 → bad_index。
- 每个估计行：估计字段之后恰有一个 Weight 字段（词 weight，前后可有 * _，接半角或全角冒号）；0 个 missing_weight，多个 multiple_weights。
  - 估计值在 Weight 字段之前：按直接问法的值规则（0–100、带 %），错误加前缀 estimate_；% 之后到 Weight 字段之前不得再有数字或 %
    （estimate_range_or_extra_number），可有其他文字与分隔符（| , ; 括号等）。
  - 权重在 Weight 字段之后：`[-+]?数字[.数字]`，或无前导零的小数 `[-+]?.数字`（如 `.2`；PLAN v0.4 第 4 节、c 第二轮 S1）；
    后接 % → weight_percent；无数字 → weight_no_number；`1e-1`、`1/5` 之类 → weight_malformed；越出 [0, 1] → weight_out_of_range；数字之后同一行不得再有数字或 %（weight_extra_number）。
- 权重和须在 [0.95, 1.05]，否则 weight_sum_out_of_tolerance:<和>；在容差内则按和归一。
- 「重复」指估计编号重复；估计值相同是允许的（PLAN v0.2 不再要求 different）。
- 截断由 run.py 判（截断的尝试不解析，记 truncated）。
- 返回：聚合值 value＝Σ w̃·p（0–100）；另给候选层描述量：加权端点质量 endpoint_mass＝Σ w̃·[p ≤ 5 或 p ≥ 95]，
  加权标准差 weighted_sd＝sqrt(Σ w̃·(p − value)²)。
"""
import math
import re

THINK_OPEN = "<think>"
THINK_CLOSE = "</think>"
N_ESTIMATES = 5
PARSE_VERSION = 2
WSUM_LO, WSUM_HI = 0.95, 1.05
ENDPOINT_LO, ENDPOINT_HI = 5.0, 95.0

_FIELD = re.compile(r"(?P<pre>[*_]*)(?P<key>probability)(?P<post>[*_]*)[ \t]*(?P<colon>[:：])", re.IGNORECASE)
_VALUE = re.compile(r"[ \t*_]*(?P<num>[-+]?\d+(?:\.\d+)?)(?P<sp> ?)%")
_BAD_NUM = re.compile(r"[ \t*_]*[-+]?(?:\d*\.\d*|\d+)(?:[eE][-+]?\d+)?[ \t]?%")
_DIGIT_OR_PCT = re.compile(r"[\d%]")
_EST_FIELD = re.compile(r"[*_]*(?<![A-Za-z])estimate[*_]*[ \t]*(?P<k>\d+)[*_]*[ \t]*[:：]", re.IGNORECASE)
_EST_LOOSE = re.compile(r"[*_]*(?<![A-Za-z])estimate[*_]*[ \t]*(?P<k>\d+)", re.IGNORECASE)
_W_FIELD = re.compile(r"[*_]*(?<![A-Za-z])weight[*_]*[ \t]*[:：]", re.IGNORECASE)
_W_VALUE = re.compile(r"[ \t*_]*(?P<num>[-+]?(?:\d+(?:\.\d+)?|\.\d+))")
_W_BAD = re.compile(r"[ \t*_]*[-+]?(?:\d*\.\d*|\d+)(?:[eE][-+]?\d+|/\d+)?")


def is_endpoint(v):
    return v <= ENDPOINT_LO or v >= ENDPOINT_HI


def strip_thinking(text):
    """返回 (最终答案文字, 错误)。"""
    if text is None:
        return None, "no_text"
    if THINK_CLOSE in text:
        return text.rsplit(THINK_CLOSE, 1)[1], None
    if THINK_OPEN in text:
        return None, "thinking_unterminated"
    return text, None


def _value_after(s):
    """s 是字段冒号之后、到行尾的文字。返回 (值, 写法集合, 错误)。（与 ../suppression/parse.py 相同）"""
    forms = set()
    m = _VALUE.match(s)
    if not m:
        if _BAD_NUM.match(s):
            return None, forms, "malformed"
        stripped = s.strip(" \t*_")
        if re.match(r"[-+]?(\d+(\.\d*)?|\.\d+)", stripped):
            return None, forms, "no_percent"
        return None, forms, "no_number"
    if m.group("sp"):
        forms.add("space_before_percent")
    if "*" in s[:m.start("num")] or "_" in s[:m.start("num")]:
        forms.add("bold")
    after = s[m.end():]
    if _DIGIT_OR_PCT.search(after):
        return None, forms, "range_or_extra_number"
    if after.strip(" \t*_.,;:)。，；"):
        forms.add("trailing_text")
    v = float(m.group("num"))
    if not math.isfinite(v):
        return None, forms, "non_finite"
    if not (0.0 <= v <= 100.0):
        return None, forms, "out_of_range"
    return v, forms, None


def parse_direct_v1(text):
    """返回 dict(ok, value, error, forms)。value 为 0–100 的浮点数。（＝ ../suppression/parse.py 的 parse_e1）"""
    final, err = strip_thinking(text)
    if err:
        return {"ok": False, "value": None, "error": err, "forms": []}
    fields = list(_FIELD.finditer(final))
    if not fields:
        return {"ok": False, "value": None, "error": "no_field", "forms": []}
    if len(fields) > 1:
        return {"ok": False, "value": None, "error": "multiple_fields", "forms": []}
    f = fields[0]
    forms = set()
    if f.group("pre") or f.group("post"):
        forms.add("bold")
    if f.group("colon") == "：":
        forms.add("fullwidth_colon")
    if f.group("key") != "Probability":
        forms.add("lowercase_key" if f.group("key") == "probability" else "other_case_key")
    line_rest = final[f.end():].split("\n", 1)[0]
    v, vf, err = _value_after(line_rest)
    forms |= vf
    if err:
        return {"ok": False, "value": None, "error": err, "forms": sorted(forms)}
    return {"ok": True, "value": v, "error": None, "forms": sorted(forms) or ["plain"]}


def _weight_after(s):
    """s 是 Weight 冒号之后、到行尾的文字。返回 (权重, 错误)。"""
    m = _W_VALUE.match(s)
    bad = _W_BAD.match(s)
    if not m:
        if bad and re.search(r"\d", bad.group(0)):
            return None, "weight_malformed"
        return None, "weight_no_number"
    after = s[m.end():]
    if after[:1] in (".", "e", "E", "/") and re.match(r"[./eE]\S*\d", after):
        return None, "weight_malformed"
    if after.lstrip(" \t").startswith("%"):
        return None, "weight_percent"
    if _DIGIT_OR_PCT.search(after):
        return None, "weight_extra_number"
    w = float(m.group("num"))
    if not math.isfinite(w):
        return None, "weight_malformed"
    if not (0.0 <= w <= 1.0):
        return None, "weight_out_of_range"
    return w, None


def _multi_fail(err, forms=()):
    return {"ok": False, "value": None, "error": err, "estimates": None, "weights": None, "weight_sum": None,
            "endpoint_mass": None, "weighted_sd": None, "forms": sorted(forms)}


def parse_multi_v1(text):
    """返回 dict(ok, value, error, estimates, weights（归一前）, weight_sum, endpoint_mass, weighted_sd, forms)。"""
    final, err = strip_thinking(text)
    if err:
        return _multi_fail(err)
    rows, forms = [], set()
    for line in final.splitlines():
        fields = list(_EST_FIELD.finditer(line))
        if not fields:
            continue
        if len(fields) > 1:
            return _multi_fail("multiple_estimate_fields_in_line")
        f = fields[0]
        if "*" in f.group(0) or "_" in f.group(0):
            forms.add("bold")
        if "：" in f.group(0):
            forms.add("fullwidth_colon")
        rest = line[f.end():]
        wf = list(_W_FIELD.finditer(rest))
        if not wf:
            return _multi_fail("missing_weight")
        if len(wf) > 1:
            return _multi_fail("multiple_weights")
        left, right = rest[:wf[0].start()], rest[wf[0].end():]
        v, vf, e = _value_after(left.rstrip(" \t|,;(["))
        if e:
            return _multi_fail("estimate_" + e)
        forms |= (vf - {"trailing_text"})
        w, e = _weight_after(right)
        if e:
            return _multi_fail(e)
        rows.append((int(f.group("k")), v, w))
    if len(rows) != N_ESTIMATES:
        return _multi_fail("n_estimates_%d" % len(rows))
    idx = [k for k, _, _ in rows]
    if len(set(idx)) != len(idx):
        return _multi_fail("duplicate_index")
    if set(idx) != set(range(1, N_ESTIMATES + 1)):
        return _multi_fail("bad_index")
    ws = sum(w for _, _, w in rows)
    if not (WSUM_LO <= ws <= WSUM_HI):
        return _multi_fail("weight_sum_out_of_tolerance:%.4f" % ws)
    rows.sort()
    ps = [v for _, v, _ in rows]
    wn = [w / ws for _, _, w in rows]
    agg = sum(w * p for w, p in zip(wn, ps))
    return {"ok": True, "value": agg, "error": None, "estimates": ps, "weights": [w for _, _, w in rows],
            "weight_sum": ws, "endpoint_mass": sum(w for w, p in zip(wn, ps) if is_endpoint(p)),
            "weighted_sd": math.sqrt(max(0.0, sum(w * (p - agg) ** 2 for w, p in zip(wn, ps)))),
            "forms": sorted(forms) or ["plain"]}


def parse_direct(text):
    """v2：最后字段同一行必须有合法数值；此前无值标题不影响结果。"""
    final, err = strip_thinking(text)
    if err:
        return parse_direct_v1(text)
    fields = list(_FIELD.finditer(final))
    if not fields:
        return parse_direct_v1(final)
    candidate = final[fields[-1].start():].split("\n", 1)[0]
    return parse_direct_v1(candidate)


def parse_multi(text):
    """v2：最后一个宽松 Estimate 1 行到结尾为末组；正权重和归一。"""
    final, err = strip_thinking(text)
    if err:
        return dict(_multi_fail(err), weight_sum_in_tolerance=None)
    all_lines = final.splitlines()
    starts = [i for i, line in enumerate(all_lines)
              if any(int(f.group("k")) == 1 for f in _EST_LOOSE.finditer(line))]
    lines = [line for line in all_lines[starts[-1] if starts else 0:] if _EST_LOOSE.search(line)]
    if len(lines) != N_ESTIMATES:
        return dict(_multi_fail("n_estimates_%d" % len(lines)), weight_sum_in_tolerance=None)
    idx = [int(f.group("k")) for line in lines for f in _EST_LOOSE.finditer(line)]
    if len(idx) != len(lines):
        return dict(_multi_fail("multiple_estimate_fields_in_line"), weight_sum_in_tolerance=None)
    if len(set(idx)) != len(idx):
        return dict(_multi_fail("duplicate_index"), weight_sum_in_tolerance=None)
    if set(idx) != set(range(1, N_ESTIMATES + 1)):
        return dict(_multi_fail("bad_index"), weight_sum_in_tolerance=None)
    rows, forms = [], set()
    for line in lines:
        fields = list(_EST_FIELD.finditer(line))
        if len(fields) != 1:
            return dict(_multi_fail("malformed_estimate_field"), weight_sum_in_tolerance=None)
        f = fields[0]
        rest = line[f.end():]
        wf = list(_W_FIELD.finditer(rest))
        if len(wf) != 1:
            return dict(_multi_fail("missing_weight" if not wf else "multiple_weights"), weight_sum_in_tolerance=None)
        v, vf, err = _value_after(rest[:wf[0].start()].rstrip(" \t|,;(["))
        if err:
            return dict(_multi_fail("estimate_" + err), weight_sum_in_tolerance=None)
        w, err = _weight_after(rest[wf[0].end():])
        if err:
            return dict(_multi_fail(err), weight_sum_in_tolerance=None)
        forms |= vf - {"trailing_text"}
        if "*" in f.group(0) or "_" in f.group(0):
            forms.add("bold")
        if "：" in f.group(0):
            forms.add("fullwidth_colon")
        rows.append((int(f.group("k")), v, w))
    idx = [k for k, _, _ in rows]
    if len(set(idx)) != N_ESTIMATES:
        return dict(_multi_fail("duplicate_index"), weight_sum_in_tolerance=None)
    if set(idx) != set(range(1, N_ESTIMATES + 1)):
        return dict(_multi_fail("bad_index"), weight_sum_in_tolerance=None)
    rows.sort()
    ws = sum(w for _, _, w in rows)
    if ws <= 0:
        return dict(_multi_fail("weight_sum_not_positive"), weight_sum=ws, weight_sum_in_tolerance=False)
    ps = [p for _, p, _ in rows]
    wn = [w / ws for _, _, w in rows]
    value = sum(w * p for w, p in zip(wn, ps))
    return {"ok": True, "value": value, "error": None, "estimates": ps,
            "weights": [w for _, _, w in rows], "weight_sum": ws,
            "weight_sum_in_tolerance": WSUM_LO <= ws <= WSUM_HI,
            "endpoint_mass": sum(w for w, p in zip(wn, ps) if is_endpoint(p)),
            "weighted_sd": math.sqrt(max(0.0, sum(w * (p - value) ** 2 for w, p in zip(wn, ps)))),
            "forms": sorted(forms) or ["plain"]}


PARSERS = {"direct": parse_direct, "multi": parse_multi}
