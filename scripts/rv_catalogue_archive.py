"""Catalogue archive worker.

Keeps a private copy of every catalogue PDF we have read, plus the text of every page, so any
part number or replacement can be re-verified against the exact page later. It also re-checks
archived catalogues every 30 days; if the manufacturer has published a new edition, the new file
is stored alongside the old one and the catalogue is flagged edition_changed for re-reading.

Never publishes parts, replacements or fitment. Never deletes anything.
Reuses the existing source rules from rv_master_disk.py: allowlisted hosts, robots.txt,
no cross-host redirects.
"""
import hashlib
import json
import os
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pymupdf  # noqa: E402
from rv_master_disk import (  # noqa: E402
    AGENT, OPENER, Held, authorize_job_origin, checked, disk_capacity, open_catalogue,
)

GATEWAY = "https://dlijhukwzlqwtmiynncg.supabase.co/functions/v1/rv-catalogue-archive-gateway"
AUDIENCE = "rv-catalogue-archive-dlijhukwzlqwtmiynncg"
TEXT_METHOD = "pymupdf-text-v1"
BATCH_BYTES = 800_000      # gateway accepts up to 2 MB per call; stay well under
BATCH_PAGES = 400          # database accepts up to 500 pages per call
RUN_SECONDS = 18 * 60      # stop claiming new work after this; lease is 25 minutes
PAUSE_SECONDS = 2          # be polite to manufacturers' servers between catalogues


def rpc(action, args=None, timeout=120):
    token_url = os.environ["ACTIONS_ID_TOKEN_REQUEST_URL"]
    token_url += ("&" if "?" in token_url else "?") + urllib.parse.urlencode({"audience": AUDIENCE})
    req = urllib.request.Request(token_url, headers={"Authorization": "Bearer " + os.environ["ACTIONS_ID_TOKEN_REQUEST_TOKEN"]})
    with OPENER.open(req, timeout=30) as response:
        jwt = json.load(response)["value"]
    req = urllib.request.Request(
        GATEWAY, data=json.dumps({"action": action, "args": args or {}}).encode(),
        headers={"Authorization": "Bearer " + jwt, "Content-Type": "application/json"}, method="POST")
    with OPENER.open(req, timeout=timeout) as response:
        return json.load(response)


class NotModified(Exception):
    pass


def fetch_pdf(url, dest, etag=None, last_modified=None):
    """Download a catalogue to disk. Returns (sha256, bytes, etag, last_modified).
    With etag/last_modified, asks the server to answer 304 if nothing changed."""
    extra = {}
    if etag:
        extra["If-None-Match"] = etag
    if last_modified:
        extra["If-Modified-Since"] = last_modified

    def opener(u):
        checked(u)
        return OPENER.open(urllib.request.Request(u, headers={"User-Agent": AGENT, **extra}), timeout=180)

    digest = hashlib.sha256()
    total = 0
    try:
        response = open_catalogue(url, opener=opener)
    except urllib.error.HTTPError as exc:
        if exc.code == 304:
            raise NotModified() from None
        raise
    with response, dest.open("wb") as f:
        capacity = disk_capacity(dest)
        if int(response.headers.get("Content-Length", "0") or 0) > capacity:
            raise Held("insufficient runner disk capacity")
        new_etag = response.headers.get("ETag")
        new_modified = response.headers.get("Last-Modified")
        while chunk := response.read(1024 * 1024):
            total += len(chunk)
            if total > capacity:
                raise Held("insufficient runner disk capacity")
            digest.update(chunk)
            f.write(chunk)
    with dest.open("rb") as f:
        if f.read(5) != b"%PDF-":
            raise Held("not a PDF")
    return digest.hexdigest(), total, new_etag, new_modified


def page_record(page, number):
    """Text of one page. text_sha256 is over PyMuPDF's raw get_text("text"), the same hash the
    extraction worker stores as page_text_sha256 on replacement evidence, so the two line up."""
    raw = page.get_text("text")
    text_sha = hashlib.sha256(raw.encode("utf-8", "surrogatepass")).hexdigest()
    clean = raw.replace("\x00", "").encode("utf-8", "replace").decode("utf-8")
    return {"page": number, "text": clean, "text_sha256": text_sha, "method": TEXT_METHOD}


