"""Idempotent PDF fetcher with disk cache and host rate limit."""

from __future__ import annotations

import hashlib
import logging
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

from . import config

log = logging.getLogger(__name__)

# One host -> timestamp of last successful request, so the delay holds across calls.
_LAST_REQUEST_AT: dict[str, float] = {}


def _respect_host_delay(url: str) -> None:
    host = urlparse(url).netloc
    last = _LAST_REQUEST_AT.get(host)
    if last is not None:
        wait = config.HOST_DELAY_S - (time.monotonic() - last)
        if wait > 0:
            log.debug("rate-limit: sleeping %.2fs before hitting %s", wait, host)
            time.sleep(wait)
    _LAST_REQUEST_AT[host] = time.monotonic()


def cache_path(url: str) -> Path:
    """Where on disk would we cache this URL? Filename comes from the URL tail."""
    config.ensure_dirs()
    name = Path(urlparse(url).path).name or "download.pdf"
    return config.RAW_DIR / name


def fetch_pdf(url: str, *, force: bool = False) -> Path:
    """Download `url` into `data/raw/`, or return the cached copy if present.

    Idempotent: re-running is safe and (by default) does not re-download.
    Raises on HTTP/network failure — we want loud failures, not silent skips.
    """
    dest = cache_path(url)
    if dest.exists() and not force:
        log.info("cache hit: %s", dest.name)
        return dest

    _respect_host_delay(url)
    req = urllib.request.Request(url, headers={"User-Agent": config.USER_AGENT})
    log.info("fetching %s", url)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp, dest.open("wb") as fh:
            fh.write(resp.read())
    except (urllib.error.HTTPError, urllib.error.URLError) as exc:
        if dest.exists():
            dest.unlink()
        raise RuntimeError(f"failed to fetch {url}: {exc}") from exc
    log.info("saved %s (%d bytes)", dest.name, dest.stat().st_size)
    return dest


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()
