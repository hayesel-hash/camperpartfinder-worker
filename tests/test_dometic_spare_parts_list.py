"""Dometic (ex-Electrolux) "Spare parts list" reader: regression test from real page text and word boxes.

Fixtures (Larry's Drive, 27 Nov 2026): RMD8555 page 5 (Pos "-" rows, partial matrix "A -" / "- B"),
CTLP3050/CTS3110 cassette toilets page 10 (7 PNC columns, matrix and description on one text line),
DM2652 page 13 (production-date qualifier lines "< 0923..." under the description, 9-digit numbers).
"""
import json, os, sys, unittest

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "scripts", "aftermarket_pdf"))
import dometic_spare_parts_list as d


class FakePage:
    def __init__(self, p):
        self.text, self.words = p["text"], [tuple(w) for w in p["words"]]

    def get_text(self, kind="text"):
        return self.words if kind == "words" else self.text


def page(name):
    return FakePage(json.load(open(os.path.join(HERE, "fixtures", name)))["pages"][0])


def read(name):
    p = page(name)
    a, table = d.pass_a(p)
    return a, d.pass_b(p, table), table


class SparePartsListTest(unittest.TestCase):
    def test_rmd8555_dash_positions_and_partial_matrix(self):
        a, b, table = read("dometic_rmd8555_p5_positions.json")
        self.assertEqual(a, b)
        self.assertEqual(table, {"A": ("921084829", "RMD8555"), "B": ("921084830", "RMD8555")})
        by = {n: (p, desc) for p, n, desc in a}
        self.assertEqual(by["2412559177"], ("-", "Expanding rivet,nature,D=7,8/2,8x12, 5 piec"))
        self.assertEqual(by["2890284009"], ("007A", "Decoration plate,silver,RAL9006 [applies to: RMD8555 921084829]"))
        self.assertEqual(by["2890284504"], ("007A", "Decoration plate,silver,RAL9006 [applies to: RMD8555 921084830]"))
        self.assertEqual(len(a), 21)

    def test_ctlp_seven_columns_matrix_on_description_line(self):
        a, b, table = read("dometic_ctlp3050_p10_positions.json")
        self.assertEqual(a, b)
        self.assertEqual(len(table), 7)
        by = {n: desc for p, n, desc in a}
        self.assertEqual(by["2426011199"], "Cover,complete")
        self.assertEqual(by["2426010795"], "Reed,sensor [applies to: CTW3110 921000510]")

    def test_dm2652_qualifier_lines_kept(self):
        a, b, _ = read("dometic_dm2652_p13_positions.json")
        self.assertEqual(a, b)
        by = {n: desc for p, n, desc in a}
        self.assertEqual(by["3858004025"], "Screw,MRX M4x12 < 0923...")
        self.assertEqual(by["3858039054"], "Screw,MRX-TT/SW M4x12 > 0922...")
        self.assertEqual(by["561014010"], "Cable clamp")  # 9 digits, stored as printed
        self.assertEqual(len(a), 35)


if __name__ == "__main__":
    unittest.main()
