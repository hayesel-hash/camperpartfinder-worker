"""Regression test for atwood_hf_parts_list.py (27 Nov 06:49 scheduled Drive intake), from real page text, word boxes
and ruled-table row boxes (Larry's Drive, 27 Nov 2026):
- hydro flame 7900-II & 8012-II list page 2: two tables side by side, rows interleave left / right in text order;
- hydro flame 8900-III list page 3: a merged Item cell spanning two rows (find_tables reports one row covering both).
"""
import json, os, sys, unittest

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "scripts", "aftermarket_pdf"))
import atwood_hf_parts_list as m


class FakePage:
    def __init__(self, p):
        self.text, self.words, self.tables = p["text"], [tuple(w) for w in p["words"]], p["tables"]

    def get_text(self, kind="text"):
        return self.words if kind == "words" else self.text


def pages():
    return [FakePage(p) for p in json.load(open(os.path.join(HERE, "fixtures", "atwood_hf_7900_p2_8900_p3_positions.json")))["pages"]]


def norm(rows):
    return [(g, c, n, t, tuple(k)) for g, c, n, t, k in rows]


class AtwoodHydroFlameListTest(unittest.TestCase):
    def test_passes_agree(self):
        for p in pages():
            a, groups, bad = m.pass_a(p)
            self.assertEqual(bad, [])
            self.assertEqual(norm(a), norm(m.pass_b(p, p.tables)))

    def test_two_up_rows_keep_their_table(self):
        p7900 = pages()[0]
        a, groups, _ = m.pass_a(p7900)
        self.assertEqual(len(groups), 2)
        self.assertEqual(len(a), 56)
        by = {n: (g, c, t, k) for g, c, n, t, k in a}
        self.assertEqual(by["31036"], (1, "Motors", "MOTOR, 79", [False, True, True, True]))
        self.assertEqual(by["36043"], (0, "", "ASSY,BURNER HEAD COMPLETE", [True, True, True, True]))
        self.assertEqual(by["36147"][2:], ("BAFFLE,SECONDARY AIR 7916 7920", [False, False, True, True]))
        names = [x for x in groups[0] if x not in m.LABELS]
        self.assertEqual(m.models_text(by["31265"][3], names), " [models: 7920_II]")

    def test_merged_item_cell(self):
        p8900 = pages()[1]
        b = {n: k for g, c, n, t, k in m.pass_b(p8900, p8900.tables)}
        self.assertIn("35122", b)
        self.assertIn("37964", b)
        self.assertEqual(b["37964"][-2:], [True, True])


if __name__ == "__main__":
    unittest.main()
