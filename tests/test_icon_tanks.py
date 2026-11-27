"""ICON tank-page reader: regression test from real page positions.

Fixture: PDF pages 26 and 43 of the ICON Technologies 2027 RV Parts Catalog split pp 115-229
supplied in Larry's Drive (27 Nov 2026): real text lines and word boxes.
Page 43 has the rotated "HOLDING TANKS" label on the left edge sharing a baseline with a row.
"""
import json, os, sys, unittest

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "scripts", "aftermarket_pdf"))
import icon_tanks as t

FIX = json.load(open(os.path.join(HERE, "fixtures", "icon_2027_tanks_p26_p43_positions.json")))


def pages():
    return [(p["lines"], [tuple(w) for w in p["words"]], p["width"]) for p in FIX["pages"]]


class IconTanksTest(unittest.TestCase):
    def setUp(self):
        self.rows, self.diffs = t.read(pages(), first_full_page=140)

    def test_passes_agree_despite_edge_label(self):
        self.assertEqual(self.diffs, [])
        self.assertIn(("14088", "0188275"), {(r["icon"], r["oem_number"]) for r in self.rows})

    def test_two_numbers_make_two_assertions_under_the_heading(self):
        got = [(r["oem_number"], r["heading"]) for r in self.rows if r["icon"] == "14568"]
        self.assertEqual(got, [("0342578", "WT3832 Fresh Water Tank"), ("2000227", "WT3832 Fresh Water Tank")])

    def test_unnamed_or_misspelt_brand_is_held_not_guessed(self):
        held = {(r["icon"], r["oem_number"]): r for r in self.rows if r["hold"]}
        self.assertIsNone(held[("15924", "2047644")]["brand"])
        self.assertIn("no brand", held[("15924", "2047644")]["hold"])
        self.assertIsNone(held[("14883", "0206")]["brand"])
        self.assertIn("misspelt", held[("14883", "0206")]["hold"])
        self.assertIn("tank model code", held[("16423", "WT3834")]["hold"])

    def test_brand_casing_and_printed_brand_kept(self):
        sc = [r for r in self.rows if r["icon"] == "14088"][0]
        self.assertEqual((sc["printed_brand"], sc["brand"]), ("StarCraft", "Starcraft"))
        self.assertEqual(sc["heading"], "Center Side Drain HT140-SD")

    def test_split_rest(self):
        self.assertEqual(t.split_rest("Forest River #3038")[1:3], ("Forest River", ["3038"]))
        self.assertEqual(t.split_rest("Jayco Entegra 2078798")[:3], ("Jayco Entegra", "Jayco", ["2078798"]))


if __name__ == "__main__":
    unittest.main()
