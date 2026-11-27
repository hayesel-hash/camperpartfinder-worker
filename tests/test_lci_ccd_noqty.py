"""Regression test for lci_ccd_noqty.py from real page text and word boxes (Larry's Drive, 27 Nov 2026):
Lippert Power Tongue Jack CCD-0002709 page 2 (callout I holding two numbers, Original / Current) and SlimRack Plus
CCD-0007723 page 7 ("*" numbers with the page's "*Part must be replaced using variant code" note)."""
import json, os, sys, unittest

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "scripts", "aftermarket_pdf"))
import lci_ccd_noqty as nq


class FakePage:
    def __init__(self, p):
        self.text, self.words = p["text"], [tuple(w) for w in p["words"]]
        self.rect = type("R", (), {"height": p["height"]})

    def get_text(self, kind="text"):
        return self.words if kind == "words" else self.text


def pages():
    return [FakePage(p) for p in json.load(open(os.path.join(HERE, "fixtures", "lippert_ccd_noqty_positions.json")))["pages"]]


class CcdNoQtyTest(unittest.TestCase):
    def test_passes_agree(self):
        for p in pages():
            self.assertEqual(nq.finish(p, nq.pass_a(p)), nq.finish(p, nq.pass_b(p)))

    def test_rows(self):
        p2709, p7723 = pages()
        a = dict(nq.finish(p2709, nq.pass_a(p2709)))
        self.assertEqual(a["225885"], "Lens (Original)")
        self.assertEqual(a["706948"], "Lens (Current)")
        self.assertEqual(len(a), 9)
        b = dict(nq.finish(p7723, nq.pass_a(p7723)))
        self.assertEqual(b["694131"], "H-column (OBSOLETE- USE 2024027511) (*Part must be replaced using variant code)")
        self.assertNotIn("*694131", b)


if __name__ == "__main__":
    unittest.main()
