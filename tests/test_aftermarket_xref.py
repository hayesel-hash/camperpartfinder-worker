"""Aftermarket cross-reference chart reader (Dinosaur Electronics).

Fixtures are short excerpts reproducing the chart layouts seen on the maker's
pages on 26 Nov 2026 (a few rows per table, inside the site's layout and
navigation tables). They test layout handling, not real-world counts; the
live run is verified separately against the archived page text.
"""
import os, sys, unittest
HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
import aftermarket_xref as ax

NAV = """<table><tr><td><a href="index.htm"><b>DINOSAUR ELECTRONICS HOME PAGE</b></a></td>
<td><a href="Onan_boards.htm">REPLACEMENTS for ONAN&reg;</a></td></tr></table>"""

NORCOLD = f"""<html><body><table><tr><td>{NAV}</td></tr><tr><td>
<p><b>Norcold&reg; Cross reference</b></p>
<table border=1>
<tr><td>Norcold &reg; Model#</td><td>Dino # Control</td><td>Dino # Eyebrow</td>
    <td>Norcold &reg; Model#</td><td>Dino # Control</td><td>Dino # Eyebrow</td></tr>
<tr><td>652 2-way (long wires)</td><td>618661</td><td>61647322</td>
    <td>838 EG2 (2-way)*</td><td>61716822*</td><td>N/A</td></tr>
</table>
<table border=1>
<tr><td colspan=3><b>Norcold&reg; Control Board Cross reference</b></td></tr>
<tr><td>Norcold&reg; Control Board#</td><td>Dino Control Board #</td><td>Jumper Position</td></tr>
<tr><td>621269.001</td><td>6212XX</td><td>621269</td></tr>
<tr><td>618224</td><td>N991</td><td>618224</td></tr>
</table></td></tr></table></body></html>"""

DOMETIC = """<html><body>
<p>These charts are for guidence only. We highly recommend that you get the exact board number</p>
<table border=1>
<tr><td>Dometic&reg; Part #</td><td>Dinosaur #</td><td>Dometic&reg; Part #</td><td>Dinosaur #</td></tr>
<tr><td>3106375.015</td><td>See Service Alert</td><td>3850712-01</td><td>3850712.01</td></tr>
<tr><td>2931308-01</td><td>P246 Plus</td><td>87500351-19</td><td>Micro P1338 Rev 5</td></tr>
</table>
<table border=1>
<tr><td>Dometic&reg; Black Box #</td><td>Dinosaur #</td><td>Dometic&reg; Black Box #</td><td>Dinosaur #</td></tr>
<tr><td>2931842.01</td><td>Micro P-711</td><td>3850415-013</td><td>3850415.01 Note1</td></tr>
</table>
<p>Note: The Mirco P-711 will not work to replace the 3850415-013 board found in Universal Power Board kits</p>
<table border=1>
<tr><td>Dometic&reg; Model #</td><td>Dinosaur #</td><td>Dometic&reg; Model#</td><td>Dinosaur #</td></tr>
<tr><td>RM 2551 "Americana"</td><td></td><td>RM 3607</td><td>Micro P-711</td></tr>
<tr><td>Prod. # 921142101 - 921142110</td><td>3850415.01</td><td></td><td></td></tr>
<tr><td>Pord. # 921146167 - 921146184</td><td>3850712.01</td><td></td><td></td></tr>
</table></body></html>"""

IGNITOR = """<table border=1>
<tr><td>MFG&#8217;S Part #</td><td>Dinosaur #</td><td>MFG&#8217;S Part #</td><td>Dinosaur#</td></tr>
<tr><td>Mark 10DM-12-1-12-12-E3002</td><td>UIB S &amp; a 6 pin header connector</td><td>38242</td><td>None</td></tr>
<tr><td>05-159000-003</td><td>UIB L</td><td>520814</td><td>Kit with ? UIB S</td></tr>
<tr><td>BLUE BOY</td><td>UIB S</td><td>232613</td><td>Fan 50 Plus Pins</td></tr>
</table>"""

ONAN = """<table border=1>
<tr><td>Onan &reg; Part #</td><td>Dinosaur #</td></tr>
<tr><td>300-3764</td><td>300-3764</td></tr>
<tr><td>300-0944</td><td>300-1073/4950</td></tr>
</table>
<p>You must look at the board, you are replacing to get the correct part number.</p>"""


def by(rows, **kw):
    return [r for r in rows if all(r.get(k) == v for k, v in kw.items())]


