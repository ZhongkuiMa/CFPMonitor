"""Conference website BFS crawler."""

import heapq
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin, urlparse

import yaml
from bs4 import BeautifulSoup
from ddgs import DDGS

from .base import BaseCrawler
from .filters import (
    EXCLUDED_DOMAINS,
    has_obvious_wrong_year,
    is_accepted_papers_page,
    is_obviously_non_cfp,
    should_skip_url,
)
from .scoring import score_page
from .utils import compute_content_hash, url_to_filename

# Keywords used to identify CFP-related links
_CFP_URL_KEYWORDS = re.compile(
    r"cfp|call-for|call_for|submission|deadlines?|author|guideline|important-date|"
    r"camera.?ready|paper.?format|topics?-of-interest",
    re.IGNORECASE,
)
_CFP_TEXT_KEYWORDS = re.compile(
    r"call for|cfp|submission|deadlines?|author|guideline|important date|"
    r"camera.?ready|paper format|topics? of interest",
    re.IGNORECASE,
)
_CFP_STRONG_KEYWORDS = re.compile(
    r"cfp|call.for.paper|submission|deadlines?|important.date",
    re.IGNORECASE,
)


def _is_cfp_related(url, link_text=""):
    """Return True if *url* or *link_text* suggests CFP-relevant content."""
    return bool(_CFP_URL_KEYWORDS.search(url) or _CFP_TEXT_KEYWORDS.search(link_text))


def _link_priority(url, link_text=""):
    """Return a priority value (lower = visit sooner) for a discovered link.

    - 10: strong CFP keyword in both URL and text
    - 30: CFP keyword in URL or text
    - 50: same-domain, no keyword signal
    - 80: fallback (unlikely to be reached in practice)
    """
    url_match = _CFP_URL_KEYWORDS.search(url)
    text_match = _CFP_TEXT_KEYWORDS.search(link_text)
    strong = _CFP_STRONG_KEYWORDS.search(url) or _CFP_STRONG_KEYWORDS.search(link_text)

    if strong and (url_match and text_match):
        return 10
    if url_match or text_match:
        return 30
    return 50


