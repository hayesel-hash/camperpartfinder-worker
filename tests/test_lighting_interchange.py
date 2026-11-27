"""Tests for the Peterson and Grote lighting interchange readers (27 Nov 2026, Larry's "yes": in scope).
Line texts and cell texts copied from the batch-2 Drive excerpts (Peterson PM-126 2025 pp 136-140, Grote 2016 pp 233-249)."""
import os, sys, unittest

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "scripts", "aftermarket_pdf"))
import peterson_interchange as pi
import grote_interchange as gi


class Peterson(unittest.TestCase):
    def test_pairs(self):
        self.assertEqual(pi.parse("52092.............. M817R-9"), (("52092", "M817R-9"), None))
        self.assertEqual(pi.parse("M09300RCL ...... M177CR-BT2"), (("M09300RCL", "M177CR-BT2"), None))

    def test_held(self):
        self.assertEqual(pi.parse("43970......150-09 + 142-49")[1], "Peterson cell names several parts")
        self.assertEqual(pi.parse("10205R/10208R. M143R")[1], "competitor number with '/' shorthand")
        self.assertEqual(pi.parse("44211Y......817SA-1/-2")[1], "not a number pair")

    def test_headers(self):
        hs, top = pi.headers([(50, 79, "GROTE......"), (90, 79, "PETERSON"), (181, 79, "MAXXIMA"), (300, 300, "noise")])
        self.assertEqual([b for _, b in hs], ["Grote", "Maxxima"])
        self.assertEqual(top, 79)


class Grote(unittest.TestCase):
    def test_classify(self):
        self.assertIsNone(gi.classify("26331", "60101-5"))
        self.assertIn("combination", gi.classify("40894", "40850+G4002"))
        self.assertIn("combination", gi.classify("M20321R", "G1502 & 43979"))
        self.assertIn("several", gi.classify("27010", "63451-4, 90951"))
        self.assertIn("several", gi.classify("30402", "67050 92149"))
        self.assertIn("space", gi.classify("PT3000A-AB S", "45063"))

    def test_groups_and_cells(self):
        # one table group: header words as on page 11 (Peterson PN | Grote Form, Fit & Function | Grote Fit & Function)
        W = [(79.8, 114.6, 105.1, 123.2, "Peterson"), (106.6, 114.6, 115.2, 123.2, "PN"),
             (124.7, 114.6, 140.2, 123.2, "Grote"), (141.8, 114.6, 157.3, 123.2, "Form,"), (158.9, 114.6, 165.9, 123.2, "Fit"),
             (167.4, 114.6, 172.1, 123.2, "&"), (136.1, 121.6, 160.6, 130.2, "Function"),
             (184.3, 114.6, 199.9, 123.2, "Grote"), (201.4, 114.6, 208.4, 123.2, "Fit"), (210.0, 114.6, 214.7, 123.2, "&"),
             (187.3, 121.6, 211.8, 130.2, "Function"),
             (80.0, 131.0, 105.0, 138.0, "V603"), (186.0, 131.0, 210.0, 138.0, "12204,"), (200.0, 131.0, 225.0, 138.0, "12004-5"),
             (80.0, 139.0, 105.0, 146.0, "V603B"), (186.0, 139.0, 210.0, 146.0, "12004"),
             (80.0, 147.0, 105.0, 154.0, "V7004"), (136.0, 147.0, 160.0, 154.0, "43153")]
        rows = gi.read(W, 792)
        self.assertIn(("Peterson", "V603B", "fit_function", "12004"), rows)
        self.assertIn(("Peterson", "V7004", "form_fit_function", "43153"), rows)
        self.assertIn(("Peterson", "V603", "fit_function", "12204, 12004-5"), rows)


if __name__ == "__main__":
    unittest.main()
