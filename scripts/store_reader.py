"""Read makers' own online parts stores (first: Lippert) and STAGE page facts.

Most RV component part numbers are published in makers' web stores, not PDFs.
For each enabled store (config comes from the database via the gateway):
  1. weekly, load product URLs from the store's sitemap into the frontier;
  2. claim product URLs, fetch each page politely, extract SKU, name, brand and
     any "compatible with / replaces / fits" wording, and stage them.
Nothing is published here: rv_private.publish_store_identities_v1 does that,
only for a reviewed store and only for the maker's own brands.

Every fetch goes through rv_master_disk.open_catalogue: host allowlist, robots
rules (all applicable groups), Crawl-delay handling, no cross-host redirects.
"""
import hashlib
import html
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from html.parser import HTMLParser

GATEWAY = "https://dlijhukwzlqwtmiynncg.supabase.co/functions/v1/rv-store-gateway"
AUDIENCE = "rv-store-reader-dlijhukwzlqwtmiynncg"
RUN_SECONDS = 14 * 60       # stop claiming new work after this
PAGE_PAUSE = 1.5            # seconds between page requests to one store
CLAIM = 40
MAX_PAGE = 3_000_000
MAX_SITEMAP = 60_000_000

LOC = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>", re.I)
SKU_TEXT = re.compile(r"\bSKU\s*#?\s*:?\s*([A-Za-z0-9][A-Za-z0-9./-]{2,39})\b", re.I)
BRAND_TEXT = re.compile(r"\bBrand\s*:\s*([A-Za-z][A-Za-z0-9 &'.-]{1,40}?)(?:\s*[®™]|\s{2,}|\s*\||$)", re.M)
COMPAT = re.compile(r"[^.!?\n]*\b(?:compatible with|replaces|replacement for|direct replacement|fits)\b[^.!?\n]*[.!?]?", re.I)


