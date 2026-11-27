"""Thetford North-America toilet parts sheet reader: regression test from real page text and word boxes.

Fixtures (Larry's Drive, 27 Nov 2026): Cassette C2 Rev C pages 1-2 ("Superseded by" chains, N/A rows, 7-8 digit
numbers, a Not Shown block beside the table on page 2); Aqua-Magic Style Plus Rev D page 1 (vertically centred
two-line descriptions, Not Shown block with a stray drawing callout "11").
"""
import json, os, sys, unittest

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "scripts", "aftermarket_pdf"))
import thetford_us_sheet as t


class FakePage:
    def __init__(self, p):
        self.text, self.words = p["text"], [tuple(w) for w in p["words"]]

    def get_text(self, kind="text"):
        return self.words if kind == "words" else self.text


def pages(name):
    return [FakePage(p) for p in json.load(open(os.path.join(HERE, "fixtures", name)))["pages"]]


class ThetfordUsSheetTest(unittest.TestCase):
    def test_c2_supersessions_and_na_rows(self):
        p1, p2 = pages("thetford_c2_p1_p2_positions.json")
        a1, b1 = t.pass_a(p1), t.pass_b(p1)
        self.assertEqual(sorted(a1), sorted(b1))
        by = dict(a1)
        self.assertEqual(by["1638578"], "Drain Cap Water Fill Funnel")
        self.assertEqual(by["33337"], "Superseded by 16385")
        self.assertEqual(by["20063874"], "Holding Tank Complete (Right-Hand)")
        self.assertEqual(by["16175"], "Lip Seal (Pre-6/15/00) (limited availability)")
        self.assertNotIn("N/A", by)
        self.assertNotIn("Hinge Post/Pin", by.values())  # N/A row's text is not given to a neighbour
        a2, b2 = t.pass_a(p2), t.pass_b(p2)
        self.assertEqual(sorted(a2), sorted(b2))
        self.assertEqual(dict(a2)["16451"], "Fuse – 3 Amp")

    def test_style_plus_two_line_cells_and_stray_callout(self):
        p = pages("thetford_am_styleplus_p1_positions.json")[0]
        a, b = t.pass_a(p), t.pass_b(p)
        self.assertEqual(sorted(a), sorted(b))
        by = dict(a)
        self.assertEqual(by["34366"], "Drive Link")
        self.assertEqual(by["34454"], "Seat and Cover Assembly – Wood (limited availability)")
        self.assertEqual(len(a), 25)


if __name__ == "__main__":
    unittest.main()
