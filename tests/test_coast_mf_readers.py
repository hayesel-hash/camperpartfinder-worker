"""Unit tests for the Coast to Coast maker-column reader and the MF Campingwelt Hersteller-Nr. reader (synthetic input only)."""
import os, sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts", "aftermarket_pdf"))

import coast_maker_column_tables as coast  # noqa: E402
import mf_campingwelt_tables as mf  # noqa: E402


def test_coast_join_number_only_after_hyphen():
    assert coast.join_number(["R012530-", "TB76L"]) == "R012530-TB76L"
    assert coast.join_number(["R030345-", "007-MP"]) == "R030345-007-MP"
    assert coast.join_number(["901020"]) == "901020"
    assert coast.join_number(["901020", "W"]) is None  # no hyphen: two pieces are not one number
    assert coast.join_number(["R012530-"]) is None  # cut-off number
    assert coast.join_number([]) is None


def test_coast_number_line():
    assert coast.is_number_line(["4a", "R040792-005", "200-38506"])
    assert coast.is_number_line(["R001618WHT", "200-38502"])
    assert not coast.is_number_line(["Freedom", "Plug", "White"])
    assert not coast.is_number_line(["2.43m", "to", "4.0m"])


def W(x0, top, text, w=None):
    return (x0, top, x0 + (w or 6 * len(text)), top + 9, text)


def test_mf_reads_four_column_table_and_skips_extra_columns():
    words = [W(260, 100, "Hersteller"), W(320, 100, "Nr."), W(372, 100, "Art-Nr."),
             W(50, 112, "1"), W(70, 112, "Kit"), W(90, 112, "Rafter"), W(130, 112, "Side"), W(262, 112, "98660-009"),
             W(372, 112, "071/354"),
             W(50, 123, "2"), W(70, 123, "Endkappe"), W(130, 123, "links"), W(262, 123, "98673-240"), W(372, 123, "071/591"),
             W(70, 134, "Stuetzfuss"), W(262, 134, "06270-07-"), W(372, 134, "071/400")]
    rows = mf.read_tables(words, 2.0, lambda x, y: "Fiamma")
    assert ("98660-009", "Kit Rafter Side", "Fiamma") in rows
    assert ("98673-240", "Endkappe links", "Fiamma") in rows
    # numbers ending in "-" are returned but filtered by main(); here they come back as read
    assert ("06270-07-", "Stuetzfuss", "Fiamma") in rows
    extra = words + [W(200, 100, "Menge")]
    assert all(n == "?" for n, _, _ in mf.read_tables(extra, 2.0, lambda x, y: "Fiamma"))


def test_mf_row_with_description_above_number_is_not_read():
    words = [W(260, 100, "Hersteller"), W(320, 100, "Nr."), W(372, 100, "Art-Nr."),
             W(70, 112, "Gelenkarm"), W(130, 112, "320"),
             W(70, 122, "links"), W(262, 122, "98673-244"), W(372, 122, "071/595")]
    rows = mf.read_tables(words, 2.0, lambda x, y: "Fiamma")
    assert rows and rows[0][0] == "?"


def test_mf_no_maker_no_rows():
    words = [W(260, 100, "Hersteller"), W(320, 100, "Nr."), W(372, 100, "Art-Nr."),
             W(70, 112, "Kit"), W(262, 112, "98660-009"), W(372, 112, "071/354")]
    assert mf.read_tables(words, 2.0, lambda x, y: None) == []
