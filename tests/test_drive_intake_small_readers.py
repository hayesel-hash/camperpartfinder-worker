"""Regression tests for three small readers added by the 27 Nov 06:19 scheduled Drive intake, from real page text and
word boxes (Larry's Drive, 27 Nov 2026):
- lci_ccd_model_list.py: Furrion tankless water heater CCD-0009617 pages 11-12 (Callout | Part # | Description |
  Model; vertically centred model cells; callout G "N/A");
- dometic_parts_web.py: Penguin II 641935 sheet page 2 (descriptions wrapped mid-word) and Brisk II B59516 Parts Web
  export page 2 (footer below the last row);
- dometic_df_furnace.py: DF Series furnace list 33402 pages 5 and 8 (X marks a few points off the row baseline; SPI 4850
  without an SCV_KIT number).
"""
import json, os, sys, unittest

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "scripts", "aftermarket_pdf"))
import lci_ccd_model_list as lm
import dometic_parts_web as pw
import dometic_df_furnace as df


class FakePage:
    def __init__(self, p):
        self.text, self.words = p["text"], [tuple(w) for w in p["words"]]

    def get_text(self, kind="text"):
        return self.words if kind == "words" else self.text

    class rect:
        height = 792


def pages(name):
    return [FakePage(p) for p in json.load(open(os.path.join(HERE, "fixtures", name)))["pages"]]


class FurrionModelListTest(unittest.TestCase):
    def test_both_pages_agree(self):
        for p in pages("furrion_ccd0009617_p11_p12_positions.json"):
            self.assertEqual(lm.pass_a(p), lm.pass_b(p))
        p11, p12 = pages("furrion_ccd0009617_p11_p12_positions.json")
        by = dict(lm.pass_a(p11) + lm.pass_a(p12))
        self.assertEqual(by["2022006595"], "Controller Unit with Freeze Detector [models: FWH09A, FWH09A-AM, FWH09AFA, FWH09AFA-AM]")
        self.assertEqual(by["2023136654"], "Water Drain Ramp For Flangeless Water Heater [models: FWH09AFA-AB]")
        self.assertEqual(by["2026072612"], "Flue Duct seal for Flangeless Water Heater Door (White) [models: FWH09AFA, FWH09AFA-AM, FWH09AFA-AB]")
        self.assertNotIn("N/A", by)
        self.assertEqual(len(by), 31)


class PartsWebTest(unittest.TestCase):
    def test_penguin(self):
        p = pages("dometic_penguin2_p2_positions.json")[0]
        a = pw.pass_a(p)
        self.assertEqual(a, pw.pass_b(p))
        by = dict(a)
        self.assertEqual(by["3314471.001"], "S,SHROUD,PENGUI N II,WHT")
        self.assertEqual(by["3310328.000"], "HEATER ELEMENT & SWITCH")
        self.assertEqual(by["3311599.000"], "NO LONGER AVAILABLE")
        self.assertEqual(len(a), 20)

    def test_brisk2_footer_not_in_last_row(self):
        p = pages("dometic_brisk2_p2_positions.json")[0]
        a = pw.pass_a(p)
        self.assertEqual(a, pw.pass_b(p))
        self.assertEqual(dict(a)["3312195.000"], "KIT,SVC CAPACITOR 60/5 MFD")
        self.assertEqual(len(a), 14)


class DfFurnaceTest(unittest.TestCase):
    def test_marks_and_missing_number(self):
        p5, p8 = pages("dometic_df_furnace_p5_p8_positions.json")
        a5 = df.pass_a(p5); b5, sizes5 = df.pass_b(p5)
        self.assertEqual(a5, b5)
        self.assertEqual(sizes5["4504"], ["Small", "Medium"])
        self.assertEqual(sizes5["4510"], ["Small", "Medium", "Large DC", "Large AC"])
        self.assertIn(("4541", "31501", "KIT, UNIV IGNITION DC", 3), a5)
        a8 = df.pass_a(p8); b8, _ = df.pass_b(p8)
        self.assertEqual(a8, b8)
        self.assertIn(("4850", None, "BLOWER HOUSING - REAR - LG", 2), a8)


if __name__ == "__main__":
    unittest.main()
