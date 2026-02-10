"""Shared utilities: browser headers, content hashing, URL-to-filename."""

import hashlib
import re
from urllib.parse import urlparse

WHITESPACE_PATTERN = re.compile(r"\s+")


def get_browser_headers() -> dict:
    """Return realistic browser headers to avoid bot detection."""
    return {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
    }


def compute_content_hash(text: str) -> str:
    """SHA-256 hash of whitespace/case-normalized text for deduplication."""
    normalized = re.sub(r"\s+", " ", text.strip().lower())
    return hashlib.sha256(normalized.encode()).hexdigest()


def url_to_filename(url: str) -> str:
    """Convert URL path to a ``.txt`` filename.

    Examples::

        https://icml.cc/Conferences/2025/CallForPapers -> Conferences-2025-CallForPapers.txt
        https://aaai.org/conference/aaai/aaai-25/       -> conference-aaai-aaai-25.txt
        https://neurips.cc/                             -> neurips-cc.txt
    """
    parsed = urlparse(url)
    path_parts = [p for p in parsed.path.split("/") if p]

    if not path_parts:
        base = parsed.netloc.replace(".", "-").replace(":", "-")
    else:
        base = "-".join(path_parts)
        base = re.sub(r"[^a-zA-Z0-9-]", "-", base)
        base = re.sub(r"-+", "-", base).strip("-")

    return f"{base}.txt"
