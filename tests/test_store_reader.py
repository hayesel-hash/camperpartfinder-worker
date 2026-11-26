"""Store reader page extraction.

Fixtures are short, hand-written pages in the shape of a Magento product page
(Lippert's store) and a JSON-LD product page. They test the extraction rules;
the first live run is reviewed against real pages before the store is marked
reviewed.
"""
import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import store_reader as sr

PATTERN = r"^https://www\.lippert\.com/[a-z0-9-]+-(v?[0-9]{5,10})-\1$"
URL = "https://www.lippert.com/solera-universal-vinyl-replacement-fabric-for-16ft-rv-awning-blue-fade-v000334402-v000334402"

MAGENTO = """<html><head>
<meta property="og:title" content="Solera Universal Vinyl Replacement Fabric for 16ft RV Awning - Blue Fade">
<meta property="product:retailer_item_id" content="V000334402">
<script>var dataLayer = {"sku":"WRONG"};</script>
<style>.x{color:red}</style>
</head><body>
<h1 class="page-title"><span>Solera&reg; Universal Vinyl Replacement Fabric for 16ft RV Awning - Blue Fade</span></h1>
<div class="product-info"><div>SKU #: V000334402</div><div>Brand: Solera&reg;</div></div>
<div class="quick-facts"><ul>
<li>Compatible with Dometic&reg;, Carefree&reg;, and Solera awnings (but not compatible with Solera 2000 Series)</li>
<li>Fits multiple awning sizes ranging from 10' to 21'</li>
</ul></div>
<div class="description"><p>Durable vinyl. Replaces worn fabric quickly.</p></div>
</body></html>"""

JSONLD = """<html><head>
<script type="application/ld+json">{"@context":"https://schema.org","@graph":[
 {"@type":"BreadcrumbList"},
 {"@type":"Product","name":"Kwikee 25 Series Step Motor","sku":"379608","brand":{"@type":"Brand","name":"Kwikee"}}]}</script>
</head><body><h1>Kwikee 25 Series Step Motor</h1><p>Direct replacement for Kwikee step motors 1101070 and 909525.</p></body></html>"""


class Magento(unittest.TestCase):
    facts = sr.extract(MAGENTO, URL, PATTERN)

    def test_sku_name_brand(self):
        self.assertEqual(self.facts["sku"], "V000334402")
        self.assertEqual(self.facts["brand"], "Solera")
        self.assertTrue(self.facts["name"].startswith("Solera Universal Vinyl Replacement Fabric"))
        self.assertNotIn("®", self.facts["name"])

    def test_scripts_ignored(self):
        self.assertNotEqual(self.facts["sku"], "WRONG")

    def test_compatibility_wording_kept(self):
        joined = " | ".join(self.facts["compat"])
        self.assertIn("Compatible with Dometic, Carefree, and Solera awnings", joined)
        self.assertIn("Fits multiple awning sizes", joined)
        self.assertIn("Replaces worn fabric quickly", joined)


class JsonLd(unittest.TestCase):
    def test_product_from_graph(self):
        f = sr.extract(JSONLD, "https://store.example/kwikee-step-motor-379608")
        self.assertEqual((f["sku"], f["brand"], f["name"]), ("379608", "Kwikee", "Kwikee 25 Series Step Motor"))
        self.assertIn("Direct replacement for Kwikee step motors 1101070 and 909525.", f["compat"])


class Guards(unittest.TestCase):
    def test_sku_mismatch_with_url_is_not_trusted(self):
        page = MAGENTO.replace("V000334402", "V000999999")
        f = sr.extract(page, URL, PATTERN)
        self.assertIsNone(f["sku"])
        self.assertIn("differs from URL SKU", f["note"])

    def test_page_without_sku(self):
        f = sr.extract("<html><body><h1>Awning arms</h1><p>Category page</p></body></html>", "https://www.lippert.com/awnings", PATTERN)
        self.assertIsNone(f["sku"])

    def test_sitemap_locs(self):
        xml = "<urlset><url><loc>" + URL + "</loc></url><url><loc>https://www.lippert.com/rv-awnings</loc></url></urlset>"
        import re
        self.assertEqual([u for u in sr.LOC.findall(xml) if re.match(PATTERN, u)], [URL])


if __name__ == "__main__":
    unittest.main()
