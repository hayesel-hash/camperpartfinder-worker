"""Coleman-Mach repair parts list reader: regression test from real page positions.

Fixture: Coleman-Mach (Airxcel) Mach 8 472X4*87X 15,000 BTU repair parts list R-607C (3-15), page 3,
supplied in Larry's Drive (27 Nov 2026): real text layer and word boxes.
"""
import json, os, sys, unittest

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "scripts", "aftermarket_pdf"))
import coleman_mach_rpl as c

FIX = json.load(open(os.path.join(HERE, "fixtures", "coleman_mach8_rpl_p3_positions.json")))


class ColemanMachRplTest(unittest.TestCase):
    def setUp(self):
        self.rows, self.diffs = c.read([(p["text"], [tuple(w) for w in p["words"]]) for p in FIX["pages"]])
        self.by = {num: (desc, used) for _, _, num, desc, used in self.rows}

    def test_passes_agree_on_every_row(self):
        self.assertEqual(self.diffs, [])
        self.assertEqual(len(self.rows), 30)

    def test_used_on_cells(self):
        self.assertEqual(self.by["47233-3261"], ("Shroud (Arctic White/Arctic White)", "876"))
        self.assertEqual(self.by["47233-3291"], ("Shroud (Black/Black)", "879"))
        # second number under item 9: used-on cell printed on its own line
        self.assertEqual(self.by["47233A3011"], ("Basepan", "47224/47234"))
        self.assertEqual(self.by["47233A2011"], ("Basepan", "47204/47214"))
        # "ns" (not shown) rows are read too
        self.assertEqual(self.by["7333A3011"], ("Charger Assembly", "47214/47234"))
        self.assertEqual(c.describe("Basepan", "47224/47234"), "Basepan - used on 47224/47234")
        self.assertEqual(c.describe("Overload", "All"), "Overload")

    def test_numbers_as_printed(self):
        self.assertEqual(self.by["1472D5041"][0], "Fan Blade")
        self.assertEqual(self.by["1450-4069"][0], "Compressor (Tecumseh - HG373AR-904-A2JI)")
        self.assertNotIn("HG373AR-904-A2JI", self.by)  # compressor model inside a description is not a part


if __name__ == "__main__":
    unittest.main()
