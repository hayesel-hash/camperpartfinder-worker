"""Suburban literature readers: regression tests from real page text, word boxes and ruled lines.

Fixtures (Larry's Drive, 27 Nov 2026): SFV-35Q/42Q furnace replacement parts 205877XP page 3 (two ruled tables side by
side, description-first layout, item cells spanning two numbers), furnace core replacement cross reference LS122221
(model -> core stock no. -> distributor no., two rows without a distributor number).
"""
import json, os, sys, unittest
import pymupdf

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "scripts", "aftermarket_pdf"))
import suburban_parts_table as t
import suburban_catalogue as c


class FakePage:
    def __init__(self, p):
        self.text, self.words = p["text"], [tuple(w) for w in p["words"]]
        self.dr = [{"fill": None, "items": [("l", pymupdf.Point(i[1]), pymupdf.Point(i[2])) if i[0] == "l" else ("re", pymupdf.Rect(i[1]))
                                            for i in g["items"]]} for g in p["drawings"]]

    def get_text(self, kind="text"):
        return self.words if kind == "words" else self.text

    def get_drawings(self):
        return self.dr


P = {p["doc"]: FakePage(p) for p in json.load(open(os.path.join(HERE, "fixtures", "suburban_literature_pages.json")))["pages"]}


class SuburbanLiteratureTest(unittest.TestCase):
    def test_sfv_two_tables(self):
        a, b = t.pass_a(P["SFV"]), t.pass_b(P["SFV"])
        self.assertEqual(sorted(a), sorted(b))
        by = dict(b)
        self.assertEqual(len(by), 51)
        self.assertEqual(by["063581"], "Plate, Discharge Cover SFV-35/42Q, 35/42FQ ONLY (Accessory)")
        self.assertEqual(by["121857"], "Screw #8-18 x ½ (5 Required)")      # right-hand table
        self.assertEqual(by["062935"], "Plate, Secondary Air (Bottom) (for SFV-42Q and SFV-42FQ only)")

    def test_core_cross_reference(self):
        a, b = c.core_rows(P["CoreXref"])
        self.assertEqual(sorted(a), sorted(b))
        self.assertEqual(len(a), 30)
        self.assertIn(("SF-20", "2605A"), a)          # no distributor number printed on this row
        self.assertIn(("P-40", "2615A"), a)


if __name__ == "__main__":
    unittest.main()
