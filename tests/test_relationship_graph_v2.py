"""Regression gates for relationship_graph_v2 (staging-only extractor)."""
import os
import sys
import unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, "benchmarks"))

import pymupdf  # noqa: E402
import relationship_graph_v2 as v2  # noqa: E402
import run_relationship_benchmark as bench  # noqa: E402
from relationship_cases import CASES as DEV  # noqa: E402
from relationship_holdout_cases import CASES as HOLDOUT  # noqa: E402


def page_with(*items):
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    for x, y, t in items:
        page.insert_text((x, y), t, fontsize=9)
    return doc, page


class TestBenchmarkGates(unittest.TestCase):
    def _summary(self, cases):
        saved = bench.CASES
        bench.CASES = cases
        try:
            per_kind, per_case = bench.score(bench.v2_edges)
        finally:
            bench.CASES = saved
        return bench.summary(per_kind), per_case

    def test_dev_set_full_recall_no_false_positives(self):
        s, _ = self._summary(DEV)
        self.assertEqual(s["ALL"]["clean_false_positives"], 0)
        self.assertGreaterEqual(s["ALL"]["clean_recall"], 1.0)

    def test_holdout_precision_gate(self):
        # Mandate: >=98% precision for anything that could be auto-published.
        s, cases = self._summary(HOLDOUT)
        self.assertEqual(s["ALL"]["clean_false_positives"], 0, cases)
        # Recall floor recorded at freeze time (0.62); must not regress.
        self.assertGreaterEqual(s["ALL"]["clean_recall"], 0.62)


class TestSemantics(unittest.TestCase):
    def test_direction_is_preserved_for_reverse_wording(self):
        doc, p = page_with((40, 60, "New valve 80020 replaces 80010"))
        e = v2.extract_page(p, 1)
        self.assertEqual([(x["kind"], x["a"], x["b"]) for x in e], [("supersedes", "80010", "80020")])
        doc.close()

    def test_qualifier_is_kept_not_dropped(self):
        doc, p = page_with((40, 60, "12345 replaced by 67890 only with adapter 11111"))
        e = v2.extract_page(p, 1)
        self.assertEqual(len(e), 1)
        self.assertTrue(e[0]["qualifiers"])
        doc.close()

    def test_scope_does_not_block(self):
        doc, p = page_with((40, 60, "40123 superseded by 40188 from 2019 production"))
        e = v2.extract_page(p, 1)
        self.assertEqual(e[0]["qualifiers"], [])
        self.assertIn("2019", e[0]["scope"])
        doc.close()

    def test_distributor_crossref_never_claimed_for_manufacturer_authority(self):
        doc, p = page_with((40, 40, "Art.-Nr. 318044"), (40, 56, "Hersteller-Nr. 30030-21500"))
        self.assertFalse([x for x in v2.extract_page(p, 1, "manufacturer") if x["kind"] == "oem_xref"])
        d = [x for x in v2.extract_page(p, 1, "distributor") if x["kind"] == "oem_xref"]
        self.assertEqual(len(d), 1)
        self.assertEqual(d[0]["assertion_class"], "distributor_assertion")
        doc.close()

    def test_no_interchangeability_edge_type_exists(self):
        for case in DEV + HOLDOUT:
            doc, page = bench.build(case)
            for e in v2.extract_page(page, 1, case[1]):
                self.assertIn(e["kind"], {"supersedes", "oem_xref", "fits"})
            doc.close()

    def test_empty_and_image_pages(self):
        doc = pymupdf.open()
        self.assertEqual(v2.extract_page(doc.new_page(), 1), [])
        doc.close()


if __name__ == "__main__":
    unittest.main()
