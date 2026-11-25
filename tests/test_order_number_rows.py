"""Regression test for Knott parts tables headed "Bezeichnung | Bestell-/nummer".

Fixture: word positions captured by the range reader from the official Knott
2026 catalogues on Knott's own Shopify tenant:
  * Katalog_Ersatzteile_Anhaengertechnik (208 pp) pages 40-41: exploded brake
    drawings with two side-by-side "Pos | Bezeichnung | Bestell-nummer" tables,
    one- and two-line names, and text stored under a Mac Roman encoding;
  * Katalog_Bauteile_Anhaengertechnik (678 pp) page 122: easydriver mover
    tables where weight and current columns sit between name and number.
Previously no reader fired on these pages (0 parts from the first 40 pages).
"""
import json, os, sys, unittest
HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
sys.path.insert(0, HERE)
import rv_master_disk as worker
from test_suburban_kit_rows import page_from_fixture

FIXTURE = "knott_2026_spl_p40_p41_p100_comp_p122_p289_positions.json"


def rows(page_no):
    with open(os.path.join(HERE, "fixtures", FIXTURE)) as f:
        doc, page = page_from_fixture(json.load(f)[str(page_no)])
    try:
        return worker.order_number_rows(page, page_no)
    finally:
        doc.close()


class KnottOrderNumberTables(unittest.TestCase):
    def test_both_side_by_side_tables_every_number(self):
        nums = [r["number"] for r in rows(40)]
        self.assertEqual(len(nums), 29)
        self.assertEqual(len(set(nums)), 29)
        for n in ("407446P002", "D471.022", "45982.04", "33586.07", "D74361.005", "409879.002"):
            self.assertIn(n, nums)
        p41 = {r["number"] for r in rows(41)}
        self.assertEqual(len(p41), 36)
        for n in ("25766P02", "43299", "D94.019", "43123-1", "33983-1.07", "980145.12", "44559.11"):
            self.assertIn(n, p41)

    def test_drawing_callouts_and_dimensions_are_not_parts(self):
        nums = {r["number"] for r in rows(40)} | {r["number"] for r in rows(41)}
        for not_part in ("205x6/M18", "M42x1,5", "15", "23", "1460/2000"):
            self.assertNotIn(not_part, nums)

    def test_names_take_every_line_of_their_own_row_only(self):
        names = {r["number"]: r["description"] for r in rows(40)}
        self.assertTrue(names["407446P002"].startswith("Bremsnabe kpl. 205x6/M18"))
        self.assertIn("145mm", names["407446P002"])
        self.assertEqual(names["416249.002"], "Buchsen Set für Ausf.: ohne Feststellung")
        self.assertEqual(names["416249.001"], "Buchsen Set für Ausf.: mit Feststellung")
        self.assertEqual(names["407440.001"], "Bremswelle links L = 134,5mm")
        self.assertEqual(names["D74361.006"], "Federring")
        names41 = {r["number"]: r["description"] for r in rows(41)}
        self.assertEqual(names41["46226.10"], "Kronenmutter zu Pos. 1 M30x2")
        self.assertEqual(names41["980145.02"], "Seilzug ( 700/ 960) Nirosta")

    def test_mac_roman_text_is_repaired_in_names(self):
        names = {r["number"]: r["description"] for r in rows(40)}
        self.assertEqual(names["417569.001"], "Kappe Ø90mm")
        self.assertIn("für", names["416249.002"])

    def test_columns_between_name_and_number_stay_out_of_the_name(self):
        names = {r["number"]: r["description"] for r in rows(122)}
        self.assertEqual(len(names), 8)
        self.assertEqual(names["424339.001"], "easydriver active 2.0 für Einachser")
        self.assertEqual(names["424413.001"], "easydriver infinity 2.5 für Einachser (Caravan)")
        self.assertEqual(names["421091.001"], "Fernbedienung easydriver 2.3 und 3.1")
        for name in names.values():
            self.assertNotRegex(name, r"\b(1200|1800|33,00|20 A)\b")

    def test_centred_name_column_is_read_whole(self):
        # Page 289 centres names under "Bezeichnung"; the second line starts
        # left of the heading and the "Maße" values start left of theirs.
        names = {r["number"]: r["description"] for r in rows(289)}
        self.assertEqual(len(names), 14)
        self.assertTrue(names["409705.001"].startswith("7-pol. Stecker 7-pol. Kupplung"))
        self.assertTrue(names["409109.001"].startswith("13-pol. Stecker 13-pol. Kupplung"))
        for n in ("424201", "52-5180-017"):  # ID-Nr. column, not order numbers
            self.assertNotIn(n, names)

    def test_identical_names_are_told_apart_by_the_adjacent_column(self):
        names = {r["number"]: r["description"] for r in rows(289)}
        self.assertEqual(len(set(names.values())), 14)
        self.assertIn("0,50m Arbeitslänge", names["409705.001"])
        self.assertIn("7,50m Arbeitslänge", names["420691.001"])
        self.assertNotIn("0,20", names["409705.001"])  # weight column stays out
        # unique names are left alone
        self.assertEqual(dict((r["number"], r["description"]) for r in rows(122))["424339.001"],
                         "easydriver active 2.0 für Einachser")

    def test_name_set_right_of_centre_falls_back_to_next_heading(self):
        # A row whose only name text sits right of the halfway bound (but
        # still before the next heading) keeps that text as its name.
        items = [["Bezeichnung", 185.4, 645.6, 49.8], ["Maße", 404.1, 645.6, 20.4],
                 ["Bestell-", 544.1, 650.4, 28.9], ["nummer", 542.8, 640.8, 31.6],
                 ["Lichtscheibe", 330.0, 619.8, 40.0], ["12 mm", 410.0, 619.8, 20.0], ["425029.002", 537.5, 619.8, 42.3],
                 ["Lichtscheibe", 330.0, 595.8, 40.0], ["15 mm", 410.0, 595.8, 20.0], ["425029.001", 537.5, 595.8, 42.3]]
        doc, page = page_from_fixture(items)
        try:
            names = {r["number"]: r["description"] for r in worker.order_number_rows(page, 1)}
        finally:
            doc.close()
        self.assertTrue(names["425029.002"].startswith("Lichtscheibe"))
        self.assertFalse(names["425029.002"].startswith(" ") or names["425029.002"].startswith("("))

    def test_long_left_aligned_name_is_kept_whole(self):
        # A left-aligned name that runs past the halfway bound must not lose
        # its middle words; a value that starts in the next column stays out.
        items = [["Bezeichnung", 185.4, 645.6, 49.8], ["Maße", 404.1, 645.6, 20.4],
                 ["Bestell-", 544.1, 650.4, 28.9], ["nummer", 542.8, 640.8, 31.6],
                 ["Klettband zur Sicherung des Losendenrestes von", 185.6, 624.6, 190.0],
                 ["Zurrgurten nach dem Spannen mit Ring", 185.6, 615.0, 150.0],
                 ["25 mm", 410.0, 619.8, 20.0], ["412153.001", 537.5, 619.8, 42.3],
                 ["Staubox Typ 8Z3010 Stahl, pulverbeschichtet schwarz", 185.6, 595.8, 200.0],
                 ["600 mm", 410.0, 595.8, 24.0], ["425071.001", 537.5, 595.8, 42.3]]
        doc, page = page_from_fixture(items)
        try:
            names = {r["number"]: r["description"] for r in worker.order_number_rows(page, 1)}
        finally:
            doc.close()
        self.assertEqual(names["412153.001"], "Klettband zur Sicherung des Losendenrestes von Zurrgurten nach dem Spannen mit Ring")
        self.assertEqual(names["425071.001"], "Staubox Typ 8Z3010 Stahl, pulverbeschichtet schwarz")

    def test_headings_in_a_shifted_font_are_decoded(self):
        # Spare-parts pp. 81-180 print "Bestell-/nummer" and "Bezeichnung" in a
        # subset font 29 code points low ("%HVWHOO", "QXPPHU"); 0 rows before.
        got = {r["number"]: r["description"] for r in rows(100)}
        self.assertEqual(len(got), 25)
        for n in ("8802709X", "98761993", "8700311314", "6J1031.006", "D6325.006", "208352.001", "207556.001"):
            self.assertIn(n, got)
        self.assertEqual(got["206799.001"], "Kugelkupplung absperrbar inkl. Schraubenmaterial")
        self.assertEqual(got["69000393"], "Faltenbalg für Pos. 1+3+4")
        self.assertNotIn("100", got)

    def test_shift_decoder_leaves_numbers_and_real_words_alone(self):
        for t in ("8802709X", "D6325.006", "6J1031.006", "KS30", "LKW", "ALU", "Zugkugelkupplung"):
            self.assertFalse(worker.looks_shifted(t), t)
        self.assertTrue(worker.looks_shifted("DEVSHUUEDU"))
        self.assertEqual(worker.unshift29("%HVWHOO\x10"), "Bestell-")

    def test_rows_are_publishable_labelled_columns(self):
        for r in rows(41):
            self.assertEqual(r["method"], "labelled-column-v1")
            self.assertRegex(r["position"], r"^x[0-9]+ y[0-9]+ col[0-9]+$")


