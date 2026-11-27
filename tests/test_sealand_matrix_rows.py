"""Synthetic-geometry tests for the SeaLand model-matrix rule, N/A cells, note sentences and the colour-abbreviation check
(27 Nov 12:15 Drive intake run; no maker content)."""
import json, os, subprocess, sys
HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "scripts", "aftermarket_pdf"))

import dometic_sealand_parts_list as sealand


def w(x0, y, text, width=None):
    width = width or 5 * len(text)
    return (x0, y, x0 + width, y + 8, text)


HEADER = [w(300, 80, "ITEM"), w(400, 80, "PART"), w(430, 80, "NUMBER"), w(640, 80, "DESCRIPTION")]


def test_matrix_row_numbers_take_description_column():
    # four model columns, description column header at x 640, text starting 5 pt left of it
    words = HEADER + [w(330, 100, "6"), w(425, 100, "385310001", 37), w(478, 100, "385310002", 37),
                      w(532, 100, "385310003", 37), w(586, 100, "385310004", 37),
                      w(635, 100, "BASE"), w(655, 100, "KIT,"), w(675, 100, "WHITE")]
    rows, orphans, _ = sealand.rows_from(words)
    assert sorted(rows) == [(n, "BASE KIT, WHITE") for n in ("385310001", "385310002", "385310003", "385310004")]
    assert orphans == []


def test_matrix_na_cells_not_description():
    # last model column prints N/A reaching past the column margin; the N/A is not part of the description
    words = HEADER + [w(425, 120, "385310005", 37), w(478, 120, "N/A", 15), w(532, 120, "385310006", 37),
                      w(632, 120, "N/A", 15), w(652, 120, "BASE"), w(672, 120, "KIT,"), w(692, 120, "EBONY")]
    rows, _, _ = sealand.rows_from(words)
    assert sorted(rows) == [("385310005", "BASE KIT, EBONY"), ("385310006", "BASE KIT, EBONY")]


def test_text_far_right_of_description_column_is_another_column():
    # description missing from the text layer; the models cell far right must not become the description
    words = [w(60, 80, "NO."), w(100, 80, "PART"), w(125, 80, "NUMBER"), w(200, 80, "DESCRIPTION"),
             w(100, 140, "385320006", 37), w(350, 140, "974MSD")]
    rows, orphans, _ = sealand.rows_from(words)
    assert rows == [] and orphans == ["385320006"]


def test_part_number_and_description_header_keeps_baseline_rule():
    words = [w(60, 80, "PART"), w(85, 80, "NUMBER"), w(122, 80, "&"), w(130, 80, "DESCRIPTION"),
             w(60, 100, "385311979"), w(110, 100, "-"), w(118, 100, "BOWL"), w(145, 100, "SEAL")]
    assert sealand.desc_column(words) is None
    rows, _, _ = sealand.rows_from(words)
    assert rows == [("385311979", "BOWL SEAL")]


def test_colour_abbreviations_are_not_conflicts(tmp_path):
    def out(rows):
        return {"rows": "\n".join(rows), "other_wordings": []}
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    json.dump(out(["1|1|385311618|SEAT/COVER SLOW-CLOSE KIT - WHITE|0", "1|2|385340177|SUPPLY HOSE - WHITE|0"]), open(a, "w"))
    json.dump(out(["2|1|385311618|KIT, SEAT/CVR SLOW-CLOSE/WHT|0", "2|2|385340177|HOSE, SUPPLY - BONE|0"]), open(b, "w"))
    script = os.path.join(HERE, "..", "scripts", "aftermarket_pdf", "sealand_colour_conflicts.py")
    subprocess.run([sys.executable, "-I", script, str(a), str(b)], check=True, capture_output=True)
    ra, rb = json.load(open(a)), json.load(open(b))
    assert ra["colour_conflicts"] == ["385340177"] and rb["colour_conflicts"] == ["385340177"]
    assert "385311618" in ra["rows"] and "385311618" in rb["rows"]
