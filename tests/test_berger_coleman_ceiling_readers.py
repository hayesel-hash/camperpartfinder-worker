"""Tests for the Fritz Berger catalogue reader helpers and the Coleman ceiling-assembly extension (synthetic input, no maker
content beyond invented sample numbers)."""
import os, sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts", "aftermarket_pdf"))
import berger_hersteller_tables as bg  # noqa: E402
import coleman_so_quick_reference as cq  # noqa: E402


def test_berger_header_names_the_maker():
    m = bg.HDR.match("Pos. Berger-Nr. FIAMMA-Nr. Artikel-Bezeichnung")
    assert m and m.group(1) == "FIAMMA"
    assert bg.HDR.match("Pos. Berger-Nr. Truma-Nr. Artikel-Bezeichnung").group(1) == "Truma"
    assert bg.HDR.match("Berger Dometic Nr. Bestellmaß mm Glasmaß mm Bezeichnung") is None


def test_berger_pos_allows_spaced_letter():
    assert bg.POS.match("8 c") and bg.POS.match("10a") and bg.POS.match("3")
    assert not bg.POS.match("ns")


def test_heading_lines_by_baseline_drop_far_callout_letters():
    # "CARRY-BIKE" and " PRO - " share a baseline but the second span is taller; a callout "H" sits far right
    items = [(45, 23, "CARRY-BIKE", 111), (45, 115, " PRO - ", 165), (44, 165, "(Nr. 116100)", 232), (44.5, 400, "H", 406)]
    heads = bg.join_heading_lines(items)
    assert heads == [(44, "CARRY-BIKE PRO - (Nr. 116100)")]
    assert bg.heading_for(heads, 60) == "CARRY-BIKE PRO"  # Berger's own stock number dropped
    # single callout letters are never headings
    assert bg.join_heading_lines([(300, 50, "S", 56)]) == []


def _w(x0, bottom, text):
    return {"x0": x0, "x1": x0 + 5 * len(text), "top": bottom - 7, "bottom": bottom, "text": text}


def test_coleman_ceiling_rows_mfg_and_so_columns():
    text = "COLEMAN CEILING ASSEMBLY NUMBERS"
    ws = [_w(111, 482, "INDEX"), _w(193, 482, "PARTS"), _w(215, 482, "DESCRIPTION"), _w(313, 482, "ORDER"), _w(386, 482, "MFG"),
          _w(437, 497, "1111-2222"),  # assembly header over the bullet columns: not a row
          _w(121, 511, "1"), _w(160, 511, "Decal"), _w(181, 511, "Package"), _w(324, 511, "S/O"), _w(379, 511, "1234-5671"),
          _w(121, 546, "3"), _w(160, 545, "Filter"), _w(179, 545, "Package"), _w(320, 546, "65354"), _w(379, 546, "#1234-5681"),
          _w(160, 563, "Vane"), _w(178, 563, "(White"), _w(324, 561, "S/O"), _w(379, 561, "1234-5691")]
    rows, held, _ = cq.read_ceiling_page(ws, text)
    assert {r["number"]: r["desc"] for r in rows} == {
        "1234-5671": "Decal Package [9000 Series Coleman ceiling assemblies]",
        "1234-5681": "Filter Package [9000 Series Coleman ceiling assemblies]"}
    assert held == [{"number": "1234-5691", "why": "description with unbalanced brackets (misprint)", "text": "Vane (White"}]


def test_coleman_ceiling_so_in_order_column():
    ws = [_w(97, 488, "INDEX"), _w(161, 488, "PARTS"), _w(183, 488, "DESCRIPTION"), _w(270, 488, "ORDER"),
          _w(107, 584, "5"), _w(134, 584, "Plug"), _w(151, 584, "Assembly"), _w(260, 584, "S/O"), _w(277, 584, "1234-567"),
          _w(107, 601, "6"), _w(134, 601, "Thermostat"), _w(276, 603, "65356")]
    rows, held, _ = cq.read_ceiling_page(ws, "COLEMAN CEILING ASSEMBLY NUMBERS")
    assert rows == [{"number": "1234-567", "desc": "Plug Assembly [9000 Series Coleman ceiling assemblies]"}]