class MacRomanRepair(unittest.TestCase):
    def test_reverses_latin1_under_mac_roman(self):
        self.assertEqual(worker.repair_mac_roman("Bremsgrˆfle: 255x55"), "Bremsgröfle: 255x55")
        self.assertEqual(worker.repair_mac_roman("Kabell‰nge: 350mm"), "Kabellänge: 350mm")
        self.assertEqual(worker.repair_mac_roman("ƒnderungen vorbehalten"), "Änderungen vorbehalten")
        self.assertEqual(worker.repair_mac_roman("Sensor f¸r ABS 0∞"), "Sensor für ABS 0°")
        self.assertEqual(worker.repair_mac_roman("Spreizschloﬂ"), "Spreizschloß")

    def test_byte_shifted_ligatures(self):
        self.assertEqual(worker.repair_byte_shifted_ligatures("Re\u6600\u6c00ex-Re\u6600\u6c00ector"), "Reflex-Reflector")
        self.assertEqual(worker.repair_byte_shifted_ligatures("Zugkugelkupplung"), "Zugkugelkupplung")

    def test_leaves_correct_text_alone(self):
        for text in ("für Einachser", "Kappe 90mm", "Größe ÿ", "Flachbundmutter"):
            self.assertEqual(worker.repair_mac_roman(text), text)


