"""Regression test for Thetford absorption-refrigerator spare-part lists.

Fixture: word positions captured by the range reader from page 9 of
SPL-Absorption-Refrigerator-N3000-3.pdf (N3100 front). The list has up to three
stacked "Spare part / number" columns; some numbers are printed between rows
(merged cells) and must be skipped rather than guessed.
"""
import json, os, sys, unittest
HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
sys.path.insert(0, HERE)
import rv_master_disk as worker
from test_suburban_kit_rows import page_from_fixture


class ThetfordSparePartLists(unittest.TestCase):
    def rows(self):
        with open(os.path.join(HERE, "fixtures", "thetford_n3000_spl_p9_positions.json")) as f:
            fx = json.load(f)
        doc, page = page_from_fixture(fx["9"])
        try:
            return {r["number"]: r for r in worker.spare_part_number_rows(page, 9)}
        finally:
            doc.close()

    def test_aligned_rows_named_by_their_description(self):
        rows = self.rows()
        self.assertEqual(rows["626986"]["description"], "Storage strap (2x)")
        self.assertEqual(rows["624479"]["description"], "Cap freezer bolt (6x)")
        self.assertEqual(rows["69154027R"]["description"], "Cabinet door (production date > July 2016)")
        self.assertEqual(rows["69157127SP"]["description"], "Door panel (production date > July 2016)")

    def test_item_number_bracketed_by_two_description_lines(self):
        self.assertEqual(self.rows()["693141"]["description"], "Hinge kit (hinges #6, 22) Hinge pins + screws")

    def test_numbers_between_rows_are_skipped_not_guessed(self):
        rows = self.rows()
        for ambiguous in ("626985", "691468", "690852", "623077"):
            self.assertNotIn(ambiguous, rows)

    def test_colour_codes_and_page_refs_are_not_parts(self):
        rows = self.rows()
        self.assertEqual(len(rows), 17)
        self.assertFalse(any(len(n) < 6 for n in rows))
        for r in rows.values():
            self.assertNotRegex(r["description"], r"^\d")
            self.assertEqual(r["method"], "labelled-column-v1")

    def test_no_rows_without_spare_part_header(self):
        with open(os.path.join(HERE, "fixtures", "lippert_catalog_2023_p40_p41_positions.json")) as f:
            fx = json.load(f)
        doc, page = page_from_fixture(fx["41"])
        try:
            self.assertEqual(worker.spare_part_number_rows(page, 41), [])
        finally:
            doc.close()



class SplitSpareHeader(unittest.TestCase):
    def test_kerned_s_pare_part_header(self):
        import pymupdf
        doc = pymupdf.open(); page = doc.new_page()
        for t, x, y in [("S", 261, 50), ("pare", 268, 50), ("part", 292, 50), ("number", 266, 63),
                        ("2", 62, 85), ("Storage strap (2x)", 89, 85), ("626986", 268, 85), ("27", 500, 85)]:
            page.insert_text((x, y), t, fontsize=9)
        rows = worker.spare_part_number_rows(page, 1)
        doc.close()
        self.assertEqual([(r["number"], r["description"]) for r in rows], [("626986", "Storage strap (2x)")])



class QualifierLines(unittest.TestCase):
    def test_production_date_line_takes_the_item_name_above(self):
        import pymupdf
        doc = pymupdf.open(); page = doc.new_page()
        for t, x, y in [("Spare part", 261, 50), ("number", 266, 63), ("Spare part", 340, 50), ("number", 345, 63),
                        ("27", 62, 85), ("Framed cabinet door", 89, 85),
                        ("Production date > July 2016", 89, 98), ("63500127R", 340, 98)]:
            page.insert_text((x, y), t, fontsize=9)
        rows = {r["number"]: r["description"] for r in worker.spare_part_number_rows(page, 1)}
        doc.close()
        self.assertEqual(rows["63500127R"], "Framed cabinet door (Production date > July 2016)")


if __name__ == "__main__":
    unittest.main()