class Norcold(unittest.TestCase):
    rows, notes = ax.extract(NORCOLD, "Nor_chart.htm")

    def test_navigation_table_ignored(self):
        self.assertFalse([r for r in self.rows if "HOME" in r["row_text"]])

    def test_board_number_table_is_a_named_replacement(self):
        (r,) = by(self.rows, oem_number="618224")
        self.assertEqual((r["relation"], r["oem_brand"], r["oem_brand_basis"], r["aftermarket_number"], r["status"]),
                         ("replaces", "Norcold", "named_on_page", "N991", "staged"))
        self.assertEqual(r["category"], "refrigeration")

    def test_jumper_position_kept_as_qualifier(self):
        (r,) = by(self.rows, oem_number="621269.001")
        self.assertEqual(r["aftermarket_number"], "6212XX")
        self.assertEqual(r["qualifiers"]["jumper_position"], "621269")

    def test_model_table_is_fitment_not_replacement(self):
        fits = by(self.rows, oem_model="652 2-way (long wires)")
        self.assertEqual({r["relation"] for r in fits}, {"fits_model"})
        self.assertEqual({r["aftermarket_number"] for r in fits}, {"618661", "61647322"})
        self.assertTrue(all(r["oem_number"] is None for r in fits))

    def test_asterisk_kept_and_na_dropped(self):
        rows = by(self.rows, oem_model="838 EG2 (2-way)*")
        self.assertEqual([r["aftermarket_number"] for r in rows], ["61716822"])
        self.assertIn("footnote_marker", rows[0]["qualifiers"])


class Dometic(unittest.TestCase):
    rows, notes = ax.extract(DOMETIC, "Dom_Chart.htm")

    def test_service_alert_is_not_a_replacement(self):
        (r,) = by(self.rows, oem_number="3106375.015")
        self.assertIsNone(r["aftermarket_number"])
        self.assertNotEqual(r["status"], "staged")

    def test_paired_columns_both_read(self):
        self.assertEqual(by(self.rows, oem_number="3850712-01")[0]["aftermarket_number"], "3850712.01")
        self.assertEqual(by(self.rows, oem_number="87500351-19")[0]["aftermarket_number"], "MICRO P1338 REV 5")

    def test_note_marker_split_from_number(self):
        (r,) = by(self.rows, oem_number="3850415-013")
        self.assertEqual(r["aftermarket_number"], "3850415.01")
        self.assertEqual(r["qualifiers"]["chart_note"], "Note1")

    def test_page_caveats_travel_with_every_row(self):
        r = by(self.rows, oem_number="2931842.01")[0]
        caveats = " ".join(r["qualifiers"]["page_caveats"])
        self.assertIn("guidence only", caveats)
        self.assertIn("will not work to replace the 3850415-013", caveats)

    def test_production_ranges_attach_to_model_heading(self):
        rows = by(self.rows, relation="fits_model", oem_model='RM 2551 "Americana"')
        self.assertEqual({r["qualifiers"]["production_numbers"] for r in rows},
                         {"921142101-921142110", "921146167-921146184"})
        self.assertEqual(by(self.rows, oem_model="RM 3607")[0]["aftermarket_number"], "MICRO P-711")


class Ignitor(unittest.TestCase):
    rows, notes = ax.extract(IGNITOR, "UIB_Chart.htm")

    def test_unnamed_manufacturer_is_marked(self):
        self.assertTrue(self.rows)
        self.assertTrue(all(r["oem_brand"] is None and r["oem_brand_basis"] == "not_named" for r in self.rows))

    def test_kit_with_question_mark_is_held(self):
        (r,) = by(self.rows, oem_number="520814")
        self.assertEqual(r["status"], "held")
        self.assertIsNone(r["aftermarket_number"])

    def test_extra_requirement_kept_and_model_code_held(self):
        (r,) = [x for x in self.rows if x["row_text"].startswith("Mark 10DM")]
        self.assertEqual(r["aftermarket_number"], "UIB S")
        self.assertEqual(r["qualifiers"]["also_requires"], "a 6 pin header connector")
        # "Mark 10DM-..." is an appliance model code, not a part number.
        self.assertIsNone(r["oem_number"])
        self.assertEqual(r["status"], "held")

    def test_none_and_names_without_numbers(self):
        self.assertEqual(by(self.rows, oem_number="38242")[0]["status"], "skipped")
        self.assertFalse(by(self.rows, row_text="BLUE BOY | UIB S", status="staged"))


class Onan(unittest.TestCase):
    rows, notes = ax.extract(ONAN, "Msc_Chart.htm")

    def test_onan_rows_and_caveat(self):
        (r,) = by(self.rows, oem_number="300-0944")
        self.assertEqual((r["oem_brand"], r["aftermarket_number"], r["category"]),
                         ("Onan", "300-1073/4950", "external_equipment"))
        self.assertIn("must look at the board", " ".join(r["qualifiers"]["page_caveats"]))


if __name__ == "__main__":
    unittest.main()
