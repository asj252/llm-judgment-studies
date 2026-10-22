"""提示模板与题面渲染（PLAN v0.2 第 3 节；任务书第 2、3 步）。只用标准库，纯函数。

来源：改写自 ../suppression/prompts.py（v0.5 英文版）。保留：英文、`Probability: NN%` 的答题格式说明、末尾的
「Do not use any tools; answer directly.」（codex 隔离要求；四个配置用同一提示）。改动：去掉演绎／日常指示、前提列表、
E2 与 AP；改为 PLAN 第 3 节的情境框架（先验／陈述后验／转述后验）× 两种问法（直接／多估计），并加入机械的句面规则。

题面（全英文；PLAN 第 3 节，c 第一轮建议 12：P 是已知情境，U 是另外得知的一句话，可用常识，不用「前提绝对为真」）：
  Here is a situation: P
  [Here is something else you learned: U]        ← 陈述后验（stated）
  [Someone said that u]                          ← 转述后验（reported；u＝U 的首字母按规则小写化）
  <空行>
  Using common sense, how likely is it that the following statement is true?
  Statement: H
  <空行> 问法尾段 <空行> Do not use any tools; answer directly.
先验（prior）没有第二行。

机械规则（写死；任何改动都会改变 prompts.py 的哈希，从而改变实验指纹）：
- 句末标点 terminate()：去掉首尾空白；若以 . ! ? 结尾（其后可再跟任意个右引号或右括号 " ' ” ’ )），原样保留；否则补一个句点。
  P、H、U 在所有框架里都用同一规则；句中文字（含拼写错误、双空格、弯引号）一律不改。
- 首字母小写化 lower_initial()（只用于转述）：看 U 的第一个词（按空白切分）。
  1 第一个字符不是字母（如引号开头的片名）→ 不改；2 已是小写 → 不改；
  3 词干（第一个词去掉尾部非字母字符后的 [A-Za-z'’-] 前缀）是 I 或以 I' / I’ 开头 → 不改；
  4 词干除首字母外还有大写字母（缩写或 McX 之类）→ 不改；
  5 词干去掉所有格 's / ’s 后在 PROPER_INITIAL 里 → 不改；
  6 其余 → 第一个字符改成小写。
  PROPER_INITIAL 由检查 δ-SNLI dev＋test 全部有效（非 impossible）更新句的句首词（3,622 句、129 个不同的句首词）定出，
  与抽到哪些题无关：Batman（dev:659）、Christmas（dev:848、test:625）、Sally（test:27，Sally Field）、
  Gone（test:327，片名 Gone With the Wind）、Mom（test:1915，当称呼用）。
"""
import re

FRAME_SITUATION = "Here is a situation: {P}"
FRAME_STATED = "Here is something else you learned: {U}"
FRAME_REPORTED = "Someone said that {u}"
FRAME_QUESTION = ("Using common sense, how likely is it that the following statement is true?\n"
                  "Statement: {H}")
NO_TOOLS = "Do not use any tools; answer directly."

ASK_DIRECT = ("What is the probability that the statement is true?\n\n"
              "On the last line of your answer, give the answer strictly in the following format:\n"
              "Probability: NN%\n"
              "where NN is a number from 0 to 100 (decimals allowed), and it must be followed by a percent sign.")
N_ESTIMATES = 5
ASK_MULTI = ("Give 5 probability estimates that the statement is true, each with a weight for how likely you think "
             "that estimate is; the weights sum to 1.\n\n"
             "At the end of your answer, give the 5 estimates strictly in the following format, one per line:\n"
             + "".join("Estimate %d: NN%% | Weight: W\n" % k for k in range(1, N_ESTIMATES + 1)) +
             "where each NN is a number from 0 to 100 (decimals allowed) followed by a percent sign, and each W is a "
             "number from 0 to 1 (decimals allowed); the five weights sum to 1.")
ASKS = {"direct": ASK_DIRECT, "multi": ASK_MULTI}
PRESENTATIONS = ("prior", "stated", "reported")
UPDATE_TYPES = ("S", "W")

PROPER_INITIAL = ("Batman", "Christmas", "Sally", "Gone", "Mom")
_TERMINAL = re.compile(r"[.!?][\"'”’)]*$")
_STEM = re.compile(r"[A-Za-z][A-Za-z'’\-]*")


def templates():
    """全部模板文字（进实验指纹的「转述模板与问法」）。"""
    return {"situation": FRAME_SITUATION, "stated": FRAME_STATED, "reported": FRAME_REPORTED,
            "question": FRAME_QUESTION, "no_tools": NO_TOOLS, "asks": dict(ASKS),
            "proper_initial": list(PROPER_INITIAL), "terminal_regex": _TERMINAL.pattern, "stem_regex": _STEM.pattern}


def terminate(s):
    s = s.strip()
    return s if _TERMINAL.search(s) else s + "."


def lower_initial(u):
    """返回 (改写后的句子, 规则编号)。规则见文件头。"""
    u = u.strip()
    first = u.split()[0] if u else ""
    if not first or not first[0].isalpha():
        return u, "1_starts_non_letter"
    if first[0].islower():
        return u, "2_already_lower"
    m = _STEM.match(first)
    stem = m.group(0) if m else first
    stem = stem.rstrip("'’-")
    if stem == "I" or stem.startswith("I'") or stem.startswith("I’"):
        return u, "3_pronoun_I"
    if any(c.isupper() for c in stem[1:]):
        return u, "4_internal_capital"
    if re.sub(r"['’]s$", "", stem) in PROPER_INITIAL:
        return u, "5_proper_initial"
    return u[0].lower() + u[1:], "6_lowered"


def update_line(pres, U):
    if pres == "stated":
        return FRAME_STATED.format(U=terminate(U))
    if pres == "reported":
        return FRAME_REPORTED.format(u=terminate(lower_initial(U)[0]))
    raise ValueError(pres)


def render(pres, ask, P, H, U=None):
    """pres ∈ prior/stated/reported；ask ∈ direct/multi；先验时 U 必须为 None。"""
    if ask not in ASKS:
        raise ValueError(ask)
    if pres not in PRESENTATIONS:
        raise ValueError(pres)
    if (pres == "prior") != (U is None):
        raise ValueError("U must be given exactly for posteriors")
    lines = [FRAME_SITUATION.format(P=terminate(P))]
    if pres != "prior":
        lines.append(update_line(pres, U))
    return "\n\n".join(["\n".join(lines), FRAME_QUESTION.format(H=terminate(H)), ASKS[ask], NO_TOOLS])


def render_item(item, pres, utype, ask):
    """item 来自 raw/items_text.json：P、H、U_S、U_W。utype ∈ S/W（先验为 '-'）。"""
    if pres == "prior":
        if utype != "-":
            raise ValueError("prior has no update type")
        return render("prior", ask, item["P"], item["H"])
    if utype not in UPDATE_TYPES:
        raise ValueError(utype)
    return render(pres, ask, item["P"], item["H"], item["U_" + utype])
