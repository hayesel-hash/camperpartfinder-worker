"""Synthetic-geometry tests for readers added by the 27 Nov 08:20 Drive intake run (no maker content)."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts", "aftermarket_pdf"))

import dometic_sealand_parts_list as sealand
import eberspacher_spare_parts_list as eber
import lci_ccd_model_list as ccdm
import lci_component_chart as chart
import truma_parts_viewer as tpv


def w(x0, y, text, width=None):
    width = width or 5 * len(text)
    return (x0, y, x0 + width, y + 8, text)


def test_sealand_side_by_side_item_number_dropped():
    words = [w(100, 100, "385310076"), w(150, 100, "KIT,"), w(172, 100, "DB"), w(186, 100, "VALVE"), w(220, 100, "16"),
             w(240, 100, "385310664"), w(290, 100, "KIT,"), w(312, 100, "MOTOR")]
    rows, orphans, odd = sealand.rows_from(words)
    assert ("385310076", "KIT, DB VALVE") in rows
    assert ("385310664", "KIT, MOTOR") in rows


def test_sealand_dash_layout_and_orphan():
    words = [w(60, 200, "385311979"), w(110, 200, "-"), w(118, 200, "BOWL"), w(145, 200, "SEAL"), w(400, 50, "600347002")]
    rows, orphans, odd = sealand.rows_from(words)
    assert rows == [("385311979", "BOWL SEAL")]
    assert orphans == ["600347002"]


def test_eberspacher_blocks_12v_24v_and_variant_line():
    words = [w(40, 220, "Item"), w(147, 220, "Designation"), w(277, 220, "Order", 20), w(299, 220, "No.", 10),
             w(40, 371, "3"),
             w(147, 371, "Blower"), w(173, 371, "12"), w(184, 371, "V"), w(191, 371, "incl."), w(208, 371, "screws"),
             w(235, 371, "and"), w(147, 384, "blower"), w(173, 384, "seal"),
             w(277, 371, "25.2953.99.1500"), w(277, 384, "25.2955.99.1500"),
             w(147, 397, "Blower"), w(173, 397, "24"), w(184, 397, "V"), w(277, 397, "25.2954.99.1500"),
             w(40, 430, "4"), w(147, 430, "Hood"), w(277, 430, "22.1000.01.0017"), w(160, 443, "Ø"), w(168, 443, "90"),
             w(180, 443, "mm"), w(277, 443, "22.1000.01.0019")]
    rows, cover, no_name = eber.read_page(words)
    assert ("3", "25.2955.99.1500", "Blower 12 V incl. screws and blower seal") in rows
    assert ("3", "25.2954.99.1500", "Blower 24 V") in rows
    assert ("4", "22.1000.01.0017", "Hood") in rows
    assert any(x["number"] == "22.1000.01.0019" and "variant_line" in x for x in no_name)


def test_ccd_model_all_dropped():
    assert ccdm.models_text(["All"]) == ""
    assert ccdm.models_text(["FWH09A, FWH09A-AM,"]) == " [models: FWH09A, FWH09A-AM]"


def test_component_chart_colour_columns_and_shared_cells():
    t = [["ITEM", "DESCRIPTION", "PART NUMBER\n(WHITE)", "PART NUMBER\n(BLACK)"],
         ["1", "L Track Mount", "7523001-01", "7523002-01"],
         ["2", "Mounting Bracket", "7523003-02", "N/A"]]
    rows, shared, hdr = chart.read_tables([t])
    assert ("7523002-01", "L Track Mount (black)") in rows and ("7523003-02", "Mounting Bracket (white)") in rows
    assert len(rows) == 3
    rows, shared, _ = chart.read_tables([[["Callout", "Part #", "Description"], ["O", "2025008011/ 2025008012", "Lead rail"]]])
    assert rows == [] and shared == ["2025008011/ 2025008012"]
    # continuation table without header uses the previous page's header
    rows, _, _ = chart.read_tables([[["19", "Cross Bar Support", "2202160-19"]]], ["ITEM", "DESCRIPTION", "PART NUMBER"])
    assert rows == [("2202160-19", "Cross Bar Support")]


def test_truma_viewer_row_text():
    assert tpv.row_text("Control unit SR ", "") == "Control unit SR"
    assert tpv.row_text("Fuse holder", "without fuse") == "Fuse holder (without fuse)"
