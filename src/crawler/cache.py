"""File-based page cache with TTL expiry."""

import hashlib
import json
import tempfile
import time
from pathlib import Path

DEFAULT_TTL = 86400
CACHE_DIR = Path("data/.cache")


def _path(url):
    return CACHE_DIR / hashlib.sha256(url.encode()).hexdigest()[:16]


def get(url, ttl=DEFAULT_TTL):
    """Return cached HTML for *url* if younger than *ttl* seconds, else ``None``.

    :param url: URL whose cached content to retrieve.
    :param ttl: Maximum age in seconds.
    :rtype: str or None
    """
    p = _path(url)
    meta = p.with_suffix(".meta")
    if not p.exists() or not meta.exists():
        return None
    try:
        ts = json.loads(meta.read_text())["timestamp"]
    except (json.JSONDecodeError, KeyError):
        return None
    if time.time() - ts > ttl:
        return None
    return p.read_text(encoding="utf-8")


def put(url, content):
    """Write *content* to disk, keyed by *url*.

    :param url: URL to cache.
    :param content: HTML string.
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    p = _path(url)
    p.write_text(content, encoding="utf-8")
    meta = p.with_suffix(".meta")
    tmp = tempfile.NamedTemporaryFile(
        dir=CACHE_DIR,
        suffix=".tmp",
        mode="w",
        delete=False,
    )
    tmp.write(json.dumps({"url": url, "timestamp": time.time()}))
    tmp.close()
    Path(tmp.name).replace(meta)
