"""Norcold (Thetford NA) refrigerator parts-list reader: regression test from real page text, word boxes and ruled lines.

Fixtures (Larry's Drive, 27 Nov 2026): N2152 641000 page 3 (merged number cells 691867 / 692758, italic grey rows,
SUPERSEDED TO notes, separate WARRANTABLE box), 2118 PolarMax 637110 page 7 (grey PART # cells, legend "*" = NOT
AVAILABLE and grey = NO LONGER AVAILABLE, (USE n) notes, horizontal model headers), N8DC/N10DC 640138 page 6
("***" footnote written as a separate word).
"""
import json, os, sys, unittest
import pymupdf

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "scripts", "aftermarket_pdf"))
import norcold_parts_list as n


class FakePage:
    def __init__(self, p):
        self.text, self.words = p["text"], [tuple(w) for w in p["words"]]
        self.rect = pymupdf.Rect(p["rect"])
        self.dr = []
        for g in p["drawings"]:
            items = []
            for it in g["items"]:
                if it[0] == "l":
                    items.append(("l", pymupdf.Point(it[1]), pymupdf.Point(it[2])))
                else:
                    items.append(("re", pymupdf.Rect(it[1])))
            self.dr.append({"fill": tuple(g["fill"]) if g["fill"] else None, "items": items})

    def get_text(self, kind="text"):
        return self.words if kind == "words" else self.text

    def get_drawings(self):
        return self.dr


PAGES = {(p["doc"], p["page"]): FakePage(p) for p in json.load(open(os.path.join(HERE, "fixtures", "norcold_parts_list_pages.json")))["pages"]}


def both(page):
    a = n.pass_a(page)
    b = [(r["num"], r["star"], r["desc"], r["nx"]) for r in n.pass_b(page)]
    return a, b


class NorcoldPartsListTest(unittest.TestCase):
    def test_n2152_merged_cells_and_supersessions(self):
        p = PAGES[("N2152", 3)]
        a, b = both(p)
        self.assertEqual(a, b)
        by = {r[0]: r for r in a}
        self.assertEqual(by["691867"][2], "CABINET FAN COVER ; CABINET FAN SCREEN")
        self.assertEqual(by["692758"][2], "DOOR LATCH ; WINTER LOCK SUPPORT")
        self.assertEqual(by["692802"][2], "SUPERSEDED TO 692754")
        self.assertEqual(by["692801"][1], 1)
        stars, shade = n.legend(p)
        self.assertEqual((stars.get(1), shade), ("limited availability", "not available"))
        cols = n.pass_b(p)[0]["mcols"]
        self.assertEqual([c[1] for c in cols], ["N2175", "WARRANTABLE"])

    def test_2118_cell_shading_legend_and_models(self):
        p = PAGES[("2118", 7)]
        a, b = both(p)
        self.assertEqual(a, b)
        stars, shade = n.legend(p)
        self.assertEqual((stars.get(1), shade), ("not available", "no longer available"))
        rows = {r["num"]: r for r in n.pass_b(p)}
        self.assertEqual([c[1] for c in rows["636932"]["mcols"]], ["NON DISPENSER (IM)", "WITH DISPENSER (IMD)"])
        self.assertEqual(rows["636932"]["nx"], 1)
        greys = n.grey_rects(p)
        shaded = lambda num: any(pymupdf.Rect(g).intersect(rows[num]["rect"]).get_area() > 0.5 * rows[num]["rect"].get_area() for g in greys)
        self.assertTrue(shaded("640272"))   # thin grey cell, checked at 200 dpi
        self.assertFalse(shaded("639719"))
        self.assertTrue(shaded("61656822"))
        self.assertEqual(rows["61656922"]["star"], 1)

    def test_n8dc_triple_star_footnote(self):
        p = PAGES[("N8DC", 6)]
        a, b = both(p)
        self.assertEqual(a, b)
        stars, _ = n.legend(p)
        self.assertEqual(stars.get(3), "used during troubleshooting only")
        self.assertEqual({r[0]: r[1] for r in a}["641315"], 3)


if __name__ == "__main__":
    unittest.main()
