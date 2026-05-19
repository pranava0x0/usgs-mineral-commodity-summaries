#!/usr/bin/env python3
"""Tiny static file server for the viewer.

Run from anywhere — it serves the project root so the viewer's
relative path to `data/audit/.../*.png` resolves correctly.
"""

from __future__ import annotations

import http.server
import os
import socketserver
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
PORT = int(os.environ.get("PORT", "8765"))


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(PROJECT_ROOT), **kwargs)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_GET(self):  # noqa: N802 (stdlib convention)
        # Send a real 302 to /viewer/ so the browser's URL becomes /viewer/
        # and the page's relative paths (style.css, viewer.js, data.json,
        # ../data/audit/...) resolve correctly. An internal rewrite would
        # leave the URL at "/" and break those relative refs.
        if self.path in ("/", ""):
            self.send_response(302)
            self.send_header("Location", "/viewer/")
            self.end_headers()
            return
        return super().do_GET()


class ReusableTCPServer(socketserver.TCPServer):
    """Allow rapid restarts without TIME_WAIT errors."""
    allow_reuse_address = True


def main() -> int:
    with ReusableTCPServer(("127.0.0.1", PORT), Handler) as httpd:
        print(f"serving {PROJECT_ROOT} at http://127.0.0.1:{PORT}/", flush=True)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
