"""Tests for the 27 Nov 11:19 run readers: dometic_llc_index_list, wedgewood_range_matrix, dometic_model_matrix_list."""
import os, sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts", "aftermarket_pdf"))

import dometic_llc_index_list as L  # noqa: E402
import dometic_model_matrix_list as M  # noqa: E402
import wedgewood_range_matrix as W  # noqa: E402


def test_llc_pass_a_rows_dashes_and_shared_index():
    text = "\n".join([
        "6", "RM2351 Parts List", "CABINET, EXTERIOR COMPONENTS",
        "Only Those Parts Identified With An Index Number Are Available For Service Replacement.",
        "Model RM2351 Prod # 921145039 = A", "Model RM2351 Prod # 921145040 = B",
        "40", "3850270012", "--", "B", "Hinge RH",
        "17", "2932754019", "A", "B", "Spring LH",
        "2932754027", "A", "B", "Spring RH",
        "Index", "No.", "Part No.", "A", "B", "Description"])
    km = L.keymap(text)
    assert km == {"A": ("RM2351", "921145039"), "B": ("RM2351", "921145040")}
    rows = L.pass_a(text, set(km))
    assert rows == [("40", "3850270012", "B", "Hinge RH"), ("17", "2932754019", "AB", "Spring LH"),
                    ("17", "2932754027", "AB", "Spring RH")]
    assert L.heading(text) == "CABINET, EXTERIOR COMPONENTS"


def test_wedgewood_split_desc():
    assert W.split_desc(86, "Grate                                                Black ", 82.6) == ("Grate", "Black")
    assert W.split_desc(224, "Black ", 82.6) == (None, "Black")
    assert W.split_desc(86, "                                                         White ", 82.6) == (None, "White")
    assert W.split_desc(86, "Burner Gasket ", 82.6) == ("Burner Gasket", None)


def test_wedgewood_serial_notes_stripped_only_as_qualifiers():
    a = "Valve, Burner - Mini 9000 BTU (1) (after serial #F11030969) (Dbl D)"
    b = "Valve, Burner - Mini 9000 BTU (1) (after serial #F11040784) (Dbl D)"
    assert W.norm(W.SERIAL.sub("", a)) == W.norm(W.SERIAL.sub("", b)) == "Valve, Burner - Mini 9000 BTU (1)"


def test_model_matrix_pass_a_dates_marks_and_see_note():
    cells = lambda s: [("–" if c == "-" else c) for c in s]
    lines = ["4", "Index", "Description", "Part No.", "No.",
             "1", "Shroud", "SEE NOTE 1", *list("ABCDEFGHIJ"),
             "3", "Decal, Shroud Duo-Therm (2 req.)", "3101380.016", *cells("ABCDEF--IJ"), "2/14/03**",
             "11", "Asm, Compressor-2P15S3R126B-1F", "3104355.023", *cells("A---------"),
             "A1", "Overload", "3100250.400", *cells("A---------"),
             "57912.531(X)"]
    rows, err = M.pass_a("\n".join(lines), 10)
    assert err is None
    assert rows == [("3", "Decal, Shroud Duo-Therm (2 req.)", "3101380.016", "xxxxxx--xx", "2/14/03**"),
                    ("11", "Asm, Compressor-2P15S3R126B-1F", "3104355.023", "x---------", None),
                    ("A1", "Overload", "3100250.400", "x---------", None)]
    assert M.date_text("2/14/03**") == " (discontinued 2/14/03)"
    assert M.date_text("8/25/03##") == " (start date 8/25/03)"
