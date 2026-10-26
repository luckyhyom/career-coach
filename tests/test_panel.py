import unittest

from coach.panel import aggregate


def member(band, vec, verdict, kill_axis, before, scores=None):
    return {"band": band, "label": band, "seats": 10, "vec": vec, "stack_position": {"agnostic": 10},
            "result": {"verdict": verdict, "kill_axis": kill_axis, "kill_reason": "r", "kill_quote": "",
                       "scores": scores or {}, "interview_q": [{"q": "q", "topic": "t"}],
                       "one_fix": {"before": before, "after": "a"}}}


class PanelAggregateTests(unittest.TestCase):
    def test_shared_axes_do_not_collapse_distinct_personas(self):
        # raw cosine is ~0.97 for both pairs; only the deviation from the mean differs
        a = member("a", {"x": 10, "y": 10, "z": 1}, "HOLD", "z", "line one")
        b = member("b", {"x": 10, "y": 10, "z": 3}, "HOLD", "z", "- line one")
        agg = aggregate([a, b])
        self.assertEqual(len(agg["independence_groups"]), 2)
        self.assertTrue(agg["points"][0]["act"])
        self.assertEqual(agg["fix_consensus"][0]["votes"], 2)  # bullet prefix ignored

    def test_identical_personas_count_once(self):
        a = member("a", {"x": 10, "y": 1}, "HOLD", "x", "l")
        b = member("b", {"x": 10, "y": 1}, "HOLD", "x", "l")
        c = member("c", {"x": 1, "y": 10}, "REJECT", "y", "m")
        agg = aggregate([a, b, c])
        x = next(p for p in agg["points"] if p["axis"] == "x")
        self.assertEqual(x["votes"], 1)
        self.assertFalse(x["act"])
        self.assertEqual(agg["seats"], {"PASS": 0, "HOLD": 20, "REJECT": 10})

    def test_promotion_without_kill_votes(self):
        ps = [member(b, {"x": i + 1, "y": 5 - i}, "HOLD", "x", "l", {"y": 2}) for i, b in enumerate("abc")]
        y = next(p for p in aggregate(ps)["points"] if p["axis"] == "y")
        self.assertTrue(y.get("promoted") and y["act"])


if __name__ == "__main__":
    unittest.main()
