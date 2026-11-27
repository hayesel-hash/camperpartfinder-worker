"""Tests for the Dexter V1-24 branch catalogue and Movera 2017-2018 readers (synthetic geometry, no maker content)."""
import os, sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts", "aftermarket_pdf"))
import dexter_v124_tables as dx  # noqa: E402
import movera_hersteller_tables as mv  # noqa: E402


def test_dexter_heading_names_dexter_first():
    assert dx.is_dexter("GENUINE DEXTER HUB-DRUM")
    assert dx.is_dexter("DEXTER REPLACEMENT PARTS")
    assert not dx.is_dexter("KODIAK AND DEXTER BRAKE PARTS")
    assert not dx.is_dexter("FORTRESS OIL CAP FOR DEXTER HUBS")
    assert not dx.is_dexter("TRAILER PARTS PRO HUB-DRUM")
    assert not dx.is_dexter("REPLACEMENT COMPONENTS")


def test_dexter_build_row_attributes_and_dashes():
    hdr = ["PART #", "REF #", "DESCRIPTION", "LUBRICATION", "SEAL ID", "DIAGRAM #"]
    r = dx.build(hdr, ["K08-219-1G", "106254", "COMPLETE HUB-DRUM ASSEMBLY", "GREASE", "—", "3"], "GENUINE DEXTER HUB-DRUM")
    assert r == {"number": "K08-219-1G", "desc": "COMPLETE HUB-DRUM ASSEMBLY; LUBRICATION: GREASE [GENUINE DEXTER HUB-DRUM]"}
    # note rows and a second PART # column are not read
    assert dx.build(hdr, ["Brake assembly not included", "", "", "", "", ""], "GENUINE DEXTER HUB-DRUM") is None
    assert dx.build(["PART #", "REF #", "DESCRIPTION", "PART #"], ["23-472", "1", "BRAKE", "23-473"], "GENUINE DEXTER BRAKES") is None


def _it(x0, y, text, bold=False, size=8.5):
    return (x0, y - 8, x0 + 6 * len(text), y, text, bold, size)


def test_movera_rows_subheading_auf_anfrage_and_labels():
    items = [
        _it(60, 20, "THULE: Markisen", size=22),
        _it(75, 100, "Pos.", True), _it(98, 100, "Movera-Nr.", True), _it(152, 100, "Hersteller-Nr.", True),
        _it(215, 100, "Artikel-Bezeichnung", True),
        _it(77, 111, "Thule Omnistor 2000 (Fortsetzung)", True),
        _it(78, 122, "1"), _it(102, 122, "9956009", True), _it(158, 122, "1500600009"), _it(215, 122, "Montageschiene 300 cm"),
        _it(78, 133, "2"), _it(102, 133, "auf Anfrage", True), _it(158, 133, "1500600742"), _it(215, 133, "Gehäuse 190 cm"),
        _it(300, 133, "E", size=10),  # drawing label on the same baseline: not table text
        _it(78, 144, "3"), _it(102, 144, "auf Anfrage", True), _it(215, 144, "nur komplett"),  # no maker number
    ]
    assert mv.title_of(items) == "THULE"
    rows, unread = mv.read(items)
    assert rows == [{"number": "1500600009", "desc": "Montageschiene 300 cm [Thule Omnistor 2000]"},
                    {"number": "1500600742", "desc": "Gehäuse 190 cm [Thule Omnistor 2000]"}]
    assert len(unread) == 1
