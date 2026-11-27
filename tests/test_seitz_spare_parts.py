"""Dometic Seitz DOK spare-parts sheet reader: regression test from real word boxes (pymupdf and pdfplumber) and ruled lines.

Fixtures (Larry's Drive, 27 Nov 2026): S5 window p1 (wrapped descriptions, placeholder codes "IRE05...", "FM80/82"),
S6 window p9 (BG1078 printed for both the right-hand and the left-hand handle), Midi Heki p6 ("BG 1517" with a space,
a row with no part number: "only as complete frame available").
"""
import json, os, sys, unittest
import pymupdf

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "scripts", "aftermarket_pdf"))
import seitz_spare_parts as s


class FakePage:
    def __init__(self, p):
        self.words = [tuple(w) for w in p["words"]]
        self.dr = [{"items": [("l", pymupdf.Point(i[1]), pymupdf.Point(i[2])) if i[0] == "l" else ("re", pymupdf.Rect(i[1]))
                              for i in g["items"]]} for g in p["drawings"]]

    def get_text(self, kind="words"):
        return self.words

    def get_drawings(self):
        return self.dr


RAW = {p["doc"]: p for p in json.load(open(os.path.join(HERE, "fixtures", "seitz_spare_parts_pages.json")))["pages"]}


def read(doc):
    p = FakePage(RAW[doc]); tabs = s.tables(p)
    a = s.rows_from_words([tuple(w) for w in RAW[doc]["plumber_words"]], tabs)
    b = s.rows_from_words(p.words, tabs)
    return a, b


class SeitzSparePartsTest(unittest.TestCase):
    def test_s5_wrapped_rows_and_placeholders(self):
        a, b = read("S5")
        self.assertEqual(a, b)
        by = {pn: d for item, pn, d in b}
        self.assertEqual(by["BG 1091"], "S5-window repair set (plastic bracket, plastic plate, end cap, central lock spring, lock, lock pin)")
        self.assertIn("IRE05...", by)
        for pn in ("IRE05...", "FM80/82", "BG 1047..."):
            self.assertIsNone(s.GOOD.match(s.PREFIX.sub(r"\1\2", pn)))
        self.assertEqual(s.PREFIX.sub(r"\1\2", "BG 1091"), "BG1091")

    def test_s6_same_number_two_rows(self):
        a, b = read("S6")
        self.assertEqual(a, b)
        self.assertEqual([d for i, pn, d in b if pn == "BG1078"],
                         ["Handle/98, right hand for top hung window (view from inside)", "Handle/98, left hand for top hung window (view from inside)"])

    def test_midi_heki_row_without_number(self):
        a, b = read("MidiHeki")
        self.assertEqual(a, b)
        by = {pn: d for i, pn, d in b}
        self.assertEqual(by["BG 1517"], "Exterior frame (without assembly parts)")
        self.assertTrue(any(i == "35" and not s.GOOD.match(pn) for i, pn, d in b))


if __name__ == "__main__":
    unittest.main()
