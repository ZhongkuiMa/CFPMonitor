"""Backward-compatible functional API for the crawler.

Wraps the class-based API in free functions. New code should use
``ConfCrawler``, ``CCFDDLCrawler``, ``WikiCFPCrawler`` directly.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
import yaml
from bs4 import BeautifulSoup
from ddgs import DDGS

from .filters import (
    EXCLUDED_DOMAINS,
    has_obvious_wrong_year,
    is_accepted_papers_page,
    is_obviously_non_cfp,
    should_skip_content_type,
    should_skip_url,
)
from .scoring import score_page
from .utils import (
    WHITESPACE_PATTERN,
    compute_content_hash,
    get_browser_headers,
    url_to_filename,
)


def load_conference_homepage_domains() -> dict:
    """Load homepage domains from ``data/metadata/conferences_homepage.yaml``."""
    metadata_file = (
        Path(__file__).parent.parent.parent
        / "data"
        / "metadata"
        / "conferences_homepage.yaml"
    )
    with open(metadata_file) as f:
        return yaml.safe_load(f).get("conferences", {})


def fetch_html(
    url: str, timeout: int = 5, max_retries: int = 2
) -> tuple[bool, str | None]:
    """Fetch and validate HTML from *url* with retry.

    :param url: Target URL.
    :param timeout: Base request timeout in seconds.
    :param max_retries: Number of retries on transient errors.
    :return: ``(True, html)`` on success, ``(False, None)`` on failure.
    :rtype: tuple[bool, str | None]
    """
    if should_skip_url(url):
        return False, None

    headers = get_browser_headers()

    for attempt in range(max_retries + 1):
        try:
            response = requests.get(url, timeout=timeout + attempt * 2, headers=headers)
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

        return True, response.text

    return False, None


def search_homepage(
    conf_abbr: str,
    conf_name: str,
    year: int,
    max_results: int = 5,
    timeout: int = 5,
) -> str | None:
    """Find conference homepage from metadata or DuckDuckGo fallback.

    :return: Homepage URL, or ``None``.
    """
    homepage_domains = load_conference_homepage_domains()
    conf_data = homepage_domains.get(conf_abbr)
    if conf_data:
        domain = conf_data.get(f"domain{year}", "")
        if domain:
            homepage_url = (
                f"https://{domain}" if not domain.startswith("http") else domain
            )
            print(f"  [+] Using reliable homepage from metadata: {homepage_url}")
            return homepage_url

    print(f"Searching for {conf_abbr} {year} homepage...")
    query = f"{year} {conf_abbr}"

    with DDGS(timeout=timeout) as ddgs:
        results = list(ddgs.text(query, max_results=max_results, timelimit="y"))

    if not results:
        print("  [!] No results found")
        return None

    print(f"  [+] Found {len(results)} search results from DuckDuckGo")

    best_url = None
    best_score = 0
    year_str = str(year)
    abbr_lower = conf_abbr.lower()

    for result in results:
        url = result.get("href") or result.get("url")
        if not url:
            continue

        parsed = urlparse(url)
        netloc = parsed.netloc.lower()
        if any(excl in netloc for excl in EXCLUDED_DOMAINS):
            continue

        url_lower = url.lower()
        title = result.get("title", "").lower()

        other_years = [str(y) for y in range(year - 1, year + 3) if y != year]
        if any(oy in url_lower or oy in title for oy in other_years):
            continue

        score = 0
        if abbr_lower in netloc.split("."):
            score += 200
        elif abbr_lower in netloc:
            score += 5

        score += 10 if year_str in url_lower else 0
        score += 5 if abbr_lower in title else 0
        score += 3 if year_str in title else 0

        path_depth = len([p for p in parsed.path.split("/") if p])
        score += {0: 20, 1: 15, 2: 10}.get(path_depth, 0)

        if score > best_score:
            best_score = score
            best_url = url

    if not best_url:
        print("  [!] No suitable homepage found")
        return None

    print(f"  [+] Best match: {best_url} (score: {best_score})")

    parsed = urlparse(best_url)
    path_parts = [p for p in parsed.path.split("/") if p]

    if len(path_parts) > 2:
        conference_path = "/" + "/".join(path_parts[:2]) + "/"
        best_url = f"{parsed.scheme}://{parsed.netloc}{conference_path}"
        print(f"  [+] Adjusted to conference level: {best_url}")

    print(f"  [+] Using homepage: {best_url}")
    return best_url


def fetch_potential_pages(
    homepage_url: str, max_depth: int = 3, max_pages: int = 15
) -> list[dict]:
    """BFS from *homepage_url*, collecting up to *max_pages* pages.

    :return: List of ``{url, title, depth}`` dicts.
    """
    print(f"Exploring homepage (max depth: {max_depth}, max pages: {max_pages})...")

    parsed_home = urlparse(homepage_url)
    home_path = parsed_home.path.rstrip("/")

    pages_to_visit = [(homepage_url, 0, "Conference Homepage")]
    visited = set()
    collected_pages = []

    while pages_to_visit and len(collected_pages) < max_pages:
        url, depth, title = pages_to_visit.pop(0)

        if url in visited or depth > max_depth:
            continue
        visited.add(url)

        success, html = fetch_html(url, timeout=5, max_retries=1)
        if not success or html is None:
            continue

        soup = BeautifulSoup(html, "html.parser")
        collected_pages.append({"url": url, "title": title or url, "depth": depth})

        if depth < max_depth:
            for link in soup.find_all("a", href=True):
                next_url = urljoin(url, link["href"])
                parsed_url = urlparse(next_url)

                if parsed_url.netloc != parsed_home.netloc:
                    continue
                if not parsed_url.path.startswith(home_path):
                    continue
                if should_skip_url(next_url):
                    continue

                if next_url not in visited:
                    link_title = link.get_text().strip() or next_url
                    pages_to_visit.append((next_url, depth + 1, link_title))

    print(f"  [+] Found {len(collected_pages)} pages")
    return collected_pages


def save_pages(
    pages: list[dict],
    conf_abbr: str,
    year: int,
    archive_root: str,
    max_workers: int = 10,
    max_files: int = 10,
) -> dict[str, bool]:
    """Download, score, deduplicate, and save the top *max_files* pages.

    :return: ``{url: success_bool}`` for each page.
    """
    archive_dir = Path(archive_root) / conf_abbr.lower() / str(year)
    archive_dir.mkdir(parents=True, exist_ok=True)
    print(
        f"Collecting {len(pages)} pages, scoring, and saving top {max_files} to {archive_dir}/..."
    )

    results = {}
    downloaded_pages = []
    seen_hashes = set()

    def download_and_extract(page):
        url = page["url"]
        depth = page.get("depth", 0)

        success, html = fetch_html(url, timeout=5, max_retries=2)
        if not success or html is None:
            return None

        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(
            [
                "script",
                "style",
                "nav",
                "footer",
                "header",
                "code",
                "pre",
                "kbd",
                "samp",
                "var",
            ]
        ):
            tag.decompose()

        text = soup.get_text(strip=True)
        text = WHITESPACE_PATTERN.sub(" ", text).strip()

        if is_obviously_non_cfp(text) or has_obvious_wrong_year(text, year):
            return None
        # Filter out accepted papers/proceedings pages (can be >1 MB)
        if is_accepted_papers_page(text):
            return None

        return {
            "url": url,
            "filename": url_to_filename(url),
            "text": text,
            "score": score_page(page, text, depth),
            "hash": compute_content_hash(text),
        }

    print(f"  [+] Downloading {len(pages)} pages...")
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(download_and_extract, page): page for page in pages}

        for future in as_completed(futures):
            page = futures[future]
            result = future.result()
            if result is None:
                results[page["url"]] = False
                continue

            results[result["url"]] = True
            if result["hash"] not in seen_hashes:
                seen_hashes.add(result["hash"])
                downloaded_pages.append(result)

    downloaded_pages.sort(key=lambda x: x["score"], reverse=True)
    print(f"  [+] Downloaded and filtered {len(downloaded_pages)} unique pages")

    top_k = downloaded_pages[:max_files]
    used_filenames = set()

    for item in top_k:
        filename = item["filename"]
        file_path = archive_dir / filename
        counter = 1
        while filename in used_filenames or file_path.exists():
            stem = filename.removesuffix(".txt")
            filename = f"{stem}-{counter}.txt"
            file_path = archive_dir / filename
            counter += 1

        used_filenames.add(filename)
        file_path.write_text(item["text"], encoding="utf-8")
        print(
            f"  [+] Saved {filename} (score: {item['score']:.1f}, size: {len(item['text'])} bytes)"
        )

    print(f"  [+] Saved {len(top_k)}/{len(downloaded_pages)} pages (top {max_files})")
    return results


def load_archived_pages(
    conf_abbr: str, year: int, archive_root: str = "data/raw"
) -> list[Path]:
    """List archived ``.txt`` files for a conference."""
    archive_dir = Path(archive_root) / conf_abbr.lower() / str(year)
    if not archive_dir.exists():
        return []
    return sorted(archive_dir.glob("*.txt"))
