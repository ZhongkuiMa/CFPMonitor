"""WikiCFP scraper.

Fetches conference data from wikicfp.com.
"""

import re
import time
import unicodedata

import yaml
from bs4 import BeautifulSoup

from .base import BaseCrawler


class WikiCFPCrawler(BaseCrawler):
    """Scraper for wikicfp.com conference data."""

    BASE_URL = "http://www.wikicfp.com"

    def __init__(self, data_dir="data", **kwargs):
        kwargs.setdefault("rate_limit_delay", 2.0)
        super().__init__(data_dir=data_dir, **kwargs)

    def search_conference(self, conf_abbr, year):
        """Search WikiCFP for matching events.

        :return: List of ``{title, url, dates, location}`` dicts.
        """
        search_url = (
            f"{self.BASE_URL}/cfp/servlet/tool.search?q={conf_abbr}+{year}&year=a"
        )
        success, html = self.fetch_html(search_url, timeout=10, max_retries=2)
        if not success or html is None:
            print("  [!] Failed to fetch WikiCFP search page")
            return []

        soup = BeautifulSoup(html, "html.parser")
        events = []
        abbr_lower = conf_abbr.lower()
        year_str = str(year)

        # Find the results table (contains showcfp links).
        results_table = None
        for table in soup.find_all("table"):
            if table.find("a", href=lambda h: h and "showcfp" in h):
                results_table = table
                break
        if not results_table:
            return events

        rows = results_table.find_all("tr")
        i = 0
        while i < len(rows):
            row = rows[i]
            link_tag = row.find(
                "a", href=lambda h: h and h.startswith("/cfp/servlet/event.showcfp")
            )
            if link_tag:
                title = link_tag.get_text(strip=True)

                if abbr_lower in title.lower() and year_str in title:
                    event_url = self.BASE_URL + link_tag["href"]
                    dates = ""
                    location = ""
                    if i + 1 < len(rows):
                        detail_cells = rows[i + 1].find_all("td")
                        if len(detail_cells) >= 2:
                            dates = detail_cells[0].get_text(strip=True)
                            location = detail_cells[1].get_text(strip=True)

                    events.append(
                        {
                            "title": title,
                            "url": event_url,
                            "dates": dates,
                            "location": location,
                        }
                    )

            i += 1

        # Only keep events whose title matches the main conference
        # (e.g., "AAAI 2025"), not workshops ("CFAgentic @ ICML 2025").
        return [
            e
            for e in events
            if e["title"].replace(year_str, "").strip(" :").lower() == abbr_lower
        ]

    @staticmethod
    def _clean_text(text):
        """Normalize Unicode and remove WikiCFP navigation artifacts."""
        text = unicodedata.normalize("NFKC", text)
        text = text.replace("\u200b", "").replace("\ufeff", "")
        text = text.replace("\u2028", "\n").replace("\u2029", "\n")
        text = re.sub(r"\|back to top\|", "", text, flags=re.IGNORECASE)
        text = re.sub(r"^[=\-]{4,}$", "", text, flags=re.MULTILINE)
        text = re.sub(r"[^\S\n]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def _parse_event_page(self, html):
        """Extract structured data from a WikiCFP event page."""
        soup = BeautifulSoup(html, "html.parser")
        data = {}

        for row in soup.select("table.gglu tr"):
            th = row.find("th")
            td = row.find("td")
            if not th or not td:
                continue
            header = th.get_text(strip=True).rstrip(":").lower()
            value = td.get_text(strip=True)

            if "when" in header:
                data["dates"] = value
            elif "where" in header:
                data["location"] = value
            elif "submission" in header or "deadline" in header:
                data["submission_deadline"] = value
            elif "notification" in header:
                data["notification"] = value
            elif "final" in header or "camera" in header:
                data["camera_ready"] = value

        cfp_div = soup.find("div", class_="cfp")
        if cfp_div:
            data["cfp_text"] = self._clean_text(
                cfp_div.get_text(separator="\n", strip=True)
            )

        for link in soup.find_all("a"):
            href = link.get("href", "")
            text = link.get_text(strip=True).lower()
            if (
                ("link" in text or "website" in text)
                and href.startswith("http")
                and "wikicfp" not in href
            ):
                data["website"] = href
                break

        return data

    def crawl(self, conf_abbr, year, **kwargs):
        """Crawl WikiCFP for one conference -> ``data/wikicfp/{conf}/{year}.yaml``.

        :return: Dict with crawl results.
        """
        events = self.search_conference(conf_abbr, year)
        if not events:
            print(f"  [!] No matching event on WikiCFP for {conf_abbr} {year}")
            return {
                "conf": conf_abbr,
                "year": year,
                "success": False,
                "reason": "no_events",
            }

        event = events[0]
        print(f"  [+] Found WikiCFP event: {event['title']}")
        event_data = {
            "title": event["title"],
            "dates": event.get("dates", ""),
            "location": event.get("location", ""),
        }

        success, html = self.fetch_html(event["url"], timeout=10, max_retries=2)
        if success and html:
            event_data.update(self._parse_event_page(html))
        else:
            print("  [!] Failed to fetch WikiCFP event page")

        # Save structured metadata to data/wikicfp/.
        output_dir = self.data_dir / "wikicfp" / conf_abbr.lower()
        output_dir.mkdir(parents=True, exist_ok=True)
        output_file = output_dir / f"{year}.yaml"

        output_data = {
            "conference": conf_abbr,
            "year": year,
            "source": "wikicfp",
            "event_url": event["url"],
            **event_data,
        }

        with open(output_file, "w") as f:
            yaml.dump(
                output_data,
                f,
                default_flow_style=False,
                allow_unicode=True,
                sort_keys=False,
            )

        # Save full CFP text to data/raw/ for the extractor.
        cfp_text = event_data.get("cfp_text", "")
        if cfp_text:
            raw_dir = self.data_dir / "raw" / conf_abbr.lower() / str(year)
            raw_dir.mkdir(parents=True, exist_ok=True)
            raw_file = raw_dir / "wikicfp.txt"
            raw_file.write_text(cfp_text, encoding="utf-8")
            print(f"  [+] Saved CFP text to {raw_file} ({len(cfp_text)} bytes)")

        dates = event_data.get("dates", "")
        location = event_data.get("location", "")
        print(
            f"  [+] Saved WikiCFP data to {output_file} (dates: {dates}, location: {location})"
        )
        return {
            "conf": conf_abbr,
            "year": year,
            "success": True,
            "file": str(output_file),
        }

    def crawl_all(self, year, conferences=None):
        """Crawl WikiCFP data for all target conferences.

        :return: ``{total, success, failed}`` summary.
        """
        if conferences is None:
            conferences = self.load_conferences()

        total = len(conferences)
        success = 0
        failed = 0

        print(
            f"\n=== Fetching WikiCFP data for {total} conference(s), year {year} ===\n"
        )

        t0 = time.time()
        for i, conf in enumerate(conferences, 1):
            abbr = conf["short"]
            t1 = time.time()
            print(f"[{i}/{total}] {abbr} {year}")
            result = self.crawl(abbr, year)
            elapsed = time.time() - t1
            if result["success"]:
                success += 1
            else:
                failed += 1
            print(f"  [{elapsed:.1f}s]")

        total_time = time.time() - t0
        print(
            f"\n=== WikiCFP: {success} succeeded, {failed} failed out of {total} ({total_time:.1f}s) ==="
        )
        return {"total": total, "success": success, "failed": failed}
