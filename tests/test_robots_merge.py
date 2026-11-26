"""robots.txt: rules split across repeated groups must all apply (Google semantics).

Python's urllib.robotparser keeps only the first "User-agent: *" group. Lippert's
robots.txt (26 Nov 2026) has two: the first allows everything, the second
disallows checkout, customer, search and similar paths.
"""
import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import rv_master_disk as w

LIPPERT_LIKE = """User-agent: *
Allow: /
Content-Signal: search=yes, ai-train=no, use=reference

User-agent: *
Disallow: /checkout/
Disallow: /customer/
Disallow: /catalogsearch/
Disallow: /catalog/product/view/
Disallow: /tirelinc-pro
Sitemap: https://www.lippert.com/media/sitemap/sitemap.xml
""".splitlines()


def disallowed(lines, url, token=w.AGENT):
    return w.strict_disallowed(w.merged_robot_rules(lines, token), url)


class MergedGroups(unittest.TestCase):
    def test_second_star_group_applies(self):
        self.assertTrue(disallowed(LIPPERT_LIKE, "https://www.lippert.com/checkout/cart"))
        self.assertTrue(disallowed(LIPPERT_LIKE, "https://www.lippert.com/catalogsearch/result?q=awning"))
        self.assertTrue(disallowed(LIPPERT_LIKE, "https://www.lippert.com/tirelinc-pro-shop"))

    def test_product_pages_and_sitemap_allowed(self):
        self.assertFalse(disallowed(LIPPERT_LIKE, "https://www.lippert.com/solera-awning-fabric-v000334402-v000334402"))
        self.assertFalse(disallowed(LIPPERT_LIKE, "https://www.lippert.com/media/sitemap/sitemap-1-2.xml"))

    def test_longest_match_and_allow_wins_tie(self):
        lines = ["User-agent: *", "Disallow: /", "Allow: /parts", "Disallow: /parts/private"]
        self.assertFalse(disallowed(lines, "https://x.example/parts/123"))
        self.assertTrue(disallowed(lines, "https://x.example/parts/private/1"))
        self.assertTrue(disallowed(lines, "https://x.example/other"))
        self.assertFalse(disallowed(["User-agent: *", "Disallow: /a", "Allow: /a"], "https://x.example/a"))

    def test_wildcards_and_anchor(self):
        lines = ["User-agent: *", "Disallow: /*.pdf$", "Disallow: /*?sort="]
        self.assertTrue(disallowed(lines, "https://x.example/docs/book.pdf"))
        self.assertFalse(disallowed(lines, "https://x.example/docs/book.pdf?v=2"))
        self.assertTrue(disallowed(lines, "https://x.example/c/awnings?sort=price"))

    def test_empty_disallow_allows_everything(self):
        self.assertFalse(disallowed(["User-agent: *", "Disallow:"], "https://x.example/anything"))

    def test_group_naming_us_overrides_star(self):
        lines = ["User-agent: *", "Disallow: /", "", "User-agent: RVPartFinder", "Allow: /"]
        self.assertFalse(disallowed(lines, "https://x.example/page"))
        lines = ["User-agent: *", "Allow: /", "", "User-agent: RVPartFinder", "Disallow: /"]
        self.assertTrue(disallowed(lines, "https://x.example/page"))

    def test_airstream_file_still_allows_uploads(self):
        lines = ["User-Agent: *", "Disallow:", "Disallow: /kitchen-sink", "Disallow: /config", "Disallow: /shared"]
        self.assertFalse(disallowed(lines, "https://www.airstream.com/wp-content/uploads/2025/06/2025-Classic-Parts-Book.pdf"))
        self.assertTrue(disallowed(lines, "https://www.airstream.com/config/x"))


if __name__ == "__main__":
    unittest.main()
