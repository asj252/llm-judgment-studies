# Copied unchanged from ../dnli/test_prompts.py for agy regression.
"""prompts.py 的测试（PLAN v0.2 第 3 节提示框架；c 第一轮阻断 4、建议 12；任务书第 2、3 步）。用法：python -I -X utf8 -B test_prompts.py"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import prompts as P  # noqa: E402

ITEM = {"P": "Two dogs play in the snow", "H": "The dogs are outside.", "U_S": "The dogs are wearing coats.",
        "U_W": "The snow is on a TV screen they are watching"}


class Terminal(unittest.TestCase):
    def test_rules(self):
        self.assertEqual(P.terminate("A man runs"), "A man runs.")
        self.assertEqual(P.terminate("A man runs."), "A man runs.")
        self.assertEqual(P.terminate("  A man runs.  "), "A man runs.")
        self.assertEqual(P.terminate("The team is winning!"), "The team is winning!")
        self.assertEqual(P.terminate("He asks 'Is it raining?'"), "He asks 'Is it raining?'")
        self.assertEqual(P.terminate('It says "Proud to be here."'), 'It says "Proud to be here."')
        self.assertEqual(P.terminate("The shirts say “Walking Club”"), "The shirts say “Walking Club”.")
        self.assertEqual(P.terminate("It is warm (very)"), "It is warm (very).")


class LowerInitial(unittest.TestCase):
    def check(self, u, out, rule):
        self.assertEqual(P.lower_initial(u), (out, rule))

    def test_rules(self):
        self.check("The man is tall.", "the man is tall.", "6_lowered")
        self.check("There's a dog.", "there's a dog.", "6_lowered")
        self.check("Nearby, a dog barks.", "nearby, a dog barks.", "6_lowered")
        self.check("High-stakes poker.", "high-stakes poker.", "6_lowered")
        self.check("the man is tall.", "the man is tall.", "2_already_lower")
        self.check('"Pop Goes the Weasel" is playing.', '"Pop Goes the Weasel" is playing.', "1_starts_non_letter")
        self.check("I think so.", "I think so.", "3_pronoun_I")
        self.check("I'm here.", "I'm here.", "3_pronoun_I")
        self.check("It's raining.", "it's raining.", "6_lowered")
        self.check("NASA staff watch.", "NASA staff watch.", "4_internal_capital")
        self.check("McDonald's is nearby.", "McDonald's is nearby.", "4_internal_capital")
        self.check("Batman is riding the vehicle", "Batman is riding the vehicle", "5_proper_initial")
        self.check("Christmas lights are on", "Christmas lights are on", "5_proper_initial")
        self.check("Mom's car is red.", "Mom's car is red.", "5_proper_initial")
        self.check("Sally Field is here.", "Sally Field is here.", "5_proper_initial")
        self.check("Gone With the Wind is on.", "Gone With the Wind is on.", "5_proper_initial")
        self.check("Tourist entertain themselves.", "tourist entertain themselves.", "6_lowered")

    def test_frozen_list(self):
        self.assertEqual(P.PROPER_INITIAL, ("Batman", "Christmas", "Sally", "Gone", "Mom"))


class Frames(unittest.TestCase):
    def test_prior(self):
        p = P.render_item(ITEM, "prior", "-", "direct")
        self.assertEqual(p.split("\n\n")[0], "Here is a situation: Two dogs play in the snow.")
        self.assertNotIn("learned", p)
        self.assertNotIn("Someone said", p)
        self.assertIn("Using common sense, how likely is it that the following statement is true?\n"
                      "Statement: The dogs are outside.", p)
        self.assertTrue(p.endswith("Do not use any tools; answer directly."))

    def test_stated_and_reported_differ_only_in_update_line(self):
        s = P.render_item(ITEM, "stated", "W", "direct")
        r = P.render_item(ITEM, "reported", "W", "direct")
        ls, lr = s.split("\n"), r.split("\n")
        self.assertEqual(len(ls), len(lr))
        diff = [(a, b) for a, b in zip(ls, lr) if a != b]
        self.assertEqual(diff, [("Here is something else you learned: The snow is on a TV screen they are watching.",
                                 "Someone said that the snow is on a TV screen they are watching.")])
        self.assertNotIn("not sure", r)                         # c 第一轮阻断 4：不加明说的不确定
        p0 = P.render_item(ITEM, "prior", "-", "direct")
        self.assertEqual([l for l in ls if not l.startswith("Here is something else")], p0.split("\n"))

    def test_asks(self):
        d = P.render_item(ITEM, "stated", "S", "direct")
        m = P.render_item(ITEM, "stated", "S", "multi")
        self.assertIn("What is the probability that the statement is true?", d)
        self.assertIn("Probability: NN%", d)
        self.assertNotIn("Estimate", d)
        self.assertIn("Give 5 probability estimates that the statement is true, each with a weight for how likely you "
                      "think that estimate is; the weights sum to 1.", m)
        self.assertNotIn("different", m)                        # c 第一轮阻断 1：不要求 different
        self.assertNotIn("Probability:", m)
        self.assertEqual(d.split("\n\n")[:2], m.split("\n\n")[:2])

    def test_no_forbidden_instructions(self):
        for pres, ut in (("prior", "-"), ("stated", "S"), ("reported", "W")):
            for ask in P.ASKS:
                p = P.render_item(ITEM, pres, ut, ask).lower()
                self.assertNotIn("absolutely true", p)          # c 第一轮建议 12：不用「前提绝对为真」
                self.assertNotIn("strengthen", p)
                self.assertNotIn("weaken", p)

    def test_errors(self):
        with self.assertRaises(ValueError):
            P.render_item(ITEM, "prior", "S", "direct")
        with self.assertRaises(ValueError):
            P.render_item(ITEM, "stated", "-", "direct")
        with self.assertRaises(ValueError):
            P.render("stated", "direct", "p", "h")
        with self.assertRaises(ValueError):
            P.render("prior", "vs", "p", "h")


if __name__ == "__main__":
    unittest.main()
