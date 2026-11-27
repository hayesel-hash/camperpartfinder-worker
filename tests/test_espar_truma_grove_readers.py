"""Tests for the two readers added by the 27 Nov 12:49 scheduled Drive intake:
- espar_airtronic_parts_list.py (Espar AIRTRONIC D2/D4 manual parts list): dotted number form (Larry's 27 Nov rule),
  pass A item / variant / number events, "• short harness" sub-items, lettered sub-items with a blank description;
- truma_grove_catalogue.py (Truma Spare Parts catalogue printed by Grove Products): header detection for two tables side
  by side, Grove numbers never read as parts, "Includes items below" dropped, wrapped descriptions held.
Text lines are copied from the Drive copies (pdf pp 31 / 33 of the Espar manual, split pp 001-027 p3 of the Truma catalogue)."""
import os, sys, unittest

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "scripts", "aftermarket_pdf"))
import espar_airtronic_parts_list as esp
import truma_grove_catalogue as tg


class FakePage:
    def __init__(self, text):
        self.text = text

    def get_text(self, kind="text"):
        return self.text


class EsparTest(unittest.TestCase):
    def test_dotted(self):
        self.assertEqual(esp.dotted("25 2069 99 06 00"), "25.2069.99.0600")
        self.assertEqual(esp.dotted("152 00 139"), "152.00.139")
        self.assertEqual(esp.dotted("CA0 00 019"), "CA0.00.019")
        self.assertEqual(esp.dotted("625 101 0102"), "625.101.0102")

    def test_pass_a(self):
        page = FakePage("\n".join([
            "31", "Parts List    AIRTRONIC D2/D4", "Ref. No.", "Description", "Part Number",
            "7", "Blower motor", "12V  25 2069 99 20 00", "•", "24V  25 2070 99 20 00", "•",
            "2", "Warm air deflector", "ø 60", "20 1577 89 06 00", "•", "•",
            "2a", "ø 90", "20 1609 80 09 00", "•", "•",
            "6", "Main harness", "CA1 60 201", "•", "• short harness", "CA1 60 205", "•",
            "*", "indicates optional features",
            "*36", "Operating switch (rotary)", "12V", "25 1895 71 00 00", "•",
            "Operators tape (not shown)", "625 101 0102", "•"]))
        rows = esp.pass_a_page(page)
        got = [(r["ref"], r["desc"], r["variant"], r["printed"]) for r in rows]
        self.assertIn(("7", "Blower motor", "12V", "25 2069 99 20 00"), got)
        self.assertIn(("7", "Blower motor", "24V", "25 2070 99 20 00"), got)
        self.assertIn(("2a", "Warm air deflector", "ø 90", "20 1609 80 09 00"), got)
        self.assertIn(("6", "Main harness: short harness", "", "CA1 60 205"), got)
        self.assertIn(("*36", "Operating switch (rotary)", "12V", "25 1895 71 00 00"), got)
        self.assertIn(("", "Operators tape (not shown)", "", "625 101 0102"), got)
        star = next(r for r in rows if r["ref"] == "*36")
        self.assertEqual(esp.name(star), "Operating switch (rotary), 12V (optional feature) (printed 25 1895 71 00 00)")


def W(x0, y, text, w=None):
    w = w or 4.5 * len(text)
    return {"x0": x0, "top": y - 8, "x1": x0 + w, "bottom": y, "text": text}


class TrumaGroveTest(unittest.TestCase):
    def test_two_tables_and_holds(self):
        hdr = [W(81, 115, "Truma"), W(101, 115, "No."), W(127, 115, "Grove"), W(144, 115, "No."), W(162, 115, "Description", 33),
               W(288, 115, "Qty"),
               W(338, 115, "Truma"), W(357, 115, "No."), W(383, 115, "Grove"), W(400, 115, "No."), W(418, 115, "Description", 33),
               W(453, 115, "from"), W(470, 115, "06/14"), W(544, 115, "Qty")]
        body = [W(61, 130, "10"), W(81, 130, "30020-00100"), W(162, 130, "S"), W(169, 130, "2200"), W(190, 130, "heat"),
                W(288, 130, "1"),
                W(61, 142, "20"), W(81, 142, "30030-42700"), W(127, 142, "842700"), W(162, 142, "Mica"), W(185, 142, "window"),
                W(288, 142, "1"),
                W(162, 152, "Includes"), W(200, 152, "items"), W(225, 152, "below"),
                W(81, 164, "30030-17300"), W(162, 164, "Window"), W(195, 164, "frames"), W(288, 164, "1"),
                W(162, 174, "wrapped"), W(200, 174, "text"),
                W(317, 130, "10"), W(338, 130, "30261-01"), W(418, 130, "Wall"), W(440, 130, "cowl"), W(544, 130, "1")]
        rows, held, n = tg.read_page(hdr + body)
        self.assertEqual(n, 2)
        got = {(r["number"], r["desc"], r["qual"]) for r in rows}
        self.assertIn(("30020-00100", "S 2200 heat", ""), got)
        self.assertIn(("30030-42700", "Mica window", ""), got)
        self.assertIn(("30261-01", "Wall cowl", "from 06/14"), got)
        self.assertNotIn("842700", {r["number"] for r in rows})
        self.assertNotIn("30030-17300", {r["number"] for r in rows})          # its description wraps: held
        self.assertEqual(held[0]["number"], "30030-17300")


if __name__ == "__main__":
    unittest.main()
