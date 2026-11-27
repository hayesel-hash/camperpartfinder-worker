"""Camco OEM catalogue reader: regression test from real page positions.

Fixture: Camco "Quality Parts for RV Manufacturing / OEM Products 2023", Drive split pp 001-013, pages 3
(two side-by-side tables with the heading under the header row), 4 (water: stacked tables, two-line
headers) and 10 (cargo vents, return-air vents, battery boxes), supplied in Larry's Drive (27 Nov 2026).
"""
import json, os, sys, unittest

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "scripts", "aftermarket_pdf"))
import camco_oem as c

FIX = json.load(open(os.path.join(HERE, "fixtures", "camco_oem_2023_p3_p4_p10_positions.json")))


class CamcoOemTest(unittest.TestCase):
    def setUp(self):
        self.rows, self.held = c.read([(p["text"], p["lines"], p["width"]) for p in FIX["pages"]])
        self.by = {num: (pg, desc) for pg, _, num, desc, _ in self.rows}

    def test_side_by_side_tables_take_their_own_heading(self):
        self.assertEqual(self.by["42174"][1], "Standard Handle — black")
        self.assertEqual(self.by["42196"][1], "Short Handle — black")

    def test_heading_and_attributes_qty_dropped(self):
        self.assertEqual(self.by["22692"][1], "1/2\" High Pressure Hose for Hot & Cold Water — white / 500' / 150 psi")
        self.assertEqual(self.by["37281"][1], "Evacuation Flange with Cap — black / 2.5\" / .95\"")
        self.assertEqual(self.by["37080"][1], "Corrugated Gravity Fill Hose, 1-3/8\" diameter, 50 ft roll — 50'")
        self.assertEqual(len([r for r in self.rows if r[0] == 2]), 10)

    def test_prose_part_numbers_not_taken(self):
        # "Replacement hardware kit available, part number 42195" is prose on page 3, not a table row
        self.assertNotIn("42195", self.by)
        self.assertNotIn("42199", self.by)

    def test_integer_attribute_rows_are_held_not_guessed(self):
        # battery box GROUP SIZE "24" looks like a QTY to the text pass: the passes disagree -> held
        self.assertNotIn("55369", self.by)
        self.assertIn("55369", [h["number"] for h in self.held])
        self.assertEqual(self.by["42490"][1], "Furnace Return Air Vent — black / 23.5\" x 13.38\"")


if __name__ == "__main__":
    unittest.main()
