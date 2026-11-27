import os, sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts", "aftermarket_pdf"))

import knott_spare_parts as K
import thule_spare_parts_price_list as T
import lci_ccd_noqty as L


def test_knott_order_numbers():
    for n in ["42191", "23851B02", "D94.013", "D937.003", "45877.10", "41582-2", "405859.001", "33921-1.06",
              "409697B002", "47305V", "69000393", "8710311314", "6J1031.006", "8802539X"]:
        assert K.NUM.match(n), n
    # description lines and page references are not order numbers
    for s in ["M12", "M20x1,5", "Höhe: 101mm", "100x4/M12", "Ø48,5mm", "12", "auf Anfrage"]:
        assert not K.NUM.match(s), s


def test_knott_pass_a_skips_on_request_rows():
    class P:
        def get_text(self, *a):
            return "\n".join(["Pos", "Bezeichnung", "Bestell-", "nummer", "11", "Gehäuse verz.", "auf Anfrage",
                              "12", "Schmiernippel", "48032094", "13", "Kronenmutter", "M20x1,5", "D937.003"])
    assert K.pass_a(P()) == [("12", "Schmiernippel", "48032094"), ("13", "Kronenmutter M20x1,5", "D937.003")]


def test_thule_numbers_and_prices():
    assert T.PN.match("1500603489") and T.PN.match("301982")
    assert not T.PN.match("1500002XXX")
    assert T.PRICE.match("132.80") and T.PRICE.match("N/A")
    assert not T.PRICE.match("2.30M")


def test_thule_pass_b_pairs_number_with_next_line():
    class P:
        def get_text(self, *a):
            return "\n".join(["1", "132.80", "ART.NR.", "DESCRIPTION", "1500603489", "ROLLER TUBE 3200 - 1.90M",
                              "1500603490", "ROLLER TUBE 3200 - 2.30M"])
    assert T.pass_b(P()) == [("1500603489", "ROLLER TUBE 3200 - 1.90M"), ("1500603490", "ROLLER TUBE 3200 - 2.30M")]


def test_lci_left_right_callouts_end_a_description():
    assert L.CALL.match("E/L") and L.CALL.match("F/R") and L.CALL.match("AB")
    assert not L.CALL.match("E/X")
