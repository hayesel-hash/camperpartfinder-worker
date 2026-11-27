"""Unit tests for the pure parsing helpers of the batch-2 cross-reference readers (27 Nov 2026).

The page-geometry passes need the real PDFs (kept out of the repo); these tests pin the
rules that decide what is published and what is held.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts", "aftermarket_pdf"))

import dometic_fridge_replacement_chart as fr  # noqa: E402
import pd_crossover_list as pd  # noqa: E402
import wfco_crossref_sheet as wf  # noqa: E402


def test_fridge_models_split_full_pairs_only():
    assert fr.split_models("462, 463, 662, 663, 641") == (["462", "463", "662", "663", "641"], None)
    assert fr.split_models("N260/N260.3") == (["N260", "N260.3"], None)
    models, why = fr.split_models("1200LR/LAIM")
    assert models == [] and "shorthand" in why


def test_fridge_options_prefix_only_when_printed_in_full():
    full = {"RM2351", "RM2354", "DM2652", "DM2662", "DM2852", "DM2862", "RM3962"}
    o = fr.split_options("RM2351, 2354", full)
    assert [x["number"] for x in o] == ["RM2351", "RM2354"] and o[1]["printed_as"] == "2354"
    o = fr.split_options("DM2852**, 2862**, 3962*", full)
    assert [x["number"] for x in o] == ["DM2852", "DM2862", None]  # DM3962 is never printed
    o = fr.split_options("DM2852**, 2862,** RM3962*", full)  # misplaced comma: marks belong to 2862
    assert [(x["number"], x["marks"]) for x in o] == [("DM2852", "**"), ("DM2862", "**"), ("RM3962", "*")]


def test_pd_group_parsing_keeps_charge_wizard_and_unit_notes():
    g = pd.parse_group({"side": "left", "section": "Deck Mount", "y": 0,
                        "pd_cell": "PD9380V\n(*20 AMP PLUG)\n*This unit does not have\nPower Factor Correction",
                        "replaces": ["WFCO WF-9875\n(w/PD9105V charge wizard added)", "Iota DLS-75"]})
    assert g["pd_number"] == "PD9380V" and "20 AMP PLUG" in g["pd_notes"]
    assert [(r["brand"], r["number"], r["requires_pd9105v_charge_wizard"]) for r in g["rows"]] == [
        ("WFCO", "WF-9875", True), ("Iota", "DLS-75", False)]


def test_wfco_split_and_holds():
    assert wf._split("PD9170A, PD9180A PD9270, PD9280") == ["PD9170A", "PD9180A", "PD9270", "PD9280"]
    assert wf._split("PROSINE 1000, XM 1000") == ["PROSINE 1000", "XM 1000"]  # spaced names stay whole
    t = {"brand": "PARALLAX", "rows": [
        {"wfco": "WF-8945-AD", "cell": "7345, 7145, 6345,", "cont": [{"wfco_col": "8345", "text": ""}]},
        {"wfco": "WF-5220/5320", "cell": "PD1620", "cont": []},
        {"wfco": "WF-5110RS", "cell": "RNG-INVT-1000-", "cont": [{"wfco_col": "12V-P2,", "text": "R-INVT-PGH1-10111S"}]},
    ]}
    rows = wf._finish(t)
    assert [n["number"] for n in rows[0]["numbers"]] == ["7345", "7145", "6345"]
    assert rows[0]["held_continuation"] == ["8345"]
    assert rows[1]["numbers"][0]["hold"].startswith("WFCO number is a model pair")
    assert rows[2]["numbers"][0]["hold"].startswith("number broken over a line")
