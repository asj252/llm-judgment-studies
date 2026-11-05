# Copied verbatim from ../../dnli/prompts.py on 2026-10-26.
import re

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

_TERMINAL = re.compile(r"[.!?][\"'”’)]*$")

def terminate(s):
    s = s.strip()
    return s if _TERMINAL.search(s) else s + "."
