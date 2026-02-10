"""Base crawler with shared HTTP fetching, caching, and text extraction."""

import time
from abc import ABC, abstractmethod
from pathlib import Path

import requests
import yaml
from bs4 import BeautifulSoup

from . import cache as page_cache
from .filters import should_skip_content_type, should_skip_url
from .utils import get_browser_headers


class BaseCrawler(ABC):
    """Abstract base for all crawlers.

    Provides HTTP fetching with file-based caching and rate limiting,
    HTML text extraction, and conference metadata loading.
    """

    def __init__(self, data_dir="data", cache_ttl=86400, rate_limit_delay=0.5):
        self.data_dir = Path(data_dir)
        self.cache_ttl = cache_ttl
        self.rate_limit_delay = rate_limit_delay

    def fetch_html(self, url, timeout=5, max_retries=2, use_cache=True):
        """Fetch HTML from *url* with caching, rate limiting, and retry.

        :param url: Target URL.
        :param timeout: Base request timeout in seconds.
        :param max_retries: Number of retries on transient errors.
        :param use_cache: Read/write the file-based page cache.
        :return: ``(True, html)`` on success, ``(False, None)`` on failure.
        :rtype: tuple[bool, str | None]
        """
        if should_skip_url(url):
            return False, None

        if use_cache:
            cached = page_cache.get(url, ttl=self.cache_ttl)
            if cached:
                return True, cached

        time.sleep(self.rate_limit_delay)
        headers = get_browser_headers()

        for attempt in range(max_retries + 1):
            try:
                response = requests.get(
                    url,
                    timeout=timeout + attempt * 2,
                    headers=headers,
                )
            except (requests.Timeout, requests.ConnectionError):
                if attempt < max_retries:
                    continue
                return False, None
            except requests.RequestException:
                return False, None

            if response.status_code >= 400:
                if response.status_code in (502, 503) and attempt < max_retries:
                    continue
                return False, None

            content_type = response.headers.get("content-type", "")
            if should_skip_content_type(content_type):
                return False, None

            if "charset" not in content_type.lower():
                response.encoding = response.apparent_encoding

            if use_cache:
                page_cache.put(url, response.text)
            return True, response.text

        return False, None

    def extract_text(self, html):
        """Extract text while preserving paragraph structure.

        Strips boilerplate (nav, header, footer, script, style) and adds
        line breaks only after content-bearing block tags to minimise
        blank lines.

        :param html: Raw HTML string.
        :rtype: str
        """
        import re

        soup = BeautifulSoup(html, "html.parser")

        # Remove boilerplate and non-content tags
        for tag in soup(["script", "style", "nav", "header", "footer"]):
            tag.decompose()

        # Content-bearing block tags that warrant a line break
        _content_blocks = {
            "p",
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
            "li",
            "tr",
            "blockquote",
            "dd",
            "dt",
            "pre",
        }
        for tag in soup.find_all(list(_content_blocks)):
            tag.insert_before("\n")

        # Extract text with space separator
        text = soup.get_text(separator=" ")

        # Normalize whitespace within lines
        text = re.sub(r"[ \t]+", " ", text)

        # Strip each line and drop all blank lines
        lines = [line.strip() for line in text.split("\n")]
        lines = [line for line in lines if line]
        text = "\n".join(lines)

        return text.strip()

    def load_conferences(self, conference=None, rank=None):
        """Load conferences from ``data/metadata/conferences.yaml``.

        :param conference: Keep only this abbreviation.
        :param rank: Keep only this CCF rank (e.g. ``'A'``).
        :rtype: list[dict]
        """
        conf_file = self.data_dir / "metadata" / "conferences.yaml"
        with open(conf_file) as f:
            conferences = yaml.safe_load(f)["conferences"]
        if conference:
            conferences = [
                c for c in conferences if c["short"].upper() == conference.upper()
            ]
        if rank:
            conferences = [
                c
                for c in conferences
                if c.get("rank", {}).get("ccf", "").upper() == rank.upper()
            ]
        return conferences

    @abstractmethod
    def crawl(self, conf_abbr, year, **kwargs):
        """Crawl data for one conference. Subclasses must implement."""
