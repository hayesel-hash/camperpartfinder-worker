"""Positive N3000 fixtures and independent N4000 holdout; negative evidence tests."""
import unittest
from experimental.thetford_explicit_table_v7 import extract_rows

class TestThetfordV7(unittest.TestCase):
    def test_n3000_observed(self):
        rows = [
            {"No.":"7","Description":"Cap (2x)","Spare part number 1":"623622"},
            {"No.":"11","Description":"Shelf rack 415 x 150","Spare part number 1":"692510"},
            {"No.":"27","Description":"Freezer door","Spare part number 1":"69154427R"}]
        self.assertEqual([c.number for c in extract_rows(rows,source_page=25)],
                         ["623622","692510","69154427R"])
    def test_n4000_holdout(self):
        rows = [
            {"No.":"8","Description":"Cap freezer bolt (6x)","Spare part number 1":"624479"},
            {"No.":"7","Description":"Control panel","Spare part number 1":"Refer to page 38"}]
        self.assertEqual([c.number for c in extract_rows(rows,source_page=1)],["624479"])
    def test_retailer_sku_not_part(self):
        self.assertEqual(extract_rows([{"Description":"Latch","SKU":"ABC123"}],source_page=25),[])
    def test_price_not_part(self):
        self.assertEqual(extract_rows([{"Description":"Cap","Spare part number 1":"£12.99"}],source_page=25),[])
    def test_serial_model_not_part(self):
        for description in ("Serial number E197V1234","Model N3145"):
            self.assertEqual(extract_rows([{"Description":description,"Spare part number 1":"623622"}],source_page=25),[])
    def test_ambiguous_qualified_not_part(self):
        for value in ("691468 ≥ 31-06-2016","626985 (shared with items 2–4)"):
            self.assertEqual(extract_rows([{"Description":"Latch","Spare part number 2":value}],source_page=25),[])
    def test_no_fitment_publication(self):
        c=extract_rows([{"Description":"Cap","Spare part number 1":"623622"}],source_page=25)[0]
        self.assertEqual(c.status,"staged")
        self.assertFalse(hasattr(c,"replacement"))
    def test_authority_required(self):
        self.assertEqual(extract_rows([{"Description":"Cap","Spare part number 1":"623622"}],source_page=25,authority="retailer"),[])
    def test_idempotent(self):
        row={"No.":"7","Description":"Cap","Spare part number 1":"623622"}
        self.assertEqual(len(extract_rows([row,row],source_page=25)),1)

if __name__=="__main__":
    unittest.main()
