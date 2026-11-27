import importlib.util
import pathlib

spec = importlib.util.spec_from_file_location(
    "thetford_cooker_lines",
    pathlib.Path(__file__).resolve().parents[1] / "scripts/aftermarket_pdf/thetford_cooker_lines.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

# Synthetic page in the cooker-list geometry: item column x 60, description x 90, number columns x 330 / 413,
# colours x 490.  Words are (x0, y0, x1, y1, text, is_grey).
HEADER = [(331, 63, 356, 77, "Spare", False), (358, 63, 375, 77, "part", False), (340, 77, 370, 91, "number", False),
          (413, 63, 438, 77, "Spare", False), (440, 63, 457, 77, "part", False), (420, 77, 450, 91, "number", False),
          (490, 63, 523, 77, "Colours", False), (490, 77, 530, 91, "available", False)]


def line(y, item=None, desc=(), nums=(), grey=False, extra=()):
    out = []
    if item:
        out.append((60, y, 66, y + 10, item, False))
    x = 90
    for t in desc:
        out.append((x, y, x + 6 * len(t), y + 10, t, False)); x += 6 * len(t) + 3
    for col, t in nums:
        x0 = 333 if col == 0 else 415
        out.append((x0, y, x0 + 42, y + 10, t, grey))
    for x0, t in extra:
        out.append((x0, y, x0 + 6 * len(t), y + 10, t, False))
    return out


def test_sub_rows_take_the_item_name_and_underlined_sign_reads_as_ge():
    words = HEADER + line(110, "25", ["Oven", "burner"]) \
        + line(124, None, ["Production", "date:", ">", "01-08-21"], [(0, "SSPA0198")])
    gt = [w for w in words if w[4] == ">"][0]
    rules = [(gt[0], gt[2], gt[3] + 0.5)]            # short rule right under the ">" glyph
    glyphs = [(">",) + tuple(gt[:4])]
    rows, held = m.read(words, rules, glyphs)
    assert held == []
    assert rows == [("SSPA0198", "25", "Oven burner: Production date: ≥ 01-08-21", False, "")]


def test_plain_gt_without_underline_stays_gt():
    words = HEADER + line(110, "29", ["Grill"]) + line(124, None, ["Production", "date:", ">", "02-07-2015"], [(0, "SSPA0644")])
    gt = [w for w in words if w[4] == ">"][0]
    rows, _ = m.read(words, [], [(">",) + tuple(gt[:4])])
    assert rows[0][2] == "Grill: Production date: > 02-07-2015"


def test_variant_rows_under_a_numbered_item_line_are_not_sub_rows():
    words = HEADER + line(110, "5", ["Pan", "support", "clips", "(4x)"], [(0, "SSPA0041")]) \
        + line(124, None, ["Pan", "support", "clips", "(50x)"], [(0, "SSPA0042")])
    rows, _ = m.read(words, [], [])
    assert [r[2] for r in rows] == ["Pan support clips (4x)", "Pan support clips (50x)"]


def test_second_number_column_needs_its_sub_heading():
    words = HEADER + line(110, "9", ["Thermocouples", "hob"], extra=[(405, "For"), (425, "lid"), (443, "shut")]) \
        + line(124, None, ["Front"], [(0, "SSPA0675"), (1, "SSPA0671")])
    rows, held = m.read(words, [], [])
    assert ("SSPA0671", "9", "Thermocouples hob: Front", False, " [For lid shut]") in rows
    words = HEADER + line(110, "9", ["Thermocouples", "hob"]) + line(124, None, ["Front"], [(0, "SSPA0675"), (1, "SSPA0671")])
    rows, held = m.read(words, [], [])
    assert ("SSPA0671", "second number column without a sub-heading") in held


def test_number_without_description_on_its_line_is_held():
    words = HEADER + line(110, "23", ["Electrode", "oven"]) + line(124, None, [], [(0, "SSPA0622")])
    rows, held = m.read(words, [], [])
    assert rows == [] and held == [("SSPA0622", "no description on the number's line (merged cell)")]


def test_qualifier_printed_under_the_number_holds_it():
    words = HEADER + line(110, "23", ["Electrode", "oven"], [(0, "SSPA0626")]) + line(124, None, [], extra=[(333, "≥"), (345, "06-12-16")])
    rows, held = m.read(words, [], [])
    assert rows == [] and held == [("SSPA0626", "qualifier printed under the number in its cell")]
