"""Supplied reader: fetch queued maker documents from their publisher's own download links,
extract them with the same two-pass reader and gates as the Drive lane, and STAGE the result
through rv-supplied-gateway (stage-only; the database publishes only when every gate passed).

First use (26 Nov 2026): Airstream parts books over the Drive connector's 10 MB limit, fetched
from the links in Airstream's own document list (asset host a-us.storyblok.com).
Polite: one document at a time, 5 s between downloads; host allowlist and robots.txt enforced
by rv_master_disk.open_catalogue. Logs print titles and counts only, never document content.
"""
import importlib.util, io, json, os, sys, tempfile, time, urllib.parse, urllib.request, contextlib

HERE = os.path.dirname(os.path.abspath(__file__))
GATEWAY = "https://dlijhukwzlqwtmiynncg.supabase.co/functions/v1/rv-supplied-gateway"
AUDIENCE = "rv-supplied-reader-dlijhukwzlqwtmiynncg"
RUN_SECONDS = 25 * 60
LIMIT = 90_000_000


def gateway(action, args=None, timeout=300):
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


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod


def run():
    sys.path.insert(0, os.path.dirname(HERE))
    import rv_master_disk as worker
    book = load("batch_book", os.path.join(HERE, "batch_book.py"))
    deadline = time.monotonic() + RUN_SECONDS
    done = 0
    while time.monotonic() < deadline:
        items = gateway("claim", {"n": 2})
        if not items:
            break
        for it in items:
            try:
                with worker.open_catalogue(it["url"]) as r:
                    body = r.read(LIMIT + 1)
                if len(body) > LIMIT or not body.startswith(b"%PDF"):
                    raise RuntimeError("not a PDF or too large")
                with tempfile.TemporaryDirectory() as tmp:
                    pdf = os.path.join(tmp, "book.pdf")
                    open(pdf, "wb").write(body)
                    with contextlib.redirect_stdout(io.StringIO()):
                        book.main(pdf, it["url"], "Airstream " + it["title"] + ".pdf", tmp)
                    out = [f for f in os.listdir(tmp) if f.endswith(".json")][0]
                    doc = json.load(open(os.path.join(tmp, out)))
                res = gateway("stage", {"url": it["url"], "lease": it["lease"], "doc": doc})
                print(json.dumps({"title": it["title"], "state": doc["review_state"],
                                  "failed_gates": [k for k, v in doc["gates"].items() if not v], "result": res}), flush=True)
                done += 1
            except Exception as exc:  # report and move on; the queue retries up to 3 times
                reason = type(exc).__name__ + ": " + str(exc)[:200]
                print(json.dumps({"title": it["title"], "error": reason}), flush=True)
                try:
                    gateway("fail", {"url": it["url"], "lease": it["lease"], "reason": reason})
                except Exception:
                    pass
            time.sleep(5)
    print(json.dumps({"documents_processed": done}), flush=True)


if __name__ == "__main__":
    run()
