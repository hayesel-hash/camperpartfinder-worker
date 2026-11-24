"""Regression test for catalogue tables headed "Part #" (Lippert 2023 catalogue).

Fixture: word positions captured by the range reader from pages 40-41 of
Lippert_Catalog_AM.pdf (221 pages, previously 0 of these numbers extracted).
"""
import json, os, sys, unittest
HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
sys.path.insert(0, HERE)
import rv_master_disk as worker
from test_suburban_kit_rows import page_from_fixture


def load(name):
    with open(os.path.join(HERE, "fixtures", name)) as f:
        return json.load(f)


class PartHashTables(unittest.TestCase):
    def rows(self, n):
        doc, page = page_from_fixture(load("lippert_catalog_2023_p40_p41_positions.json")[str(n)])
        try:
            return {r["number"]: r for r in worker.part_hash_table_rows(page, n)}
        finally:
            doc.close()

    def test_two_tables_on_one_page_each_take_their_own_heading(self):
        rows = self.rows(40)
        self.assertEqual(set(rows), {"358590", "675817", "358601"})
        self.assertEqual(rows["358590"]["description"],
                         "GROUND CONTROL 3.0 AUTOMATIC 5TH WHEEL LEVELING SYSTEM (Four-point, 15,500 lbs.)")
        self.assertEqual(rows["358601"]["description"],
                         "GROUND CONTROL 3.0 REPLACEMENT REMOTE & CHARGER (Remote and charger)")

    def test_photo_callout_numbers_are_not_rows(self):
        # 358590/675817/358601 are also printed as loose photo labels.
        positions = [r["position"] for r in self.rows(40).values()]
        self.assertTrue(all(p.startswith("x67 ") for p in positions), positions)

    def test_row_attributes_disambiguate_variants(self):
        rows = self.rows(41)
        self.assertEqual(len(rows), 6)
        self.assertIn("Basic Ready Chassis Kit", rows["294717"]["description"])
        self.assertIn("Complete Ready Chassis Kit", rows["645281"]["description"])
        for r in rows.values():
            self.assertEqual(r["method"], "labelled-column-v1")
            self.assertRegex(r["position"], r"^x\d+ y\d+ col\d+$")

    def test_no_rows_without_a_part_header(self):
        fx = load("suburban_205624_revG_p2_p3_positions.json")
        doc, page = page_from_fixture(fx["2"])
        try:
            self.assertEqual(worker.part_hash_table_rows(page, 2), [])
        finally:
            doc.close()

    def test_adaptive_page_publishes_named_rows(self):
        doc, page = page_from_fixture(load("lippert_catalog_2023_p40_p41_positions.json")["41"])
        try:
            rows, metrics = worker.adaptive_page(page, 41, "adaptive-table-v3", {}, "manufacturer")
        finally:
            doc.close()
        self.assertEqual(metrics["unique"], 6)
        self.assertTrue(all(r["description"].startswith("LEVEL UP HYDRAULIC") for r in rows))



class SideBySidePartTables(unittest.TestCase):
    def test_each_table_stops_at_the_next_part_column_group(self):
        import pymupdf
        doc = pymupdf.open(); page = doc.new_page(width=612, height=792)
        items = [("SUPER SLIDE II TRIM KITS", 40, 100), ("Part #", 40, 140), ("Width", 100, 140),
                 ("Part #", 300, 140), ("Width", 360, 140),
                 ("370676", 40, 155), ('24"', 100, 155), ("370682", 300, 155), ('32"', 360, 155),
                 ("370680", 40, 170), ('28"', 100, 170), ("370692", 300, 170), ('36"', 360, 170)]
        for t, x, y in items:
            page.insert_text((x, y), t, fontsize=8)
        rows = {r["number"]: r["description"] for r in worker.part_hash_table_rows(page, 1)}
        doc.close()
        self.assertEqual(rows["370676"], 'SUPER SLIDE II TRIM KITS (24")')
        self.assertEqual(rows["370682"], 'SUPER SLIDE II TRIM KITS (32")')
        self.assertEqual(set(rows), {"370676", "370680", "370682", "370692"})



class AdjacentProductHeadings(unittest.TestCase):
    def test_neighbouring_product_headings_are_not_merged(self):
        import pymupdf
        doc = pymupdf.open(); page = doc.new_page(width=612, height=792)
        for t, x, y in [("8011 ACRYLIC ADHESIVE", 40, 100), ("8019 BONDING ADHESIVE", 160, 100),
                        ("Part #", 40, 140), ("Size", 90, 140), ("Part #", 160, 140), ("Size", 210, 140),
                        ("2020002238", 40, 155), ("1 Gallon", 90, 155), ("2020002240", 160, 155), ("5 Gallon", 210, 155)]:
            page.insert_text((x, y), t, fontsize=8)
        rows = {r["number"]: r["description"] for r in worker.part_hash_table_rows(page, 1)}
        doc.close()
        self.assertEqual(rows["2020002238"], "8011 ACRYLIC ADHESIVE (1 Gallon)")
        self.assertEqual(rows["2020002240"], "8019 BONDING ADHESIVE (5 Gallon)")


if __name__ == "__main__":
    unittest.main()