class _Page(HTMLParser):
    """Collects meta tags, JSON-LD blocks, the first <h1> and visible text."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.meta, self.ld, self.h1, self.text = {}, [], None, []
        self._skip = 0
        self._ld = None
        self._h1 = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "meta":
            key = (a.get("property") or a.get("name") or a.get("itemprop") or "").lower()
            if key and a.get("content") is not None and key not in self.meta:
                self.meta[key] = a["content"]
        elif tag == "script":
            if (a.get("type") or "").lower() == "application/ld+json":
                self._ld = []
            else:
                self._skip += 1
        elif tag in ("style", "noscript", "template"):
            self._skip += 1
        elif tag == "h1" and self.h1 is None:
            self._h1 = []
        elif tag in ("br", "p", "div", "li", "tr", "td", "th", "dt", "dd", "span", "h2", "h3"):
            self.text.append("\n")

    def handle_endtag(self, tag):
        if tag == "script":
            if self._ld is not None:
                self.ld.append("".join(self._ld))
                self._ld = None
            elif self._skip:
                self._skip -= 1
        elif tag in ("style", "noscript", "template") and self._skip:
            self._skip -= 1
        elif tag == "h1" and self._h1 is not None:
            self.h1 = " ".join("".join(self._h1).split())
            self._h1 = None

    def handle_data(self, data):
        if self._ld is not None:
            self._ld.append(data)
        elif self._skip:
            return
        else:
            if self._h1 is not None:
                self._h1.append(data)
            self.text.append(data)


def _clean(s):
    return " ".join(html.unescape(s or "").replace("®", "").replace("™", "").split())


def _ld_products(blocks):
    out = []
    for raw in blocks:
        try:
            data = json.loads(raw)
        except ValueError:
            continue
        stack = [data]
        while stack:
            node = stack.pop()
            if isinstance(node, list):
                stack.extend(node)
            elif isinstance(node, dict):
                t = node.get("@type")
                if t == "Product" or (isinstance(t, list) and "Product" in t):
                    out.append(node)
                stack.extend(v for k, v in node.items() if k in ("@graph", "mainEntity", "itemListElement"))
    return out


def extract(html_text, url, url_pattern=None):
    """Pure function: product page HTML -> facts. Covered by tests."""
    p = _Page()
    p.feed(html_text)
    p.close()
    text = re.sub(r"[ \t\r\f\v]+", " ", "".join(p.text))
    text = re.sub(r"\n\s*\n+", "\n", text)
    ld = (_ld_products(p.ld) or [{}])[0]
    brand = ld.get("brand")
    if isinstance(brand, dict):
        brand = brand.get("name")
    sku = ld.get("sku") or ld.get("mpn") or p.meta.get("product:retailer_item_id")
    if not sku:
        m = SKU_TEXT.search(text)
        sku = m.group(1) if m else None
    name = ld.get("name") or p.h1 or p.meta.get("og:title")
    if not brand:
        brand = p.meta.get("product:brand")
    if not brand:
        m = BRAND_TEXT.search(text)
        brand = m.group(1) if m else None
    sku, name, brand = _clean(sku) or None, _clean(name) or None, _clean(brand) or None
    url_sku = None
    if url_pattern:
        m = re.match(url_pattern, url)
        url_sku = m.group(1) if m and m.groups() else None
    note = None
    if sku and url_sku and sku.upper() != url_sku.upper():
        note = f"page SKU {sku} differs from URL SKU {url_sku}"
        sku = None
    compat = []
    for m in COMPAT.finditer(text):
        s = _clean(m.group(0))
        if 12 <= len(s) <= 300 and s not in compat:
            compat.append(s)
        if len(compat) == 8:
            break
    return {"sku": sku, "name": name, "brand": brand, "compat": compat, "note": note}


# ------------------------------------------------------------------- runtime
def gateway(action, args=None, timeout=120):
    url = os.environ["ACTIONS_ID_TOKEN_REQUEST_URL"]
    url += ("&" if "?" in url else "?") + urllib.parse.urlencode({"audience": AUDIENCE})
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + os.environ["ACTIONS_ID_TOKEN_REQUEST_TOKEN"]})
    with urllib.request.urlopen(req, timeout=30) as r:
        jwt = json.load(r)["value"]
    req = urllib.request.Request(GATEWAY, data=json.dumps({"action": action, "args": args or {}}).encode(),
                                 headers={"Authorization": "Bearer " + jwt, "Content-Type": "application/json"},
                                 method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def read(worker, url, limit):
    with worker.open_catalogue(url) as r:
        body = r.read(limit + 1)
    if len(body) > limit:
        raise worker.Held("response too large")
    return body


def load_frontier(worker, store):
    index = read(worker, store["sitemap_url"], MAX_SITEMAP).decode("utf-8", "replace")
    locs = LOC.findall(index)
    children = [u for u in locs if u.endswith(".xml")] or [store["sitemap_url"]]
    pattern = re.compile(store["product_url_pattern"])
    urls = [u for u in locs if pattern.match(u)]
    for child in children:
        if child == store["sitemap_url"]:
            continue
        body = read(worker, child, MAX_SITEMAP).decode("utf-8", "replace")
        urls.extend(u for u in LOC.findall(html.unescape(body)) if pattern.match(u))
        time.sleep(PAGE_PAUSE)
    urls = sorted(set(urls))
    added = 0
    for i in range(0, len(urls), 5000):
        chunk = urls[i:i + 5000]
        added += gateway("frontier", {"store": store["id"], "urls": chunk, "final": i + 5000 >= len(urls)}).get("added", 0)
    print(json.dumps({"store": store["id"], "sitemap_urls": len(urls), "frontier_added": added}), flush=True)


def crawl(worker, store, deadline):
    staged = failed = 0
    while time.monotonic() < deadline:
        claim = gateway("claim", {"store": store["id"], "n": CLAIM})
        urls = claim.get("urls") or []
        if not urls:
            break
        rows = []
        for url in urls:
            row = {"url": url}
            try:
                body = read(worker, url, MAX_PAGE)
                facts = extract(body.decode("utf-8", "replace"), url, store["product_url_pattern"])
                row.update(page_sha256=hashlib.sha256(body).hexdigest(),
                           fetched_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                           sku=facts["sku"], name=facts["name"], brand=facts["brand"], compat=facts["compat"])
                staged += 1
            except Exception as exc:  # recorded per URL; the frontier retries up to 3 times
                row["error"] = f"{type(exc).__name__}: {exc}"[:200]
                failed += 1
            rows.append(row)
            time.sleep(PAGE_PAUSE)
            if time.monotonic() > deadline + 120:
                break
        gateway("stage", {"store": store["id"], "tok": claim["lease"], "rows": rows})
    print(json.dumps({"store": store["id"], "pages_staged": staged, "pages_failed": failed}), flush=True)


def run():
    sys.path.insert(0, os.path.dirname(__file__))
    import rv_master_disk as worker
    deadline = time.monotonic() + RUN_SECONDS
    for store in gateway("config"):
        try:
            if store.get("needs_frontier"):
                load_frontier(worker, store)
            crawl(worker, store, deadline)
        except worker.Held as exc:
            print(json.dumps({"store": store["id"], "held": str(exc)}), flush=True)


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        import unittest
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tests"))
        result = unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.loadTestsFromName("test_store_reader"))
        sys.exit(0 if result.wasSuccessful() else 1)
    run()
