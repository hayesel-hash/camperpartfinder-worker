"""Tests for the two water-heater readers added by the 27 Nov 12:19 scheduled Drive intake:
- atwood_wh_part_reference.py (Atwood 2007 manual, Electronic Water Heaters REPLACEMENT PART REFERENCE): pass A text-line
  grouping (callouts, check marks, continuation and note lines, model-header stop) and the "No Longer Available" tidy-up;
- dometic_wh_training_tables.py (Dometic water-heater training slides): tank-cell naming.
Text lines are copied from split pp 001-093 page 46 (Larry's Drive, 27 Nov 2026)."""
import os, sys, unittest

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "scripts", "aftermarket_pdf"))
import atwood_wh_part_reference as awh
import dometic_wh_training_tables as wht


class FakePage:
    def __init__(self, text):
        self.text = text

    def get_text(self, kind="text"):
        return self.text


P46 = "\n".join([
    "Electronic", "Water Heaters", "REPLACEMENT PART REFERENCE", "January 2007", "a",
    "91470  130° Front Mount thermostat (not shown)", "✗", "✗",
    "93105  Adjustable Thermostat (retrofits", "✗", "✗", "front-mount thermostats) (not shown)",
    "3", "91514  Access Door (6 Gal.) Colonial White ✗", "✗",
    "NS", "91420  Potted Circuit Board", "No Longer Available (Use 91504)", "(post electrode connection)",
    "8A", "93243  Gas Valve Bracket - (6 Gal.)", "✗", "(Use with 93870)",
    "15-A", "93871  Drawn Pan (Electronic 10 Gal.)", "✗",
    "GCH6-4E, GCH6-6E, GCH6-7E, GC6A-7E", "GC10A-4E, GCH10A-4E", "35"])


class AtwoodWaterHeaterReference(unittest.TestCase):
    def test_pass_a_rows(self):
        rows = dict(awh.pass_a(FakePage(P46)))
        self.assertEqual(rows["93105"], "Adjustable Thermostat (retrofits front-mount thermostats) (not shown)")
        self.assertEqual(rows["91514"], "Access Door (6 Gal.) Colonial White")
        self.assertEqual(rows["93243"], "Gas Valve Bracket - (6 Gal.) (Use with 93870)")
        self.assertEqual(rows["93871"], "Drawn Pan (Electronic 10 Gal.)")  # model header lines and page number not appended
        self.assertEqual(awh.tidy(rows["91420"]),
                         "Potted Circuit Board (post electrode connection) - No Longer Available (Use 91504)")

    def test_tidy_leaves_plain_rows(self):
        self.assertEqual(awh.tidy("Relay"), "Relay")


class TrainingSlides(unittest.TestCase):
    def test_tank_label(self):
        self.assertEqual(wht.label("Replacement Tanks", "GC6AA"), "Replacement tank: GC6AA")
        self.assertEqual(wht.label("Description", "Relief Valve 1/2”"), "Relief Valve 1/2”")


if __name__ == "__main__":
    unittest.main()
