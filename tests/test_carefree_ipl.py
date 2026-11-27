"""Carefree illustrated parts list reader: regression test from real page positions.

Fixture: Spirit FX and Fiesta IPL page 2 and Rafter VII IPL page 1, supplied in Larry's Drive
(27 Nov 2026): real dict-layer line cells and word boxes.
"""
import json, os, sys, unittest

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "scripts", "aftermarket_pdf"))
import carefree_ipl as c

FIX = json.load(open(os.path.join(HERE, "fixtures", "carefree_ipl_spiritfx_p2_rafter7_positions.json")))


def pages():
    return [([(tuple(b), t) for b, t in p["dict_lines"]], [tuple(w) for w in p["words"]]) for p in FIX["pages"]]


class CarefreeIplTest(unittest.TestCase):
    def setUp(self):
        self.rows, self.diffs, self.templates = c.read(pages())
        self.by = {num: desc for _, _, num, desc in self.rows}

    def test_passes_agree(self):
        self.assertEqual(self.diffs, [])
        self.assertEqual(len([r for r in self.rows if r[0] == 1]), 38)

    def test_order_templates_skipped(self):
        self.assertEqual(self.templates, 16)
        self.assertFalse(any("nn" in n or "XX" in n or "xx" in n for n in self.by))

    def test_continuation_line_and_notes(self):
        self.assertEqual(self.by["R098226-005"], "Idler End Cap, White (Does Not Include a Spring) 7' 11\" or less")
        self.assertEqual(self.by["R012803-405"], "Remote Lock, White L = 41.5\" — Monaco")
        self.assertEqual(self.by["R00483WHT"], "Cradle w/ Bracket — White")

    def test_not_shown_heading_is_not_appended(self):
        self.assertEqual(self.by["901035XL"], "Pull Wand — 61\"")
        self.assertEqual(self.by["030573"], "Slider Set Screw")


class CarefreeNoNotesColumnTest(unittest.TestCase):
    """President's Club parts book page 3 (Item | Part Number | Description, no Notes column), 27 Nov 2026."""

    def setUp(self):
        fx = json.load(open(os.path.join(HERE, "fixtures", "carefree_hardware_book_p3_positions.json")))
        pages = [([(tuple(b), t) for b, t in p["dict_lines"]], [tuple(w) for w in p["words"]]) for p in fx["pages"]]
        self.rows, self.diffs, _ = c.read(pages)
        self.by = {num: desc for _, _, num, desc in self.rows}

    def test_table_without_notes_column_is_read(self):
        self.assertEqual(self.diffs, [])
        self.assertEqual(self.by["041006"], "Polycord, 5/32\u201d (per foot)")
        self.assertEqual(self.by["901044W"], "Pull Strap Catch \u2013 White pkg of 2")
        self.assertEqual(self.by["R030307-001-MP"], "Moly Rivet pkg of 50")
        self.assertNotIn("--", self.by)


if __name__ == "__main__":
    unittest.main()
