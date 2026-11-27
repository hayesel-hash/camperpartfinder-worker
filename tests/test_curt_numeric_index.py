"""CURT "All products listed numerically" reader: regression test from real page positions.

Fixture: CURT 2024 Catalog & Application Guides, Drive split pp 264-307 (27 Nov 2026), split page 21
(trailer hitches listed numerically by vehicle: fitment, must be skipped) and split page 32 (four columns
of Part # | Description | MP | IP, with cells the text layer glues together).
"""
import json, os, sys, unittest

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "scripts", "aftermarket_pdf"))
import curt_numeric_index as c

FIX = json.load(open(os.path.join(HERE, "fixtures", "curt_2024_numeric_p21_p32_positions.json")))


class CurtNumericIndexTest(unittest.TestCase):
    def setUp(self):
        self.rows, self.held = c.read([(p["text"], [tuple(w) for w in p["words"]]) for p in FIX["pages"]])
        self.by = {num: (pg, desc) for pg, _, num, desc in self.rows}

    def test_fitment_page_skipped_and_passes_agree(self):
        self.assertEqual({pg for pg, _, _, _ in self.rows}, {2})
        self.assertEqual(self.held, [])
        self.assertEqual(len(self.rows), 291)

    def test_glued_cells_split(self):
        self.assertEqual(self.by["20002"][1], "MIRROR")  # "20002 MIRROR" on one text line
        self.assertEqual(self.by["21300"][1], "REDUCER BUSHING 1 3")  # followed by "300 0" (MP IP glued)
        self.assertEqual(self.by["28964"][1], "PART,JACK FULL 7K B")

    def test_description_starting_with_a_number_is_not_a_part(self):
        self.assertEqual(self.by["19251"][1], "60691 REPL PIN & LY")
        self.assertNotIn("60691", self.by)


if __name__ == "__main__":
    unittest.main()
