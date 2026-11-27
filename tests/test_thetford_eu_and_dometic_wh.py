"""Regression tests for two readers added by the 27 Nov ~08:50 scheduled Drive intake:
- thetford_eu_spare_list.py (Thetford Europe Word spare-parts tables): number / date tokens, item labels, and the
  same-class run logic that bounds a merged cell. The 1-D profiles below copy what the C200 list (page 2, column 2)
  and the C200 waste-holding-tank list (page 6, column 3) show: a shaded cell that stops above a white cell with no
  rule between them (23848, items 26-28 only), and a shaded cell bounded by rules.
- dometic_wh_service_kits.py: part-number pattern and the footnote stop ("1\\x07The water heaters ...").
"""
import os, sys, unittest

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "scripts", "aftermarket_pdf"))
import thetford_eu_spare_list as te
import dometic_wh_service_kits as wh


def prof(spec, step=1.0):
    """'W'*a + 'G'*b ... as a profile with 1 pt per character."""
    return list(spec), step


class ThetfordTokens(unittest.TestCase):
    def test_numbers(self):
        for n in ("23343", "200641", "07524", "SSPA0606", "SSPO1104", "3111762"):
            self.assertTrue(te.NUMRE.match(n), n)

    def test_dates_and_words_are_not_numbers(self):
        for n in ("06-12-16", "29-01-2024", "25-09-2011", "31-06-", "2016", "C-model", "62", "127", "(E340T…)"):
            self.assertFalse(te.NUMRE.match(n), n)

    def test_item_labels(self):
        for n in ("1", "8b", "7A", "10B", "29a"):
            self.assertTrue(te.ITEM.match(n), n)
        self.assertFalse(te.ITEM.match("Not"))

    def test_item_span(self):
        self.assertEqual(te.item_span(["3"]), "item 3")
        self.assertEqual(te.item_span(["26", "27", "28"]), "items 26-28")
        self.assertEqual(te.item_span([]), "no item number")


class ThetfordCells(unittest.TestCase):
    def test_shaded_cell_stops_at_unshaded_cell_without_rule(self):
        # rule at 0, shaded 1-9 (number at y=5), white 10-13 (no rule in between), rule at 14
        p = prof("D" + "G" * 9 + "W" * 4 + "D")
        self.assertEqual(te.run_at(p, 5), (1.0, 10.0))
        self.assertEqual(te.cell_at([p, p], 5), (1.0, 10.0))

    def test_cell_is_intersection_of_both_sample_positions(self):
        left = prof("D" + "W" * 12 + "D")
        right = prof("D" + "W" * 5 + "D" + "W" * 6 + "D")  # a rule seen only at the right edge
        self.assertEqual(te.cell_at([left, right], 3), (1.0, 6.0))

    def test_number_on_a_rule_has_no_cell(self):
        p = prof("WWDWW")
        self.assertIsNone(te.cell_at([p], 2))

    def test_dark_lines_and_grey_ends(self):
        p = prof("WDDWGGGWD")
        self.assertEqual(te.dark_lines(p), [2.0, 8.5])  # centre of [1, 3) and [8, 9)
        self.assertEqual(te.grey_ends(p), [7.0])


class DometicWaterHeater(unittest.TestCase):
    def test_numbers(self):
        for n in ("90028", "92668", "4472006337"):
            self.assertTrue(wh.NUM.match(n), n)
        for n in ("4021", "447200633", "9GEA1"):
            self.assertFalse(wh.NUM.match(n), n)

    def test_footnote_stop(self):
        self.assertTrue(wh.FOOT.match("1\x07The water heaters actual capacity is 6 gallons respectively."))
        self.assertTrue(wh.FOOT.match("2The water heaters actual capacity"))
        self.assertFalse(wh.FOOT.match("KIT, SVC 10 GAL WHITE DOOR"))
        self.assertFalse(wh.FOOT.match("(like 91858 but with vent and new DOOR label)"))

    def test_kit_rows_from_text_order(self):
        class P:
            def get_text(self, *a):
                return "\n".join(["2", "Service Kit Parts Descriptions", "6A", "6GEA", "9GEA1", "Service Kit ", "Number",
                                  "Description", "X", "X", "X", "92101", "KIT, SVC DOOR HARDWARE ",
                                  "(like 91858 but with vent and new DOOR label)", "X", "95505", "KIT, SVC 10 GAL WHITE DOOR",
                                  "1\x07The water heaters actual capacity is 6 gallons respectively."])
        rows = wh.a_kits(P())
        self.assertEqual(rows, [("92101", "KIT, SVC DOOR HARDWARE (like 91858 but with vent and new DOOR label)", 3),
                                ("95505", "KIT, SVC 10 GAL WHITE DOOR", 1)])


if __name__ == "__main__":
    unittest.main()
