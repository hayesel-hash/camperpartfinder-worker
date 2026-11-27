"""Regression test for dometic_coolfreeze_parts_list.py from real page text and word boxes of the Dometic LLC (Waeco)
CoolFreeze CF parts list form 3312482.023 (Larry's Drive, 27 Nov 2026): page 3 (one model, serial ranges with the
"*" WAECO footnote) and page 7 (two-model legend, A / B / -- marks, "(same p/n as above)" rows adding the other
model's serial ranges, "**" picture marks on numbers)."""
import json, os, sys, unittest

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "scripts", "aftermarket_pdf"))
import dometic_coolfreeze_parts_list as cf


class FakePage:
    def __init__(self, p):
        self.text, self.words = p["text"], [tuple(w) for w in p["words"]]

    def get_text(self, kind="text"):
        return self.words if kind == "words" else self.text


def pages():
    return [FakePage(p) for p in json.load(open(os.path.join(HERE, "fixtures", "coolfreeze_3312482_p3_p7_positions.json")))["pages"]]


class CoolFreezeTest(unittest.TestCase):
    def test_passes_agree(self):
        for p in pages():
            leg = cf.page_models(p)
            self.assertTrue(leg)
            self.assertEqual(cf.pass_a(p, leg), cf.pass_b(p, leg))

    def test_rows(self):
        p3, p7 = pages()
        a3 = dict(cf.pass_a(p3, cf.page_models(p3)))
        self.assertEqual(len(a3), 9)
        self.assertEqual(a3["SP022MAINPCBASF"], "MAIN PCB, CF-18 [fits serial numbers: 05000241-05000300 (WAECO branded units), "
                                                "MB81500001-MB91200045 & higher]")
        leg7 = cf.page_models(p7)
        self.assertEqual(leg7, {"A": "CF-035AC110", "B": "CF-040AC110"})
        a7 = dict(cf.pass_a(p7, leg7))
        self.assertEqual(a7["46-026-05TSW"], "BASKET, CF-35 [models: CF-035AC110]")
        self.assertIn("CF-040AC110: MB92800001-MB95100030, MB01100001-MB01500040 & higher", a7["SP026DISPCBASB"])
        self.assertNotIn("[models:", a7["SP026DISPCBASB"])
        self.assertIn("SP005MAINPCBASA", a7)  # "**" picture mark stripped


if __name__ == "__main__":
    unittest.main()
