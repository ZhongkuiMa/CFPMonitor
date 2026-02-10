#!/usr/bin/env python3
"""Validate conference homepage URLs from metadata file."""

from pathlib import Path
from typing import NamedTuple

import requests
import yaml

METADATA_FILE = (
    Path(__file__).parent.parent.parent
    / "data"
    / "metadata"
    / "conferences_homepage.yaml"
)
TIMEOUT = 5


class ValidationIssue(NamedTuple):
    conference: str
    year: int
    domain: str
    issue_type: str
    details: str


class URLValidator:
    """Validate homepage URLs for format and reachability."""

    def __init__(self):
        self.issues = []
        self.checked_count = 0
        self.reachable_count = 0
        self.suggestions = {}

    def validate_format(self, conf_abbr: str, year: int, domain: str) -> bool:
        """Check if domain string has valid URL format.

        :param conf_abbr: conference abbreviation
        :param year: conference year
        :param domain: domain string to validate
        :return: True if valid
        """
        if not domain or not domain.strip():
            return True

        if domain.startswith(("http://", "https://")):
            self.issues.append(
                ValidationIssue(
                    conf_abbr,
                    year,
                    domain,
                    "FORMAT",
                    "URL includes protocol (should be domain only)",
                )
            )
            return False

        if any(c in domain for c in "<>\"'\n\t"):
            self.issues.append(
                ValidationIssue(
                    conf_abbr, year, domain, "FORMAT", "Contains invalid characters"
                )
            )
            return False

        if "." not in domain and "/" not in domain:
            self.issues.append(
                ValidationIssue(
                    conf_abbr,
                    year,
                    domain,
                    "FORMAT",
                    "Does not look like a domain (no . or /)",
                )
            )
            return False

        return True

    def suggest_fix(self, domain: str, issue_type: str) -> str | None:
        """Suggest a fix for common domain issues.

        :param domain: domain that failed
        :param issue_type: type of error (``DNS_ERROR``, ``404``, etc.)
        :return: suggested domain fix or ``None``
        """
        if issue_type == "DNS_ERROR" and not domain.startswith("www."):
            www_domain = f"www.{domain}"
            try:
                resp = requests.head(f"https://{www_domain}", timeout=3)
                if 200 <= resp.status_code < 400:
                    return www_domain
            except requests.RequestException:
                pass

        if issue_type == "404" and "conf.researchr.org" in domain:
            fixed = domain.replace("conf.researchr.org/", "conf.researchr.org/home/")
            if fixed != domain:
                try:
                    resp = requests.head(f"https://{fixed}", timeout=3)
                    if 200 <= resp.status_code < 400:
                        return fixed
                except requests.RequestException:
                    pass

        if issue_type == "404" and "github.io" in domain:
            base_domain = domain.split("/")[0]
            try:
                resp = requests.head(f"https://{base_domain}", timeout=3)
                if 200 <= resp.status_code < 400:
                    return base_domain
            except requests.RequestException:
                pass

        return None

    def check_reachability(self, conf_abbr: str, year: int, domain: str) -> bool:
        """Check if URL is reachable.

        :param conf_abbr: conference abbreviation
        :param year: conference year
        :param domain: domain to check
        :return: True if reachable
        """
        if not domain or not domain.strip():
            return True

        url = f"https://{domain}" if not domain.startswith("http") else domain

        try:
            response = requests.head(url, timeout=TIMEOUT, allow_redirects=True)
        except requests.Timeout:
            self.issues.append(
                ValidationIssue(
                    conf_abbr, year, domain, "TIMEOUT", f"No response within {TIMEOUT}s"
                )
            )
            return False
        except requests.ConnectionError:
            self.issues.append(
                ValidationIssue(
                    conf_abbr,
                    year,
                    domain,
                    "DNS_ERROR",
                    "Cannot resolve domain or connect",
                )
            )
            suggestion = self.suggest_fix(domain, "DNS_ERROR")
            if suggestion:
                self.suggestions[f"{conf_abbr}_{year}"] = suggestion
            return False
        except requests.RequestException as e:
            self.issues.append(
                ValidationIssue(
                    conf_abbr,
                    year,
                    domain,
                    "ERROR",
                    f"{type(e).__name__}: {str(e)[:50]}",
                )
            )
            return False

        self.checked_count += 1

        if 200 <= response.status_code < 400:
            self.reachable_count += 1
            return True

        issue_type = f"HTTP_{response.status_code}"
        self.issues.append(
            ValidationIssue(
                conf_abbr, year, domain, issue_type, f"HTTP {response.status_code}"
            )
        )
        suggestion = self.suggest_fix(domain, issue_type)
        if suggestion:
            self.suggestions[f"{conf_abbr}_{year}"] = suggestion
        return False

    def validate_all(self, check_reachability: bool = True):
        """Validate all URLs in metadata file.

        :param check_reachability: whether to test HTTP reachability
        :return: ``(total_urls, valid_urls)``
        """
        with open(METADATA_FILE) as f:
            data = yaml.safe_load(f)

        conferences = data.get("conferences", {})
        total_urls = 0
        valid_urls = 0

        for conf_abbr, years_data in sorted(conferences.items()):
            for year_key in ["domain2024", "domain2025", "domain2026"]:
                domain = years_data.get(year_key, "")
                year = int(year_key.replace("domain", ""))
                total_urls += 1

                if not self.validate_format(conf_abbr, year, domain):
                    continue

                if not domain or not domain.strip():
                    valid_urls += 1
                    continue

                valid_urls += 1
                if check_reachability:
                    self.check_reachability(conf_abbr, year, domain)

        return total_urls, valid_urls

    def report(self):
        """Print validation report with suggestions."""
        print("\n" + "=" * 80)
        print("HOMEPAGE URL VALIDATION REPORT")
        print("=" * 80)

        total_urls, valid_urls = self.validate_all(check_reachability=False)

        if not self.issues:
            print("\n[OK] All URLs validated successfully!")
            print(f"  Total URLs: {total_urls}")
            print(f"  Valid: {valid_urls}")
            return

        issues_by_type = {}
        for issue in self.issues:
            issues_by_type.setdefault(issue.issue_type, []).append(issue)

        print(f"\n[FAIL] Found {len(self.issues)} issue(s) out of {total_urls} URLs:")
        print(f"  Total URLs: {total_urls}")
        print(f"  Valid: {valid_urls}")
        print(f"  Issues: {len(self.issues)}")

        for issue_type in sorted(issues_by_type):
            issues = issues_by_type[issue_type]
            print(f"\n{issue_type} ({len(issues)} issues):")
            for issue in sorted(issues):
                key = f"{issue.conference}_{issue.year}"
                suggestion = self.suggestions.get(key)

                print(f"  {issue.conference} {issue.year}: {issue.domain}")
                print(f"    -> {issue.details}")

                if suggestion:
                    print(f"    Suggestion: Try {suggestion}")

        print(
            f"\nReachability check: {self.checked_count} URLs checked, "
            f"{self.reachable_count} reachable"
        )

        if self.suggestions:
            print(f"\n{'-' * 80}")
            print(f"SUGGESTIONS: {len(self.suggestions)} potential fixes found")
            print("Suggested Fixes (paste into YAML):")
            print(f"{'-' * 80}")

            for key, suggestion in sorted(self.suggestions.items()):
                conf, year = key.split("_")
                print(f"{conf:15} domain{year}: {suggestion}")


if __name__ == "__main__":
    validator = URLValidator()
    validator.report()
