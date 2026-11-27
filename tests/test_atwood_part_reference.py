"""Atwood furnace replacement part reference reader: regression test from real page positions.

Fixture: Atwood 2007 RV Appliance Service and Parts Manual (split pp 094-186, supplied in Larry's Drive,
27 Nov 2026), split pages 35 and 38 (furnace part reference) and 50 (A-frame coupler page, a different
layout that must not be read).
"""
import json, os, sys, unittest

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "scripts", "aftermarket_pdf"))
import atwood_part_reference as a

FIX = json.load(open(os.path.join(HERE, "fixtures", "atwood_2007_furnace_ref_p35_p38_p50_positions.json")))


class AtwoodPartReferenceTest(unittest.TestCase):
    def setUp(self):
        self.rows, self.held = a.read([(p["text"], [tuple(w) for w in p["words"]]) for p in FIX["pages"]])
        self.by = {}
        for pg, _, num, desc, head in self.rows:
            self.by.setdefault(num, (pg, desc, head))

    def test_page_one_all_rows_agree_with_headings(self):
        p1 = [r for r in self.rows if r[0] == 1]
        self.assertEqual(len(p1), 39)
        self.assertFalse([h for h in self.held if h["page"] == 1])
        self.assertEqual(self.by["31257"], (1, "#56 16,000 BTU", "Burner Orifices"))
        self.assertEqual(self.by["37605"][2], "Blowers Wheels & Covers")

    def test_legend_glyphs_become_words(self):
        self.assertEqual(self.by["37607"][1], "Blower Venturi Ring (NOT REQUIRED) (NLA - no longer available)")
        self.assertEqual(self.by["38224"][1], "Ignition Module with Motor Control (while supplies last)")

    def test_rows_where_passes_differ_are_held_not_loaded(self):
        held_a = {tuple(h["a"]) for h in self.held if "a" in h}
        self.assertIn(("35881", "Blower Wheel STEEL"), held_a)
        self.assertNotIn("35881", self.by)

    def test_other_layout_page_not_read(self):
        self.assertFalse([r for r in self.rows if r[0] == 3])


if __name__ == "__main__":
    unittest.main()
