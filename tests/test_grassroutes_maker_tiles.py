"""Unit tests for the Grassroutes Leisure maker-tile reader (synthetic input only)."""
import os, sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts", "aftermarket_pdf"))

import grassroutes_maker_tiles as g  # noqa: E402


def L(x, bottom, text, bold=False, green=False, size=9.0):
    return {"x": x, "top": bottom - 12, "bottom": bottom, "bold": bold, "green": green, "size": size, "text": text}


def page_whale():
    return [L(48, 51, "WATER PUMPS", size=17.0),
            # tile 1: heading, two description lines, green stock code
            L(188, 296, "WHALE GP1352", bold=True), L(188, 307, "12 v Premium pump"), L(188, 318, "13 litres/min"),
            L(187, 357, "30017", bold=True, green=True),
            # tile 2: heading words that are not a maker number
            L(315, 128, "COMET VIP PLUS", bold=True), L(315, 140, "Immersion 12-volt water"), L(315, 202, "30079", bold=True, green=True),
            # tile 3: one maker number over two stock codes with variant labels -> held
            L(433, 128, "WHALE GP9999", bold=True), L(433, 140, "Submersible pump."),
            L(433, 185, "30078", bold=True, green=True), L(476, 185, "12 V"),
            L(433, 201, "30082", bold=True, green=True), L(476, 201, "24 V"),
            # tile 4: no description under the heading -> held
            L(48, 600, "WHALE EP1632", bold=True), L(48, 640, "33005", bold=True, green=True)]


def test_whale_tile_read_with_description_and_code():
    rows, held = g.read_page(page_whale(), "WHALE")
    assert rows == [{"number": "GP1352", "desc": "12 v Premium pump 13 litres/min"}]
    why = {h["number"]: h["why"] for h in held}
    assert why["GP9999"].startswith("one maker number over several stock codes")
    assert why["EP1632"] == "no description under the heading"


def test_heading_with_product_words_needs_flag_and_joined_numbers_are_not_read():
    lines = [L(48, 232, "CAN LA1405 RECTANGULAR SINK", bold=True), L(49, 252, "Semi-polished rectangular sink."),
             L(49, 264, "Includes LP1800 waste."), L(48, 300, "10686", bold=True, green=True),
             L(309, 232, "CAN FL1323/FL1324 SINGLE HOB/SINK COMBINATION", bold=True), L(309, 252, "Stainless steel combination."),
             L(309, 300, "10657", bold=True, green=True)]
    assert g.read_page(lines, "CAN")[0] == []
    rows, _ = g.read_page(lines, "CAN", name_words=True, pitch=22)
    assert rows == [{"number": "LA1405", "desc": "RECTANGULAR SINK: Semi-polished rectangular sink. Includes LP1800 waste."}]


def test_paragraph_gap_limited_by_pitch():
    lines = [L(48, 325, "CAN FC1343", bold=True), L(48, 345, "Stainless steel hob."), L(48, 366, "Dimensions: 480 x 90 mm."),
             L(48, 410, "10650", bold=True, green=True)]
    # 21 pt paragraph pitch: read with --pitch=22, cut short with the default 20 (then the code is out of reach -> held)
    assert g.read_page(lines, "CAN", True, 22)[0] == [{"number": "FC1343", "desc": "Stainless steel hob. Dimensions: 480 x 90 mm."}]
    rows, held = g.read_page(lines, "CAN", True, 20)
    assert rows == [] and held[0]["why"] == "no Grassroutes code closes the tile"


def test_page_title():
    assert g.title(page_whale()) == "WATER PUMPS"
