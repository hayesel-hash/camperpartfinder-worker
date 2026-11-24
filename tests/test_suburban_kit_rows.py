"""Regression test for the Suburban master parts manual (205624 Rev G, 2026).

The fixture holds word positions (PDF points, origin bottom-left) captured by the
serverless range reader from pages 2-3 of the official manual. The 2026 layout
prints the KIT NO. heading on two stacked lines, which the previous adapter did
not recognise (1 part extracted from 27 pages).
"""
import json, os, sys, unittest
HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
import pymupdf
import rv_master_disk as worker


def page_from_fixture(items):
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    for text, x, y in items:
        page.insert_text((x, 792 - y), text, fontsize=7)
    return doc, page


class SuburbanStackedKitHeader(unittest.TestCase):
    def setUp(self):
        with open(os.path.join(HERE, "fixtures", "suburban_205624_revG_p2_p3_positions.json")) as f:
            self.fx = json.load(f)

    def rows(self, n):
        doc, page = page_from_fixture(self.fx[str(n)])
        try:
            return worker.suburban_kit_rows(page, n)
        finally:
            doc.close()

    def test_page2_every_kit_number_in_kit_column(self):
        rows = self.rows(2)
        self.assertEqual({r["number"] for r in rows}, {
            "520832", "520839", "520840", "521099", "232806", "520947", "230849", "525020",
            "230496", "231227", "233484", "232503", "231630", "525006", "525035", "233522",
            "232505", "525052", "232735", "231807", "231768", "230825"})

    def test_inline_order_number_is_not_a_kit_row(self):
        # "ORDER 521099 MODULE BOARD SEPARATELY" sits in the description column.
        rows = [r for r in self.rows(2) if r["number"] == "521099"]
        self.assertTrue(all(r["description"] != "FAN CONTROL MODULE BOARD WIRING KIT TO CONVERT NON-FAN CONTROL MODULE BOARD FURNACE" for r in rows))

    def test_component_heading_names_the_part_not_model_codes(self):
        names = {r["number"]: r["description"] for r in self.rows(2)}
        self.assertEqual(names["230849"], "LIMIT SWITCH")
        self.assertEqual(names["525006"], "LIMIT SWITCH")
        names3 = {r["number"]: r["description"] for r in self.rows(3)}
        self.assertEqual(names3["525028"], "SAIL SWITCH")
        self.assertEqual(names3["520837"], "MOTOR CAPACITOR 7.5 UF")
        self.assertEqual(names3["521099"], "TIME DELAY RELAY AND NON-FAN CONTROL MODULE BOARD CONVERSION KITS")

    def test_illustration_column_text_is_ignored(self):
        self.assertFalse(any("PICTURE" in r["description"] for r in self.rows(3)))

    def test_rows_use_publishable_labelled_column_position(self):
        for r in self.rows(3):
            self.assertEqual(r["method"], "labelled-column-v1")
            self.assertRegex(r["position"], r" col\d+$")



class SuburbanAdaptivePagePrecedence(unittest.TestCase):
    def test_kit_rows_win_in_production_traversal(self):
        with open(os.path.join(HERE, "fixtures", "suburban_205624_revG_p2_p3_positions.json")) as f:
            fx = json.load(f)
        doc, page = page_from_fixture(fx["3"])
        try:
            rows, metrics = worker.adaptive_page(page, 3, "suburban-kit-v2", {}, "manufacturer")
        finally:
            doc.close()
        names = {r["number"]: r["description"] for r in rows}
        self.assertEqual(metrics["unique"], 14)
        self.assertEqual(names["233355"], "SAIL SWITCH")


if __name__ == "__main__":
    unittest.main()
