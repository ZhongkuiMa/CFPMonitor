"""CCF Deadlines crawler.

Fetches conference data from the ``ccfddl/ccf-deadlines`` GitHub repository.
"""

import time

import yaml

from .base import BaseCrawler


class CCFDDLCrawler(BaseCrawler):
    """Fetches structured data (deadlines, links, dates) from ccfddl GitHub."""

    REPO_RAW = "https://raw.githubusercontent.com/ccfddl/ccf-deadlines/main"

    def __init__(self, data_dir="data", **kwargs):
        super().__init__(data_dir=data_dir, **kwargs)

    def _fetch_conf_yaml(self, area, dblp_key):
        """Fetch and parse ``conference/{area}/{dblp_key}.yml`` from GitHub.

        :rtype: dict or None
        """
        url = f"{self.REPO_RAW}/conference/{area}/{dblp_key}.yml"
        success, content = self.fetch_html(url, timeout=10, max_retries=2)
        if not success:
            return None
        data = yaml.safe_load(content)
        if isinstance(data, list):
            return data[0]
        return data

    def _match_year_entry(self, ccfddl_data, year):
        """Return the ``confs`` entry matching *year*, or ``None``.

        :rtype: dict or None
        """
        for entry in ccfddl_data.get("confs", []):
            if entry.get("year") == year:
                return entry
        return None

    def update_homepage_yaml(self, year, conferences):
        """Fill empty ``domain{year}`` entries in ``conferences_homepage.yaml``.

        :param year: Target year.
        :param conferences: Already-filtered list of conference dicts.
        :return: Number of entries updated.
        :rtype: int
        """
        homepage_file = self.data_dir / "metadata" / "conferences_homepage.yaml"
        with open(homepage_file) as f:
            homepage_data = yaml.safe_load(f)
        conferences_map = homepage_data.get("conferences", {})

        domain_key = f"domain{year}"
        updated = 0

        for conf in conferences:
            abbr = conf["short"]
            dblp_key = conf.get("dblp", "").lower()
            area = conf.get("area", "")

            if not dblp_key or not area:
                continue
            if conferences_map.get(abbr, {}).get(domain_key, "").strip():
                continue

            ccfddl_data = self._fetch_conf_yaml(area, dblp_key)
            if not ccfddl_data:
                continue

            year_entry = self._match_year_entry(ccfddl_data, year)
            if not year_entry:
                continue

            link = year_entry.get("link", "").strip()
            if not link:
                continue

            domain = link.removeprefix("https://").removeprefix("http://").rstrip("/")

            if abbr not in conferences_map:
                conferences_map[abbr] = {}
            conferences_map[abbr][domain_key] = domain
            updated += 1
            print(f"  [+] Updated {abbr} {domain_key}: {domain}")

        if updated > 0:
            homepage_data["conferences"] = conferences_map
            with open(homepage_file, "w") as f:
                yaml.dump(
                    homepage_data,
                    f,
                    default_flow_style=False,
                    allow_unicode=True,
                    sort_keys=True,
                )
            print(f"  [+] Saved {updated} updates to {homepage_file}")

        return updated

    def crawl(self, conf_abbr, year, **kwargs):
        """Fetch ccfddl data for one conference.

        Writes to ``data/ccfddl/{conf}/{year}.yaml``.

        :return: Dict with crawl result.
        :rtype: dict
        """
        conferences = self.load_conferences(conference=conf_abbr)
        if not conferences:
            print(f"  [!] {conf_abbr} not found in conferences.yaml")
            return {
                "conf": conf_abbr,
                "year": year,
                "success": False,
                "reason": "not_found",
            }

        conf = conferences[0]
        dblp_key = conf.get("dblp", "").lower()
        area = conf.get("area", "")

        if not dblp_key or not area:
            print(f"  [!] No dblp key or area for {conf_abbr}, skipping")
            return {
                "conf": conf_abbr,
                "year": year,
                "success": False,
                "reason": "no_dblp_key",
            }

        ccfddl_data = self._fetch_conf_yaml(area, dblp_key)
        if not ccfddl_data:
            print(f"  [!] Failed to fetch ccfddl YAML for {area}/{dblp_key}")
            return {
                "conf": conf_abbr,
                "year": year,
                "success": False,
                "reason": "fetch_failed",
            }

        year_entry = self._match_year_entry(ccfddl_data, year)
        if not year_entry:
            print(f"  [!] No {year} entry in ccfddl for {conf_abbr}")
            return {
                "conf": conf_abbr,
                "year": year,
                "success": False,
                "reason": "year_not_found",
            }

        output_dir = self.data_dir / "ccfddl" / conf_abbr.lower()
        output_dir.mkdir(parents=True, exist_ok=True)
        output_file = output_dir / f"{year}.yaml"

        output_data = {
            "conference": conf_abbr,
            "year": year,
            "title": ccfddl_data.get("title", ""),
            "description": ccfddl_data.get("description", ""),
            "dblp": dblp_key,
            "rank": ccfddl_data.get("rank", {}),
            "link": year_entry.get("link", ""),
            "date": year_entry.get("date", ""),
            "place": year_entry.get("place", ""),
            "timezone": year_entry.get("timezone", ""),
            "timeline": year_entry.get("timeline", []),
        }

        with open(output_file, "w") as f:
            yaml.dump(
                output_data,
                f,
                default_flow_style=False,
                allow_unicode=True,
                sort_keys=False,
            )

        date = year_entry.get("date", "")
        place = year_entry.get("place", "")
        print(
            f"  [+] Saved ccfddl data to {output_file} (date: {date}, place: {place})"
        )

        link = year_entry.get("link", "").strip()
        if link:
            self.save_link_page(conf_abbr, year, link)

        return {
            "conf": conf_abbr,
            "year": year,
            "success": True,
            "file": str(output_file),
        }

    def save_link_page(self, conf_abbr, year, link_url):
        """Fetch the ccfddl *link_url*, extract text, and save as raw data.

        Writes to ``data/raw/{conf}/{year}/ccfddl-link.txt``.

        :return: True if saved successfully.
        :rtype: bool
        """
        raw_dir = self.data_dir / "raw" / conf_abbr.lower() / str(year)
        output_file = raw_dir / "ccfddl-link.txt"
        if output_file.exists():
            print("  [+] ccfddl-link.txt already exists, skipping")
            return True

        success, html = self.fetch_html(link_url, timeout=10, max_retries=2)
        if not success or html is None:
            print(f"  [!] Failed to fetch ccfddl link page: {link_url}")
            return False

        text = self.extract_text(html)
        if len(text) < 50:
            print(f"  [!] ccfddl link page too short ({len(text)} chars), skipping")
            return False

        raw_dir.mkdir(parents=True, exist_ok=True)
        output_file.write_text(text, encoding="utf-8")
        print(f"  [+] Saved ccfddl-link.txt ({len(text)} bytes) from {link_url}")
        return True

    def crawl_all(self, year, conferences=None):
        """Crawl ccfddl data for all given conferences.

        :return: ``{total, success, failed}`` summary.
        :rtype: dict
        """
        if conferences is None:
            conferences = self.load_conferences()

        total = len(conferences)
        success = 0
        failed = 0

        print(
            f"\n=== Fetching ccfddl data for {total} conference(s), year {year} ===\n"
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
            f"\n=== ccfddl: {success} succeeded, {failed} failed out of {total} ({total_time:.1f}s) ==="
        )
        return {"total": total, "success": success, "failed": failed}
