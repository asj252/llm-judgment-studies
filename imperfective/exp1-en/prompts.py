"""Experiment 1 prompts; literal upstream L templates are parsed, never executed.

P/M framework adaptations (brief appendix A.3): remove DAP's prohibition on
common-sense assumptions; replace premise/hypothesis by situation/statement;
replace CF necessity judgment and JSON instructions with 'Then give your answer.'
The copied ASK controls the answer format. No delta-NLI tools instruction.
"""
import ast
from functools import lru_cache
from common import ROOT
from prompt_parts import ASK_DIRECT, ASK_MULTI, terminate

COMBINATIONS = (("L", "Z"), ("L", "DAP"), ("L", "CoT"), ("L", "CF"), ("Ps", "Z"),
                ("P", "Z"), ("P", "DAP"), ("P", "CoT"), ("P", "CF"),
                ("M", "Z"), ("M", "DAP"), ("M", "CoT"), ("M", "CF"))
KEYS = {"Z": "zero-shot", "DAP": "dap", "CoT": "cot", "CF": "counterfactual"}
RULE = ('Important Linguistic Rule: Note the distinction between activity and accomplishment verbs.\n'
        '- For accomplishments/goal-oriented actions (e.g., "was building", "was writing"), the progressive form does NOT imply completion.\n'
        '- For activities (e.g., "was running", "was singing"), the process implies the action occurred.')
INSTRUCTIONS = {
    "CoT": "First, analyze the temporal status of the event in the situation. Does the action have a defined endpoint? Was it completed? Then give your answer.",
    "CF": "First, list 3 possible real-world scenarios where the action in the situation occurs but the result in the statement is NOT achieved (e.g., interruptions, failures). Then give your answer.",
}
PS = ("User Input: Premise: {premise} Hypothesis: {hypothesis}\n"
      "What is the probability that the Hypothesis is necessarily true given only the Premise?\n\n"
      "On the last line of your answer, give the answer strictly in the following format:\n"
      "Probability: NN%\n"
      "where NN is a number from 0 to 100 (decimals allowed), and it must be followed by a percent sign.")


@lru_cache(maxsize=1)
def original_templates():
    tree = ast.parse((ROOT / "data" / "run_inference.py.txt").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "PROMPT_TEMPLATES" for t in node.targets):
            return ast.literal_eval(node.value)
    raise ValueError("PROMPT_TEMPLATES dictionary literal not found")


def render_unit(item, task, prompt):
    if (task, prompt) not in COMBINATIONS:
        raise ValueError((task, prompt))
    if task in ("L", "Ps"):
        t = original_templates()[KEYS[prompt]]
        user = t["user_format"] if task == "L" else PS
        return [{"role": "system", "content": t["system"]},
                {"role": "user", "content": user.format(premise=item["premise"], hypothesis=item["hypothesis"])}]
    parts = ["Here is a situation: " + terminate(item["premise"])]
    if prompt == "DAP":
        parts.append(RULE)
    parts.append("Using common sense, how likely is it that the following statement is true?\nStatement: " + terminate(item["hypothesis"]))
    if prompt in INSTRUCTIONS:
        parts.append(INSTRUCTIONS[prompt])
    parts.append(ASK_DIRECT if task == "P" else ASK_MULTI)
    return [{"role": "user", "content": "\n\n".join(parts)}]
