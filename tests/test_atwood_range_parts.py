"""Atwood range / cooktop Parts Identification reader: regression test from real page positions.

Fixture: Atwood Model 21 Oven & Slide-In Cooktop manual (effective 2.2.10, supplied in Larry's Drive,
27 Nov 2026): PDF page 8 (two-up spread: English parts table left, French text right) and page 3
(operating instructions with a stray "MPD 51042" mention, which must not be read).
"""
import json, os, sys, unittest

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "scripts", "aftermarket_pdf"))
import atwood_range_parts as a

FIX = json.load(open(os.path.join(HERE, "fixtures", "atwood_model21_range_p8_p3_positions.json")))


class AtwoodRangePartsTest(unittest.TestCase):
    def setUp(self):
        self.rows, self.held = a.read([(p["text"], [tuple(w) for w in p["words"]]) for p in FIX["pages"]])
        self.by = {r[2]: r for r in self.rows}

    def test_all_rows_agree(self):
        self.assertEqual(len(self.rows), 53)
        self.assertEqual(self.held, [])
        self.assertEqual({r[0] for r in self.rows}, {1})

    def test_model_columns_as_printed(self):
        self.assertEqual(self.by["52695"][3:], ("Kit, Manifold Pipe", "10", ["RA 1721", "RA 2121", "RV 1721", "RV 2121"]))
        self.assertEqual(self.by["52703"][5], ["CA 21", "CV 21"])
        self.assertEqual(self.by["51983"][5], ["RA 2121", "RV 2121"])
        self.assertEqual(self.by["52711"][5], ["RV 1721", "RV 2121", "CV 21"])

    def test_continuation_rows_keep_item_and_skip_placeholders(self):
        self.assertEqual(self.by["51358"][3:5], ("Range Top - stainless steel", "4"))
        self.assertEqual(self.by["52700"][4], "38B")
        self.assertNotIn("TBD", self.by)
        self.assertFalse([r for r in self.rows if "Control Panel" in r[3]])

    def test_other_pages_not_read(self):
        self.assertNotIn("51042", self.by)


if __name__ == "__main__":
    unittest.main()
