#!/usr/bin/env python3
"""Headless-Chromium verification for the corridor atlas.

Loads the running web app, waits for the map + data to settle, screenshots it
to web/verification-screenshot.png, and reports:
  - page errors (uncaught exceptions) and console errors
  - EVERY network request, classified same-origin vs EXTERNAL

Exit non-zero if there are page errors or any external (non-web-origin) request,
so the offline-capable guarantee is actually checked, not asserted.

Usage: python3 web/scripts/verify_map.py [URL] [OUT_PNG]
"""
import sys
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:5173/"
OUT = sys.argv[2] if len(sys.argv) > 2 else "web/verification-screenshot.png"

WEB_ORIGIN = urlparse(URL)
# Same-origin == the web dev server host:port. Its /api and /tiles are proxied
# through this same origin, so the browser only ever talks to WEB_ORIGIN.
ALLOWED_HOSTS = {WEB_ORIGIN.hostname}


def is_external(url: str) -> bool:
    u = urlparse(url)
    if u.scheme in ("data", "blob", "about"):
        return False
    return u.hostname not in ALLOWED_HOSTS


def main() -> int:
    requests = []
    page_errors = []
    console_errors = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})

        page.on("request", lambda r: requests.append(r.url))
        page.on("pageerror", lambda e: page_errors.append(str(e)))
        page.on(
            "console",
            lambda m: console_errors.append(m.text) if m.type == "error" else None,
        )

        page.goto(URL, wait_until="networkidle", timeout=30000)
        # Give MapLibre time to fetch tiles + paint the GeoJSON layers.
        page.wait_for_timeout(3500)
        page.screenshot(path=OUT, full_page=False)
        browser.close()

    external = sorted({u for u in requests if is_external(u)})

    print(f"URL: {URL}")
    print(f"screenshot: {OUT}")
    print(f"total network requests: {len(requests)}")
    print(f"external (non-{WEB_ORIGIN.hostname}) requests: {len(external)}")
    for u in external:
        print(f"  EXTERNAL -> {u}")
    print(f"page errors: {len(page_errors)}")
    for e in page_errors:
        print(f"  PAGEERROR -> {e}")
    print(f"console errors: {len(console_errors)}")
    for e in console_errors:
        print(f"  CONSOLE.ERROR -> {e}")

    # Show a compact host histogram so the report proves what WAS fetched.
    hosts = {}
    for u in requests:
        h = urlparse(u).hostname or urlparse(u).scheme
        hosts[h] = hosts.get(h, 0) + 1
    print("request hosts:")
    for h, n in sorted(hosts.items(), key=lambda kv: -kv[1]):
        print(f"  {n:4d}  {h}")

    ok = not external and not page_errors
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
