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


if __name__ == "__main__":
    unittest.main()
