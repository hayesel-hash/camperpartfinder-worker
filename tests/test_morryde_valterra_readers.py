"""Unit tests for the MORryde pin box fit chart and Valterra retail catalogue readers (Drive intake, 27 Nov 2026).

The table-finder / word-box passes need the real PDFs (kept out of the repo); these tests pin the rules that decide
what is staged, what is held and how rows are cut.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts", "aftermarket_pdf"))

import morryde_pin_box_chart as mor  # noqa: E402
import valterra_retail_catalogue as val  # noqa: E402


def test_morryde_model_cells():
    assert mor.split_models("1621HD") == (["1621HD"], None)
    assert mor.split_models("7920, 7921") == (["7920", "7921"], None)
    assert mor.split_models("300,314,316") == (["300", "314", "316"], None)
    models, why = mor.split_models("1621, SHD-TA")
    assert models == [] and "one model or several" in why
    models, why = mor.split_models("Rhino")
    assert models == [] and "no part number" in why
    models, why = mor.split_models("AB-34 HD")
    assert models == [] and "not a part number" in why


def test_morryde_chart_rows_and_pairs():
    table = [
        ["Cross Reference Guide", None, "Order according to GVWR of the trailer, not the GVW of the pin box.*", None,
         None, None, "MORryde\nPin Box Rating"],
        ["MFG", "MODEL#", "11,500 or less", "11,501 - 14,000", "14,001 - 18,000", "18,001 & over", None],
        ["Lippert", "1621HD", "RPB72-1621HD-03", "RPB72-1621HD-04", "RPB72-1621HD-05", "N/A", "18k"],
        ["Leland", "7920, 7921", "RPB72-221002300-03", "N/A", "N/A", "N/A", "19k"],
        ["Venture", "Med", "RPB72-VM-03", "N/A", "N/A", "N/A", "15k"],
    ]
    rows = mor.chart_rows(table)
    assert [r["mfg"] for r in rows] == ["Lippert", "Leland", "Venture"]
    staged, held, unread = mor.pairs(rows, 6, "16")
    assert [(s["oem_number"], s["morryde_number"], s["gvwr_band"]) for s in staged] == [
        ("1621HD", "RPB72-1621HD-03", "11,500 or less"), ("1621HD", "RPB72-1621HD-04", "11,501 - 14,000"),
        ("1621HD", "RPB72-1621HD-05", "14,001 - 18,000"),
        ("7920", "RPB72-221002300-03", "11,500 or less"), ("7921", "RPB72-221002300-03", "11,500 or less")]
    assert [h["morryde_number"] for h in held] == ["RPB72-VM-03"] and not unread
    assert mor.chart_rows([["Part #", "Description"], ["1", "x"]]) == []


def w(x0, x1, top, text):
    return (x0, x1, top, top + 8, text)


def test_valterra_rows_take_wrapped_lines_at_the_description_indent_only():
    words = [
        w(167, 200, 100, "T1011"), w(247, 260, 100, "3”"), w(262, 300, 100, "SAN"), w(302, 320, 100, "TEE"),
        w(430, 440, 100, "22"), w(488, 495, 100, "14"), w(536, 550, 100, "8.86"),
        w(247, 255, 109, "x"), w(257, 300, 109, "rotating"), w(302, 330, 109, "flange"),
        w(161, 200, 125, "Paragraph"), w(202, 240, 125, "text"),
        w(167, 200, 140, "T1020VP"), w(247, 260, 140, "SAME"), w(262, 280, 140, "AS"), w(282, 310, 140, "ABOVE"),
        w(430, 440, 140, "1"), w(490, 495, 140, "-"), w(536, 550, 140, "50/200"),
    ]
    rows = val.rows_from_words(words, 167, 430)
    assert rows == [("T1011", "3” SAN TEE x rotating flange"), ("T1020VP", "SAME AS ABOVE")]


def test_valterra_part_number_shape_and_cells():
    for n in ("T1001VP", "A01-0117VP", "F02-3305VP", "RF911", "L32CS100", "T1046-10VP"):
        assert val.PN.match(n), n
    for n in ("Part", "SPIGOT", "3”", "50"):
        assert not val.PN.match(n), n
    for c in ("50", "8.88", "-", "50/200", "4/13"):
        assert val.CELL.match(c), c
    assert val.key(("A1", "Dry, 8-2 Oz")) == val.key(("A1", "Dry,8-2 Oz"))
