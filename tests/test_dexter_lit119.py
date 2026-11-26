"""Dexter LIT-119-00 parts kit catalogue reader: regression test from real page positions.

The fixture holds the text blocks and upright word boxes of PDF pages 37 and 43 of split part 1
(pp 001-067) of the LIT-119-00 copy supplied in Larry's Drive (26 Nov 2026), plus the words of the
rotated section label on page 43 ("CALIPER REPLACEMENT & REPAIR KITS") and that label's box.
Page 37: a kit title printed on two lines with the number on the first baseline (K71-685-00) and a
manual (LIT-608-00) listed as a kit row. Page 43: an "Instruction Sheet" row in the middle of a table.
"""
import json, os, sys, unittest

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "scripts", "aftermarket_pdf"))
import dexter_lit119 as r

FIX = json.load(open(os.path.join(HERE, "fixtures", "dexter_lit119_p37_p43_positions.json")))


def pages():
    return [([tuple(x) for x in p["blines"]], [tuple(x) for x in p["words"]]) for p in FIX["pages"]]


class DexterLit119Test(unittest.TestCase):
    def test_passes_agree(self):
        rows, diffs = r.read(pages())
        self.assertEqual(diffs, [])
        self.assertEqual(len(rows), 31)

    def test_two_line_title_reads_the_same_both_ways(self):
        rows, _ = r.read(pages())
        got = {num: desc for _, _, num, desc in rows}
        self.assertEqual(got["K71-685-00"],
                         "Electric/Hydraulic Brake Actuator Fill Cap & Gasket Fits Dexter 1000 & 1600 E/H brake actuator.")
        self.assertEqual(got["097-011-01"], "Reservoir Cap Assembly, E/H Brake Actuator")

    def test_literature_rows_are_skipped_but_table_continues(self):
        rows, _ = r.read(pages())
        nums = [num for _, _, num, _ in rows]
        self.assertNotIn("LIT-608-00", nums)
        self.assertNotIn("059-799-00", nums)          # Instruction Sheet
        self.assertIn("071-650-00", nums)
        self.assertIn("089-003-02", nums)             # row after the Instruction Sheet row
        got = {num: desc for _, _, num, desc in rows}
        self.assertEqual(got["089-003-02"], "Caliper Assembly, 8K")
        self.assertEqual(got["K71-630-00"], "Caliper Replacement Kit - LH or RH Fits Dexter 8K disc brakes.")

    def test_rotated_label_words_are_dropped(self):
        boxes = FIX["rotated_boxes_p43"]
        self.assertTrue(FIX["rotated_label_words_p43"])
        self.assertFalse(any(r.upright(w, boxes) for w in FIX["rotated_label_words_p43"]))

    def test_numbers_inside_descriptions_are_not_identities(self):
        blines = [(0, "Breakaway Kit"), (0, "034-285-00"),
                  (1, "Fits E/H brake actuator K71-650-00 and K71-651-00.")]
        self.assertEqual(r.pass_a(blines), [])


if __name__ == "__main__":
    unittest.main()
