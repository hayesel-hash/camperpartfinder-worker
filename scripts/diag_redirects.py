"""Print the redirect chain the worker sees for a URL (diagnostic only).

Uses the worker's own User-Agent and no-redirect opener, follows at most 8
hops, and prints status, Location and the NAMES of any cookies set (never
their values). Fetches only headers plus the first bytes of the body. No
database access, no secrets.
"""
import sys
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, __import__("os").path.dirname(__file__))
from rv_master_disk import HTTP_AGENT, NoRedirect, SourceRedirect  # noqa: E402


class Capture(NoRedirect):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        self.last = (code, headers)
        raise SourceRedirect(newurl)


def chain(url, cookies=False):
    handler = Capture()
    handlers = [handler]
    if cookies:
        handlers.append(urllib.request.HTTPCookieProcessor())
    opener = urllib.request.build_opener(*handlers)
    print(f"== {url}  (cookie jar: {cookies})")
    for hop in range(8):
        try:
            with opener.open(urllib.request.Request(url, headers={"User-Agent": HTTP_AGENT}), timeout=60) as r:
                head = r.read(8)
                print(f"  {hop}: {r.status} {r.headers.get('Content-Type')} len={r.headers.get('Content-Length')} starts={head[:5]!r}")
                return
        except SourceRedirect as exc:
            code, headers = handler.last
            names = sorted({c.split("=", 1)[0].strip() for c in headers.get_all("Set-Cookie") or []})
            print(f"  {hop}: {code} -> {exc.target}  set-cookie names={names}")
            url = urllib.parse.urljoin(url, exc.target)
        except urllib.error.HTTPError as exc:
            print(f"  {hop}: HTTP {exc.code} server={exc.headers.get('Server')}")
            return
    print("  stopped after 8 hops")


if __name__ == "__main__":
    for target in sys.argv[1:]:
        chain(target)
        chain(target, cookies=True)
