"""Regression test for catalogue lines that start with a coach-builder service
number (Winnebago_Catalog.pdf, 241 pages, previously 0 parts extracted).

Fixture: word positions captured by the range reader from page 40 (three
columns, "(A)" callouts, wrapped descriptions, marketing copy in between).
"""
import json, os, sys, unittest
HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
sys.path.insert(0, HERE)
import rv_master_disk as worker
from test_suburban_kit_rows import page_from_fixture


def load(name, page):
    with open(os.path.join(HERE, "fixtures", name)) as f:
        return page_from_fixture(json.load(f)[page])


class WinnebagoLeadingNumbers(unittest.TestCase):
    def rows(self):
        doc, page = load("winnebago_catalog_p40_positions.json", "40")
        try:
            return {r["number"]: r for r in worker.leading_number_rows(page, 40)}
        finally:
            doc.close()

    def test_all_part_lines_across_three_columns(self):
        rows = self.rows()
        self.assertEqual(len(rows), 27)
        self.assertEqual(rows["133790-02-02B"]["description"], 'Strap-Tiedown/TV, 25.3"')
        self.assertEqual(rows["143676-01-02B"]["description"], "Bracket Asm.-VCP")
        self.assertEqual(rows["136932-01-701"]["description"], "Remote")

    def test_short_wrapped_continuation_is_joined(self):
        rows = self.rows()
        self.assertEqual(rows["142258-01-000"]["description"], "Switch-Video/Antenna Power Supply")
        self.assertEqual(rows["086757-04-000"]["description"], "Video Control Center, VCR/TV, 5 Inputs")

    def test_spec_lines_and_cross_references_are_not_names(self):
        rows = self.rows()
        self.assertEqual(rows["156689-01-000"]["description"], "RCA DT902 AV Switch/Audio/Video")
        self.assertNotIn("127517-06-000", rows)   # "*Compatible w/... 127517-06-000 only."

    def test_provenance_label(self):
        for r in self.rows().values():
            self.assertEqual(r["method"], "leading-number-v1")
            self.assertRegex(r["position"], r"^x\d+ y\d+ col\d+$")

    def test_other_layouts_unaffected(self):
        for name, pg in (("lippert_catalog_2023_p40_p41_positions.json", "41"),
                         ("suburban_205624_revG_p2_p3_positions.json", "2"),
                         ("thetford_n3000_spl_p9_positions.json", "9")):
            doc, page = load(name, pg)
            try:
                self.assertEqual(worker.leading_number_rows(page, int(pg)), [])
            finally:
                doc.close()


if __name__ == "__main__":
    unittest.main()
