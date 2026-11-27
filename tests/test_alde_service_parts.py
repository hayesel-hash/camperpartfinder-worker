"""Alde service manual reader: regression test from real page positions.

Fixture: Alde Compact 3020 HE service manual pages 13-15 (fault finding prose, exploded drawing,
spare parts), supplied in Larry's Drive (27 Nov 2026): real text layer and word boxes.
"""
import json, os, sys, unittest

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "scripts", "aftermarket_pdf"))
import alde_service_parts as a

FIX = json.load(open(os.path.join(HERE, "fixtures", "alde_3020he_p13_p15_positions.json")))


class AldeServicePartsTest(unittest.TestCase):
    def setUp(self):
        self.rows, self.diffs = a.read([(p["text"], [tuple(w) for w in p["words"]]) for p in FIX["pages"]])
        self.by = {}
        for _, _, num, desc, sec in self.rows:
            self.by.setdefault(num, (desc, sec))

    def test_passes_agree_and_prose_page_ignored(self):
        self.assertEqual(self.diffs, [])
        self.assertNotIn("3020 013", self.by)  # control panel number quoted in fault-finding prose (page 13)
        self.assertEqual(len([r for r in self.rows if r[0] == 2]), 38)
        self.assertEqual(len(self.by), 37)

    def test_number_alone_on_line_takes_next_line(self):
        self.assertEqual(self.by["3020 011"], ("Service cover", "EXPLODED DRAWING"))

    def test_two_numbers_on_one_callout(self):
        self.assertEqual(self.by["3020 040"][0], "Circuit board 3 kW for model A")
        self.assertEqual(self.by["3020 140"][0], "Circuit board 3 kW for model HE")

    def test_other_small_parts_and_spare_parts_page(self):
        self.assertEqual(self.by["3010 205"][0], "Cable for fan")
        self.assertEqual(self.by["3010 306"], ("Spark plug/Sensor plug", "SPARE PARTS"))
        self.assertEqual(self.by["3010 159"][0], "Support for non-return valve")


if __name__ == "__main__":
    unittest.main()
