"""Regression tests for the Webasto readers added by the 27 Nov 06:49 scheduled Drive intake, from real page words / dict
lines (Larry's Drive, 27 Nov 2026):
- webasto_catalogue.py: 2024/25 CV catalogue printed p27 (Air Top Evo 40/55 maintenance table, leader dots, voltage
  column) and printed p20 (one description cell holding two part numbers: both held, not loaded);
- webasto_spare_parts_list.py: Air Top Evo 40/55 spare parts list p6 (rotated version headers, glyph marks).
"""
import json, os, sys, unittest

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "scripts", "aftermarket_pdf"))
import webasto_catalogue as wc
import webasto_spare_parts_list as ws


class FakePage:
    def __init__(self, p):
        self.p = p

    def get_text(self, kind="text"):
        if kind == "words":
            return [tuple(w) for w in self.p["words"]]
        if kind == "dict":
            return self.p["dict"]
        return self.p.get("text", "")


def pages(name):
    return [FakePage(p) for p in json.load(open(os.path.join(HERE, "fixtures", name)))["pages"]]


class WebastoCatalogueTest(unittest.TestCase):
    def test_maintenance_table(self):
        p27, _ = pages("webasto_cv_catalogue_p27_p20_positions.json")
        a, b, seen = wc.read_page(p27)
        self.assertEqual(a, b)
        by = {r[0]: r for r in a}
        self.assertEqual(by["9027981B"][1:3], ("Air Top Evo 40 Diesel Base Heater", "24 V"))
        self.assertEqual(by["9029415A"][1:3], ("Air Top Evo 40/55 Diesel Burner Assembly w/out Glow Pin", "12 / 24 V"))
        # the heat-exchanger row's dash sits off the number's baseline in a tall photo row: held, not guessed
        self.assertEqual(by["9029416A"][1:3], ("", ""))
        self.assertEqual(sum(1 for r in a if r[1]), len(a) - 1)

    def test_two_numbers_in_one_cell_are_held(self):
        _, p20 = pages("webasto_cv_catalogue_p27_p20_positions.json")
        a, b, seen = wc.read_page(p20)
        self.assertEqual(a, b)
        by = {r[0]: r for r in a}
        self.assertEqual(by["5013931A"][1], "")
        self.assertEqual(by["5013932A"][1], "")
        self.assertEqual(by["5013873A"][1], "SmarTemp Control 3.0")


class WebastoSparePartsListTest(unittest.TestCase):
    def test_versions_and_marks(self):
        (p6,) = pages("webasto_evo_spare_parts_p6_positions.json")
        a, names_a = ws.pass_a(p6)
        b, names_b = ws.pass_b(p6)
        self.assertEqual(names_a, names_b)
        self.assertEqual(names_b[0], "40D 12V STD")
        bk = {r[1]: r for r in b}
        self.assertIn(("4", "9029390A", "Drive with fuel pump wiring harness", 3), a)
        self.assertEqual([names_b[i] for i in bk["9029390A"][4]], ["40D 12V STD", "40D 24V STD", "40B 12V STD"])
        self.assertEqual([names_b[i] for i in bk["9029414A"][4]], ["40B 12V STD", "55B 12V STD"])


if __name__ == "__main__":
    unittest.main()
