"""Tests for the two readers added by the 27 Nov 13:19 scheduled Drive intake (Grove Products prints, loaded under Larry's
27 Nov distributor-catalogue decision):
- thetford_grove_spares.py (Thetford_General_spares.pdf): bold Grove numbers dropped, variant words kept, numbers in cells
  that span several item rows (kits, production-date blocks) never assigned to one item;
- alko_grove_spares.py ("AL-KO Spare Parts"): AL-KO No. column only, wrapped descriptions held, numbered lines under a
  "Pos | heading" line held, qualifier-only descriptions held.
Word geometry is copied from the Drive copies (Thetford p6 N98 and p56 cassette tank, AL-KO p10 wheel brake)."""
import os, sys, unittest

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "scripts", "aftermarket_pdf"))
import thetford_grove_spares as tgs
import alko_grove_spares as ags


def W(x0, top, text, bold=False, h=10.5, w=None):
    w = w or 4.6 * len(text)
    return {"x0": x0, "top": top, "x1": x0 + w, "bottom": top + h, "text": text, "bold": bold}


def header(y=87):
    return [W(302, y, "No.", True), W(325, y, "Description", True), W(387, y, "Thetford"), W(414, y, "Part"),
            W(430, y, "No."), W(442, y, "Grove", True), W(470, y, "Part", True), W(490, y, "No.", True)]


def cells(*bands):
    """Filled table cells of the Thetford Part No. area: (top, bottom) bands, full width 389-538."""
    return [(389.3, t, 538.1, b) for t, b in bands]


class ThetfordGroveTest(unittest.TestCase):
    def test_single_row_cells_variants_and_spanning_cells(self):
        ws = header() + [
            W(40, 60, "N98", h=20),
            # A1 Latch V3 / A2 Latch strap: right-hand cell over both rows (kit) -> unread; A2 left cell -> row
            W(302, 97, "A1", True), W(325, 97, "Latch"), W(350, 97, "V3"), W(465, 98, "Black"), W(490, 98, "62974427"),
            W(302, 106, "A2", True), W(325, 106, "Latch"), W(350, 106, "strap"), W(387, 106, "Black"), W(410, 106, "62698627"),
            W(450, 106, "089278", True), W(465, 105, "Anthracite"), W(510, 105, "62974490"),
            # A6 one number + bold Grove number
            W(302, 117, "A6", True), W(325, 117, "Interior"), W(360, 117, "light"), W(380, 117, "switch", w=6),
            W(387, 118, "62301808"), W(426, 117, "S42767", True),
            # C1 Control knob: Grey left cell, Mocha right cell, both single-row
            W(302, 128, "C1", True), W(325, 128, "Control"), W(360, 128, "knob", w=20), W(387, 128, "Grey"),
            W(410, 128, "62302607"), W(450, 128, "089089", True), W(465, 128, "Mocha"), W(493, 128, "62302630"),
        ]
        rects = cells((96, 115.5), (115.5, 126.8)) + [(389.3, 126.8, 463.7, 138.1), (463.7, 126.8, 538.1, 138.1)]
        # A1+A2 right cell spans two rows; the A2 left cell is one row: model that as a narrower left cell
        rects += [(389.3, 104.5, 463.7, 115.5), (389.3, 96, 463.7, 104.5)]
        rows, held, unread, n = tgs.read_page(ws, rects)
        got = {(r["number"], r["desc"], r["qual"]) for r in rows}
        self.assertEqual(n, 1)
        self.assertIn(("62698627", "Latch strap (Black)", "N98"), got)
        self.assertIn(("62301808", "Interior light switch", "N98"), got)
        self.assertIn(("62302607", "Control knob (Grey)", "N98"), got)
        self.assertIn(("62302630", "Control knob (Mocha)", "N98"), got)
        nums = {r["number"] for r in rows}
        self.assertNotIn("62974427", nums)
        self.assertNotIn("62974490", nums)
        self.assertNotIn("089278", nums)
        self.assertNotIn("S42767", nums)
        self.assertTrue(any(u["number"] == "62974427" and "spans" in u["why"] for u in unread))

    def test_kit_cell_over_ten_items_is_not_assigned(self):
        ws = header() + [
            W(302, 200, "10", True), W(325, 200, "Water"), W(350, 200, "level"), W(372, 200, "housing", w=12),
            W(302, 211, "11", True), W(325, 211, "O-ring", w=30), W(387, 211, "Ruby"), W(405, 211, "red"), W(420, 211, "92405130"),
            W(302, 222, "12", True), W(325, 222, "Float", w=20), W(387, 222, "Signal"), W(410, 222, "white"), W(432, 222, "92404111", w=30),
        ]
        rects = [(389.3, 140.3, 538.1, 216.9), (389.3, 216.9, 538.1, 228.2)]
        rows, held, unread, n = tgs.read_page(ws, rects)
        nums = {r["number"] for r in rows}
        self.assertNotIn("92405130", nums)          # printed on the O-ring baseline but inside a 6-row cell
        self.assertIn("92404111", nums)
        self.assertTrue(any(u["number"] == "92405130" for u in unread))