def page_batches(doc, skip=0):
    """Yield lists of page records sized to fit one gateway call."""
    batch, size = [], 0
    for i in range(skip, len(doc)):
        rec = page_record(doc[i], i + 1)
        rec_size = len(json.dumps(rec))
        if batch and (size + rec_size > BATCH_BYTES or len(batch) >= BATCH_PAGES):
            yield batch
            batch, size = [], 0
        if rec_size > BATCH_BYTES:  # a single enormous page: keep the hash, trim the text
            rec["text"] = rec["text"][: BATCH_BYTES // 2]
            rec_size = len(json.dumps(rec))
        batch.append(rec)
        size += rec_size
    if batch:
        yield batch


def upload_pdf(upload_url, path, size):
    with path.open("rb") as f:
        req = urllib.request.Request(
            upload_url, data=f, method="PUT",
            headers={"Content-Type": "application/pdf", "Content-Length": str(size), "x-upsert": "true"})
        with OPENER.open(req, timeout=900) as response:
            response.read()


def archive_one(job, tmp):
    cid, tok = job["id"], job["lease"]
    authorize_job_origin(job["url"])
    dest = Path(tmp) / "catalogue.pdf"
    dest.unlink(missing_ok=True)
    try:
        if job.get("mode") == "recheck":
            try:
                sha, size, etag, modified = fetch_pdf(job["url"], dest, job.get("etag"), job.get("last_modified"))
            except NotModified:
                return "unchanged", {"note": "server reports not modified"}
        else:
            sha, size, etag, modified = fetch_pdf(job["url"], dest)
        with pymupdf.open(dest) as doc:
            pages = len(doc)
            if pages < 1:
                raise Held("empty PDF")
            began = rpc("begin", {"cid": cid, "tok": tok, "doc_sha256": sha, "doc_bytes": size,
                                  "doc_pages": pages, "etag": etag, "last_modified": modified})
            if began.get("error"):
                raise RuntimeError("begin rejected: " + began["error"])
            if began.get("need_pages"):
                for batch in page_batches(doc):
                    saved = rpc("pages", {"cid": cid, "tok": tok, "doc_sha256": sha, "page_rows": batch})
                    if saved == -1:
                        raise RuntimeError("page batch rejected")
        if began.get("need_upload"):
            try:
                upload_pdf(began["upload_url"], dest, size)
            except urllib.error.HTTPError as exc:
                body = exc.read()[:300].decode("utf-8", "replace")
                if exc.code in (400, 413) and ("size" in body.lower() or "large" in body.lower() or exc.code == 413):
                    return "text_only", {"sha256": sha, "note": f"PDF too large for storage limit ({size} bytes)"}
                raise RuntimeError(f"upload HTTP {exc.code}") from None
        return "archived", {"sha256": sha}
    finally:
        dest.unlink(missing_ok=True)


def main(worker):
    deadline = time.monotonic() + RUN_SECONDS
    done = 0
    with tempfile.TemporaryDirectory(prefix="rv-archive-") as tmp:
        while time.monotonic() < deadline:
            job = rpc("claim", {"worker": worker})
            if not job:
                print(json.dumps({"event": "archive_queue_empty", "worker": worker}), flush=True)
                break
            try:
                outcome, details = archive_one(job, tmp)
            except Held as exc:
                outcome, details = "failed", {"error": str(exc)}
            except urllib.error.HTTPError as exc:
                outcome = "unavailable" if exc.code in (404, 410) else "failed"
                details = {"error": f"HTTP {exc.code}"}
            except Exception as exc:  # never let one catalogue stop the run
                outcome, details = "failed", {"error": f"{type(exc).__name__}: {str(exc)[:200]}"}
            result = rpc("finish", {"cid": job["id"], "tok": job["lease"], "outcome": outcome, "details": details})
            done += 1
            print(json.dumps({"catalogue": job["id"], "publisher": job.get("publisher"), "mode": job.get("mode"),
                              "outcome": outcome, "result": result, "error": details.get("error")}), flush=True)
            time.sleep(PAUSE_SECONDS)
    print(json.dumps({"event": "archive_run_complete", "worker": worker, "catalogues": done}), flush=True)


def self_test():
    with pymupdf.open() as doc:
        for i in range(3):
            pg = doc.new_page()
            pg.insert_text((40, 60), f"Part No. 3310{i} Superseded by 1645{i}")
        batches = list(page_batches(doc))
        assert len(batches) == 1 and [r["page"] for r in batches[0]] == [1, 2, 3], batches
        for rec, page in zip(batches[0], doc):
            assert rec["text_sha256"] == hashlib.sha256(page.get_text("text").encode()).hexdigest()
            assert "\x00" not in rec["text"] and rec["method"] == TEXT_METHOD
        assert "33100" in batches[0][0]["text"]
        json.dumps(batches)  # must serialise cleanly
    with pymupdf.open() as doc:
        for i in range(BATCH_PAGES + 5):
            doc.new_page()
        sizes = [len(b) for b in page_batches(doc)]
        assert sizes == [BATCH_PAGES, 5], sizes
    print("archive self-test passed")


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        self_test()
    else:
        main(os.environ.get("RV_ARCHIVE_WORKER", "archive"))
