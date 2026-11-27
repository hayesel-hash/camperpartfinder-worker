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


RECPRO = """<html><head><script type="application/ld+json">{"@type":"Product","name":"RecPro RV Water Pump 12V 3 Chamber","sku":"RP-1004","brand":{"@type":"Brand","name":"RecPro"}}</script></head>
<body><h1>RecPro RV Water Pump 12V 3 Chamber</h1>
<p>Direct replacement for Flojet, Shurflo and WFCO/Arterra: Flomax equivalent.</p>
<h3>Direct Replacement Chart</h3>
<table><tr><th>Shurflo</th><th>WFCO</th><th>Flojet</th><th>Flow Max</th><th>Seaflo</th></tr>
<tr><td>4008-101-A65</td><td>PDS3B-130-1260E</td><td>03526-144A</td><td>689052</td><td>SFDP1-030-045-33</td></tr></table>
<h3>Specifications</h3><table><tr><td>Voltage</td><td>12V</td></tr><tr><td>Weight</td><td>4 lb</td></tr></table>
</body></html>"""

ETRAILER = """<html><body><h1>Replacement Control Panel for Atwood Water Heaters</h1>
<div>Replaces Dometic Atwood Control Boards 91349, 91420, 91504, 93254, 93307, 93865</div></body></html>"""


class Tables(unittest.TestCase):
    def test_replacement_chart_row(self):
        f = sr.extract(RECPRO, "https://www.recpro.com/recpro-12v-electric-3-chamber-rv-water-pump/")
        self.assertEqual(f["sku"], "RP-1004")
        t = [c for c in f["compat"] if c.startswith("TABLE|")]
        self.assertEqual(len(t), 1, f["compat"])
        self.assertIn("|Shurflo=4008-101-A65|WFCO=PDS3B-130-1260E|Flojet=03526-144A|Flow Max=689052|Seaflo=SFDP1-030-045-33", t[0])
        self.assertIn("Direct Replacement Chart", t[0])

    def test_spec_table_is_not_a_cross_reference(self):
        f = sr.extract(RECPRO, "https://www.recpro.com/x/")
        self.assertFalse(any("Voltage" in c for c in f["compat"]))

    def test_number_list_sentence_kept(self):
        f = sr.extract(ETRAILER, "https://www.etrailer.com/p-AT91367.html")
        self.assertIn("Replaces Dometic Atwood Control Boards 91349, 91420, 91504, 93254, 93307, 93865", f["compat"])


class Labels(unittest.TestCase):
    def test_label_line_joined_to_numbers(self):
        page = "<html><body><h1>MC Enterprise 521099MC Igniter Board</h1><div><dt>Replaces</dt><dd>Suburban Boards: 230483, 230587, 520741</dd></div></body></html>"
        f = sr.extract(page, "https://pantherrvproducts.com/521099mc/")
        self.assertIn("Replaces Suburban Boards: 230483, 230587, 520741", f["compat"])


class Sitemaps(unittest.TestCase):
    def test_index_children_with_query_strings(self):
        pages = {
            "https://s.example/xmlsitemap.php": "<sitemapindex><sitemap><loc>https://s.example/xmlsitemap.php?type=products&amp;page=1</loc></sitemap>"
                                                "<sitemap><loc>https://other.example/x.xml</loc></sitemap></sitemapindex>",
            "https://s.example/xmlsitemap.php?type=products&page=1": "<urlset><url><loc>https://s.example/pump-a/</loc></url><url><loc>https://s.example/blog/x</loc></url></urlset>",
        }
        sent = []

        class W:
            Held = Exception
        orig_read, orig_gw, orig_sleep = sr.read, sr.gateway, sr.time.sleep
        sr.read = lambda w, u, l: pages[u].encode()
        sr.gateway = lambda a, args=None, timeout=120: sent.append(args) or {"added": len(args["urls"])}
        sr.time.sleep = lambda s: None
        try:
            sr.load_frontier(W, {"id": "t", "host": "s.example", "sitemap_url": "https://s.example/xmlsitemap.php",
                                 "product_url_pattern": r"^https://s\.example/[a-z0-9-]+/$"})
        finally:
            sr.read, sr.gateway, sr.time.sleep = orig_read, orig_gw, orig_sleep
        self.assertEqual(sent[0]["urls"], ["https://s.example/pump-a/"])


if __name__ == "__main__":
    unittest.main()