def A(x0, y, text, w=None):
    w = w or 4.2 * len(text)
    return {"x0": x0, "top": y - 7, "x1": x0 + w, "bottom": y, "text": text}


class AlkoGroveTest(unittest.TestCase):
    def test_rows_wraps_and_cell_headings(self):
        ws = [A(40, 90, "Brakes"), {"x0": 40, "top": 100, "x1": 80, "bottom": 118, "text": "Wheel"},
              {"x0": 85, "top": 100, "x1": 120, "bottom": 118, "text": "brake"},
              A(86, 506, "AL-KO"), A(110, 506, "No."), A(136, 506, "Grove"), A(156, 506, "No."), A(172, 506, "Description"),
              A(58, 521, "1"), A(86, 521, "571950"), A(175, 521, "Brake"), A(200, 521, "welding"), A(232, 521, "plate"), A(255, 521, "left"),
              A(86, 529, "571951"), A(175, 529, "Brake"), A(200, 529, "welding"), A(232, 529, "plate"), A(255, 529, "right"),
              A(58, 543, "6"), A(86, 543, "1213888"), A(136, 543, "007660"), A(175, 543, "Brake"), A(200, 543, "pad"), A(220, 543, "set"),
              A(175, 551, "inc."), A(195, 551, "7,"), A(205, 551, "20"),
              A(58, 565, "10"), A(175, 565, "Brake"), A(200, 565, "drum"),
              A(175, 573, "Complete"), A(215, 573, "with"), A(235, 573, "bearing"),
              A(86, 581, "623748"), A(136, 581, "007659"), A(175, 581, "98"), A(186, 581, "x"), A(192, 581, "4"),
              A(86, 588, "1224800"), A(175, 588, "Bearing"), A(210, 588, "set"),
              A(58, 595, "13"), A(86, 595, "581200"), A(136, 595, "007662"), A(175, 595, "Flange"), A(205, 595, "nut"),
              A(58, 609, "19"), A(86, 609, "220098"), A(136, 609, "007628"), A(175, 609, "-7/95")]
        rows, held, n = ags.read_page(ws)
        got = {(r["number"], r["desc"]) for r in rows}
        self.assertEqual(n, 1)
        self.assertIn(("571950", "Brake welding plate left"), got)
        self.assertIn(("571951", "Brake welding plate right"), got)
        self.assertIn(("581200", "Flange nut"), got)
        nums = {r["number"] for r in rows}
        for x in ("1213888", "623748", "1224800", "220098", "007660", "007662"):
            self.assertNotIn(x, nums)
        whys = {h.get("number"): h["why"] for h in held}
        self.assertIn("wraps", whys["1213888"])
        self.assertIn("heading", whys["1224800"])
        self.assertIn("623748", whys)
        self.assertIn("word", whys["220098"])


if __name__ == "__main__":
    unittest.main()
