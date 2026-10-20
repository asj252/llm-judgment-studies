import unittest
import reparse

class Offline(unittest.TestCase):
    def test_v1_v2_and_truncation(self):
        r = reparse.parse_attempt("direct","### Probability:\nProbability: 20%")
        self.assertFalse(r["v1"]["ok"])
        self.assertTrue(r["v2"]["ok"])
        r = reparse.parse_attempt("multi","\n".join("Estimate %d: 20%% | Weight: .14" % i for i in range(1,6)))
        self.assertFalse(r["v1"]["ok"])
        self.assertTrue(r["v2"]["ok"])
        self.assertFalse(r["v2"]["weight_sum_in_tolerance"])
        r = reparse.parse_attempt("direct","Probability: 20%",True)
        self.assertEqual(r["v2"]["error"],"truncated")