class ConfCrawler(BaseCrawler):
    """BFS crawler for conference websites.

    Discovers CFP pages starting from a homepage, scores them by relevance,
    and saves the top-K most useful files.
    """

    def __init__(self, data_dir="data", use_search_engine=True, **kwargs):
        super().__init__(data_dir=data_dir, **kwargs)
        self.use_search_engine = use_search_engine
        self.homepage_domains = self._load_homepage_domains()

    def _load_homepage_domains(self):
        """Load homepage domains from ``data/metadata/conferences_homepage.yaml``."""
        metadata_file = self.data_dir / "metadata" / "conferences_homepage.yaml"
        if not metadata_file.exists():
            return {}
        with open(metadata_file) as f:
            return yaml.safe_load(f).get("conferences", {})

    def _get_ccfddl_link(self, conf_abbr, year):
        """Load the ccfddl ``link`` URL from ``data/ccfddl/{conf}/{year}.yaml``.

        :return: Link URL string, or ``None``.
        :rtype: str or None
        """
        ccfddl_file = self.data_dir / "ccfddl" / conf_abbr.lower() / f"{year}.yaml"
        if not ccfddl_file.exists():
            return None
        with open(ccfddl_file) as f:
            data = yaml.safe_load(f)
        if not data:
            return None
        link = data.get("link", "").strip()
        return link if link else None

    def search_homepage(self, conf_abbr, conf_name, year, max_results=5, timeout=5):
        """Find conference homepage from metadata or DuckDuckGo fallback.

        :return: Homepage URL, or ``None``.
        """
        conf_data = self.homepage_domains.get(conf_abbr)
        if conf_data:
            domain = conf_data.get(f"domain{year}", "")
            if domain:
                homepage_url = (
                    f"https://{domain}" if not domain.startswith("http") else domain
                )
                print(f"  [+] Using reliable homepage from metadata: {homepage_url}")
                return homepage_url

        if not self.use_search_engine:
            print(
                f"  [!] No known homepage for {conf_abbr} {year}, skipping (search engine disabled)"
            )
            return None

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
        self, homepage_url, max_depth=3, max_pages=15, seed_urls=None
    ):
        """Priority BFS from *homepage_url*, collecting up to *max_pages* pages.

        CFP-related links (by URL keywords or anchor text) are visited before
        generic links.  Depth-0 links (direct homepage links) may go to any
        same-domain path; deeper links require a path-prefix match OR a CFP
        keyword match.

        :param seed_urls: Additional URLs to seed the BFS (e.g. ccfddl link).
        :return: List of ``{url, title, depth}`` dicts.
        """
        print(f"Exploring homepage (max depth: {max_depth}, max pages: {max_pages})...")

        parsed_home = urlparse(homepage_url)
        home_path = parsed_home.path.rstrip("/")

        # Counter for stable heap ordering when priorities are equal
        counter = 0
        # Heap entries: (priority, counter, url, depth, title)
        heap = []

        def push(priority, url, depth, title):
            nonlocal counter
            heapq.heappush(heap, (priority, counter, url, depth, title))
            counter += 1

        # Seed with homepage (highest priority)
        push(0, homepage_url, 0, "Conference Homepage")

        # Seed with additional URLs (e.g. ccfddl link)
        if seed_urls:
            for seed_url in seed_urls:
                if seed_url and seed_url != homepage_url:
                    push(5, seed_url, 0, "Seed URL")

        visited = set()
        collected_pages = []

        while heap and len(collected_pages) < max_pages:
            priority, _cnt, url, depth, title = heapq.heappop(heap)

            if url in visited or depth > max_depth:
                continue
            visited.add(url)

            success, html = self.fetch_html(url, timeout=5, max_retries=1)
            if not success or html is None:
                continue

            soup = BeautifulSoup(html, "html.parser")
            collected_pages.append({"url": url, "title": title or url, "depth": depth})

            if depth < max_depth:
                for link in soup.find_all("a", href=True):
                    next_url = urljoin(url, link["href"])
                    parsed_url = urlparse(next_url)

                    # Strip fragments
                    next_url = parsed_url._replace(fragment="").geturl()

                    if parsed_url.netloc != parsed_home.netloc:
                        continue
                    if should_skip_url(next_url):
                        continue

                    link_text = link.get_text().strip() or ""

                    # Path restriction: relaxed at depth 0, stricter deeper
                    if depth == 0:
                        # Homepage links: allow any same-domain URL
                        pass
                    else:
                        # Deeper links: require path prefix OR CFP keyword
                        if not parsed_url.path.startswith(home_path):
                            if not _is_cfp_related(next_url, link_text):
                                continue

                    if next_url not in visited:
                        link_title = link_text or next_url
                        prio = _link_priority(next_url, link_text)
                        push(prio, next_url, depth + 1, link_title)

        print(f"  [+] Found {len(collected_pages)} pages")
        return collected_pages

    def save_pages(self, pages, conf_abbr, year, max_workers=10, max_files=10):
        """Download, score, deduplicate, and save the top *max_files* pages.

        Pages scoring below ``MIN_SCORE`` are dropped.  Content hashes of
        existing archive files (including ccfddl-link.txt and wikicfp.txt) are
        pre-loaded so duplicates are never written.  When a filename collision
        occurs with the *same* hash the file is skipped; with a *different*
        hash the file is overwritten with fresher data.

        :return: ``{url: success_bool}`` for each page.
        """
        MIN_SCORE = 100

        archive_dir = self.data_dir / "raw" / conf_abbr.lower() / str(year)
        archive_dir.mkdir(parents=True, exist_ok=True)
        print(
            f"Collecting {len(pages)} pages, scoring, and "
            f"saving top {max_files} to {archive_dir}/..."
        )

        results = {}
        downloaded_pages = []

        # Pre-load content hashes of existing files on disk for dedup
        seen_hashes = set()
        existing_hashes = {}  # filename -> hash
        for existing_file in archive_dir.glob("*.txt"):
            text = existing_file.read_text(encoding="utf-8")
            h = compute_content_hash(text)
            seen_hashes.add(h)
            existing_hashes[existing_file.name] = h

        def download_and_extract(page):
            url = page["url"]
            depth = page.get("depth", 0)

            success, html = self.fetch_html(url, timeout=5, max_retries=2)
            if not success or html is None:
                return None

            text = self.extract_text(html)
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
            futures = {
                executor.submit(download_and_extract, page): page for page in pages
            }

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

        # Drop pages that don't meet the minimum relevance threshold
        before_filter = len(downloaded_pages)
        downloaded_pages = [p for p in downloaded_pages if p["score"] >= MIN_SCORE]
        if before_filter != len(downloaded_pages):
            print(
                f"  [+] Dropped {before_filter - len(downloaded_pages)} pages "
                f"below min score {MIN_SCORE}"
            )

        print(f"  [+] Downloaded and filtered {len(downloaded_pages)} unique pages")

        top_k = downloaded_pages[:max_files]
        used_filenames = set()

        for item in top_k:
            filename = item["filename"]
            file_path = archive_dir / filename

            # Dedup against existing files on disk
            if file_path.exists():
                old_hash = existing_hashes.get(filename)
                if old_hash == item["hash"]:
                    # Same content — skip
                    print(f"  [=] Skipped {filename} (unchanged)")
                    used_filenames.add(filename)
                    continue
                # Different content — overwrite with fresher data
                print(f"  [~] Overwriting {filename} (content changed)")
            else:
                # Avoid filename collisions within this batch
                counter = 1
                while filename in used_filenames:
                    stem = item["filename"].removesuffix(".txt")
                    filename = f"{stem}-{counter}.txt"
                    file_path = archive_dir / filename
                    counter += 1

            used_filenames.add(filename)
            file_path.write_text(item["text"], encoding="utf-8")
            print(
                f"  [+] Saved {filename} (score: {item['score']:.1f}, size: {len(item['text'])} bytes)"
            )

        print(
            f"  [+] Saved {len(top_k)}/{len(downloaded_pages)} pages (top {max_files})"
        )
        return results

    def crawl(self, conf_abbr, year, conf_name=None, **kwargs):
        """Full pipeline: search homepage, BFS crawl, save top pages.

        :return: Dict with crawl results.
        """
        homepage = self.search_homepage(conf_abbr, conf_name or conf_abbr, year)
        if not homepage:
            return {
                "conf": conf_abbr,
                "year": year,
                "success": False,
                "reason": "no_homepage",
            }

        seed_urls = []
        ccfddl_link = self._get_ccfddl_link(conf_abbr, year)
        if ccfddl_link:
            seed_urls.append(ccfddl_link)

        pages = self.fetch_potential_pages(homepage, seed_urls=seed_urls or None)
        save_results = self.save_pages(pages, conf_abbr, year, **kwargs)

        return {
            "conf": conf_abbr,
            "year": year,
            "success": True,
            "homepage": homepage,
            "pages_found": len(pages),
            "save_results": save_results,
        }

    def load_archived_pages(self, conf_abbr, year):
        """List archived ``.txt`` files for a conference."""
        archive_dir = self.data_dir / "raw" / conf_abbr.lower() / str(year)
        if not archive_dir.exists():
            return []
        return sorted(archive_dir.glob("*.txt"))
