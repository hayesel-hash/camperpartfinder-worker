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


def test_model_matrix_notes_and_options():
    def w(x, y, t):
        return (x, y - 10, x + 6 * len(t), y, t)
    words = [w(288, 452, "Customer"), w(331, 452, "Options"), w(367, 452, "(Required)"), w(414, 452, "57912.(X)31(X)"),
             w(484, 452, "57915.(X)(X)(X)(X)"),
             w(36, 453, "NOTE"), w(59, 453, "1:"), w(83, 453, "Open"), w(107, 453, "End"), w(126, 453, "Shroud"),
             w(157, 453, "(Shell"), w(183, 453, "White)"), w(211, 453, "3108239.009"),
             w(288, 462, "Electronic"), w(325, 462, "Control"), w(353, 462, "Kit"), w(414, 462, "3109226.005"),
             w(484, 462, "3109226.005"),
             w(83, 481, "*Closed"), w(117, 481, "End"), w(136, 481, "Shroud"), w(167, 481, "(Gray)"), w(194, 481, "3308084.023"),
             w(288, 491, "Kit,"), w(301, 491, "Remote"), w(330, 491, "CC"), w(414, 491, "––––––––––"), w(484, 491, "3308417.009"),
             w(36, 510, "*Closed"), w(70, 510, "End"), w(88, 510, "Shroud"), w(120, 510, "can"), w(138, 510, "not"),
             w(154, 510, "be"), w(167, 510, "painted.")]
    rows = M.notes_and_options(words)
    assert ("note", "NOTE (shroud / shroud screws)", "Open End Shroud (Shell White)", "3108239.009", "") in rows
    assert ("option", "Customer Options (Required)", "Electronic Control Kit", "3109226.005", "") in rows
    assert ("option", "Customer Options (Required)", "Kit, Remote CC", "3308417.009",
            " [applies to: 57915.(X)(X)(X)(X)]") in rows
    assert ("note", "NOTE (shroud / shroud screws)",
            "Closed End Shroud (Gray) [*Closed End Shroud can not be painted.]", "3308084.023", "") in rows


def test_option_tables_component_box_and_two_column_table():
    import dometic_option_tables as O

    def w(x, y, t):
        return (x, y - 10, x + 6 * len(t), y, t)
    comp = [w(388, 169, "Component"), w(474, 169, "Description"), w(315, 170, "3102888.009"),
            w(388, 181, "3106615.002"), w(474, 181, "Box"), w(494, 181, "asm.,"), w(522, 181, "complete"),
            w(80, 187, "Decal,"), w(388, 193, "3106463.007"), w(474, 193, "Comfort"), w(513, 193, "center")]
    assert O.read_words(comp) == [("component", "Box asm., complete", "3106615.002", ""),
                                  ("component", "Comfort center", "3106463.007", "")]
    cols = [w(150, 90, "Description"), w(320, 90, "Part"), w(345, 90, "No."), w(410, 90, "Part"), w(435, 90, "No."),
            w(319, 100, "3106615.002"), w(409, 100, "3106615.010"),
            w(100, 112, "C1"), w(130, 112, "Box,"), w(160, 112, "asm."), w(185, 112, "air"),
            w(319, 112, "3101390.056"), w(410, 112, "3105908.010"),
            w(140, 122, "D3"), w(160, 122, "Filter"), w(319, 122, "3100281.009"), w(410, 122, "3100281.009")]
    assert O.read_words(cols) == [("columns", "Box, asm. air", "3101390.056", " [for 3106615.002]"),
                                  ("columns", "Box, asm. air", "3105908.010", " [for 3106615.010]"),
                                  ("columns", "Filter", "3100281.009", "")]


def test_flojet_accessories_sections_by_rules():
    import flojet_datasheet_accessories as F

    def w(x, y, t):
        return (x, y - 10, x + 6 * len(t), y, t)
    words = [w(42, 404, "Accessories"),
             w(43, 437, "Accumulator"), w(119, 437, "305730004A"), w(169, 437, "1"), w(175, 437, "Liter"), w(194, 437, "Tank"),
             w(122, 467, "01740000S"), w(169, 467, "In-line,"), w(197, 467, "3/4\""), w(43, 503, "Strainers"),
             w(124, 582, "20381000"), w(169, 582, "Garden"), w(199, 582, "hose"), w(43, 590, "Port"), w(62, 590, "Fittings"),
             w(320, 590, "All"), w(332, 590, "part"), w(350, 590, "numbers"), w(386, 590, "are"), w(401, 590, "2-pack"),
             w(428, 590, "kits")]
    rows = F.read(words, [413, 449, 569, 600])
    assert rows == [("Accumulator", "305730004A", "Accumulator: 1 Liter Tank"),
                    ("Strainers", "01740000S", "Strainers: In-line, 3/4\""),
                    ("Port Fittings", "20381000", "Port Fittings: Garden hose (2-pack kit)")]
