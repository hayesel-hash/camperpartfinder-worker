"""WFCO catalogue identity reader: regression test from real page positions.

The fixture is an excerpt of PDF pages 11 (door assemblies) and 14 (WF-8900-AD specification
table) of the WFCO 2026 product catalogue split part supplied in Larry's Drive (26 Nov 2026):
real text lines, word boxes and title spans, a few rows only.
"""
import json, os, sys, unittest

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "scripts", "aftermarket_pdf"))
import wfco_catalogue as w

FIX = json.load(open(os.path.join(HERE, "fixtures", "wfco_2026_p11_p14_positions.json")))


def pages():
    return [(p["lines"], [tuple(x) for x in p["words"]], p["spans"]) for p in FIX["pages"]]


class WfcoCatalogueTest(unittest.TestCase):
    def test_passes_agree(self):
        rows, diffs = w.read(pages())
        self.assertEqual(diffs, [])
        self.assertEqual(len(rows), 9)

    def test_door_assemblies_keep_printed_description(self):
        rows, _ = w.read(pages())
        got = {num: desc for _, _, num, desc in rows}
        self.assertEqual(got["WF-7925-GE-S-DA"], "Door Assembly for WF-7925-GE-S-Black")
        self.assertEqual(got["WF-8712-PB-DA"], "Door Assembly for WF-8712-Black")

    def test_spec_header_models_take_series_heading(self):
        rows, _ = w.read(pages())
        spec = [(num, desc) for pg, _, num, desc in rows if pg == 2]
        self.assertEqual([n for n, _ in spec], ["WF-8935-AD", "WF-8945-AD", "WF-8955-AD", "WF-8965-AD", "WF-8975-AD"])
        self.assertTrue(all(d == "WF-8900-AD POWER CENTER SERIES" for _, d in spec))

    def test_prose_mentions_are_not_identities(self):
        lines = ["The T-30 is designed to install onto the back of WF-8900 power centers."]
        self.assertEqual(w.pass_a(lines, "X"), [])


if __name__ == "__main__":
    unittest.main()
