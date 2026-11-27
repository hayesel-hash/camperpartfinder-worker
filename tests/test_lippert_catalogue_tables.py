import os, sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts", "aftermarket_pdf"))
import lippert_catalogue_tables as L


def test_part_label_own_numbers_and_variants():
    assert L.part_label("Part #") == ""
    assert L.part_label("Kit #") == ""
    assert L.part_label("Black #") == "black"
    assert L.part_label("10-Pack #") == "10-pack"
    assert L.part_label("Retail Clamshell #") == "retail clamshell"


def test_part_label_other_numbering_is_not_a_part():
    for h in ("Industry #", "Bearing Kit #", "Stabilization Bar #", "Switch Kit #", "Cartridge Replacement #", "OEM #",
              "Suggested Nut #", "Suggested Idler Hub #", "Race Industry #", "Seal #", "Item #", "t #", "Description",
              "Part#"):
        assert L.part_label(h) is None, h


def test_groups_of_splits_side_by_side_tables():
    hdr = ["Item #", "Part #", "Description", "", "Item #", "Part #", "Description"]
    assert L.groups_of(hdr) == [[0, 1, 2, 3], [4, 5, 6]]
    assert L.groups_of(["Part #", "Description", "Dimensions"]) == [[0, 1, 2]]


def test_heading_for_picks_nearest_heading_above_and_overlapping():
    groups = [[35, 18, 250, 63, "REPLACEMENT AXLE AP KITS & COMPONENTS"], [35, 460, 177, 505, "REPLACEMENT SHACKLE LINKS"],
              [300, 18, 500, 45, "OTHER COLUMN"]]
    assert L.heading_for(groups, (36, 586, 366, 680)) == "REPLACEMENT SHACKLE LINKS"
    assert L.heading_for(groups, (36, 308, 366, 428)) == "REPLACEMENT AXLE AP KITS & COMPONENTS"
    assert L.heading_for(groups, (36, 10, 366, 15)) == ""