class JokonMirroredTables(unittest.TestCase):
    """Jokon V47 catalogue p. 14: "Art.-Nr. / No. | Beschreibung | ..." with
    the number column on the left, top-aligned rows, the type code under the
    number, and every word printed twice in identical layers."""

    def rows(self):
        with open(os.path.join(HERE, "fixtures", "jokon_v47_p14_positions.json")) as f:
            doc, page = page_from_fixture(json.load(f)["14"])
        try:
            return worker.order_number_rows(page, 14)
        finally:
            doc.close()

    def test_every_number_once(self):
        nums = [r["number"] for r in self.rows()]
        self.assertEqual(len(nums), 14)
        self.assertEqual(len(set(nums)), 14)
        for n in ("13.1069.000", "15.0018.100", "19.2035.400", "62.3002.012"):
            self.assertIn(n, nums)

    def test_names_have_type_german_and_english_without_notes(self):
        names = {r["number"]: r["description"] for r in self.rows()}
        self.assertEqual(names["13.1069.000"], "BL 250 Blinkleuchte Kat. 2a DI Light, Cat. 2a")
        self.assertEqual(names["15.0018.100"], "ZHBL 250b Zusatzbremsleuchte High Level Stop Light")
        self.assertEqual(names["19.2035.000"], "Abdeckkappen (Paar) chrom covers (pair) chrome")
        self.assertTrue(names["62.3001.002"].startswith("LDC/LK 100b-1/12V LED-Kontrollbox"))
        for name in names.values():
            self.assertNotIn("Zusatz-Information", name)
            self.assertNotIn("DC", name.split())


if __name__ == "__main__":
    unittest.main()
