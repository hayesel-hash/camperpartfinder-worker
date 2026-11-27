"""Dometic roof A/C / heat pump parts list reader: regression test from real page positions.

Fixtures (Larry's Drive, 27 Nov 2026; real text layer and word boxes):
- Dometic 620315.421 parts list form 3106797.024, pages 5-6 (centred "Description" header, a Customer Option
  box beside the table, sub-items A1-A3 and B1-B7);
- Dometic 630515.321 heat pump parts list form 3109747.018, page 4 (two tables side by side, the right one
  without a header; rows whose number sits on a second line).
"""
import json, os, sys, unittest

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "scripts", "aftermarket_pdf"))
import dometic_parts_list as d


def load(name):
    fx = json.load(open(os.path.join(HERE, "fixtures", name)))
    return [(p["text"], [tuple(w) for w in p["words"]]) for p in fx["pages"]]


class Dometic620315Test(unittest.TestCase):
    def setUp(self):
        self.kept, self.held, self.diffs = d.read(load("dometic_620315_p5_p6_positions.json"))
        self.by = {r[3]: (r[2], r[4]) for r in self.kept}

    def test_description_left_of_centred_header(self):
        self.assertEqual(self.by["3102888.009"], ("1", "Decal, (1) each side (2 req.)"))
        self.assertEqual(self.by["312110.024"], ("14", "Screw, M .25 x 20 x .75 HW (4 req.)"))

    def test_sub_items_and_heater_page(self):
        self.assertEqual(self.by["3100394.109"], ("A1", "Sleeve, fiberglass"))
        self.assertEqual(self.by["3104567.007"], ("B1", "Element, heater"))

    def test_see_note_and_option_box_not_loaded(self):
        self.assertNotIn("3107746.004", self.by)  # shroud numbers from NOTE 1
        self.assertNotIn("3106615.002", self.by)  # Customer Option box (component first, no index)
        unread = {h[2] for h in self.held if h[1] == "unread"}
        self.assertIn("3106615.002", unread)

    def test_disagreeing_rows_are_held(self):
        held = {h[2] for h in self.held if h[1] != "unread"}
        self.assertEqual(held, {"3107856.001", "3107857.009", "3105014.132"})
        self.assertEqual(len(self.kept), 75)


class Dometic630515Test(unittest.TestCase):
    def setUp(self):
        self.kept, self.held, self.diffs = d.read(load("dometic_630515_hp_p4_positions.json"))
        self.by = {r[3]: (r[2], r[4]) for r in self.kept}

    def test_number_on_second_line(self):
        self.assertEqual(self.by["3109274.005"], ("2", 'Decal, Duo-Therm (2 req.) (Not Used On "D" or "E" Suffix)'))
        self.assertEqual(self.by["3102669.052"], ("A1", 'Tape, Foam 1.25" x 0.75" x 63"'))

    def test_headerless_right_column_reported_not_loaded(self):
        self.assertNotIn("3108703.194", self.by)
        unread = {h[2] for h in self.held if h[1] == "unread"}
        self.assertIn("3108703.194", unread)
        self.assertEqual(len(self.kept), 57)
        self.assertEqual(self.diffs, [])


if __name__ == "__main__":
    unittest.main()
