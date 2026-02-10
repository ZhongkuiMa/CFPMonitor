#!/usr/bin/env python3
"""Static website builder for CFPMonitor.

Generates ``docs/index.html`` from structured conference YAML data.
"""

import logging
from pathlib import Path

import yaml

from ..extractor.normalizers import extract_location_info
from .generate_schema import generate_rule_definitions
from .renderer import PageRenderer

logger = logging.getLogger(__name__)


class SiteBuilder:
    """Build static website from structured data."""

    def __init__(
        self,
        structured_root: str = "data/structured",
        output_dir: str = "docs",
        metadata_dir: str = "data/metadata",
        template_dir: str = "src/site/templates",
    ):
        """Initialize builder.

        :param structured_root: Root directory for structured YAML files
        :param output_dir: Output directory for website
        :param metadata_dir: Path to metadata directory (contains conferences.yaml and areas.yaml)
        :param template_dir: Directory containing Jinja2 templates
        """
        self.structured_root = Path(structured_root)
        self.output_dir = Path(output_dir)
        self.metadata_dir = Path(metadata_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.renderer = PageRenderer(template_dir)

    def build(self) -> Path:
        """Build the website.

        :return: Path to generated index.html
        """
        # Generate JavaScript schema from fields.yaml
        self._generate_schema()

        conferences = self._load_all_conferences()
        metadata_db, areas = self._load_conference_metadata()
        homepage_db = self._load_homepage_metadata()
        conferences = [
            self._merge_metadata(conf, metadata_db, homepage_db) for conf in conferences
        ]
        conferences = [c for c in conferences if self._is_visible(c)]

        html = self.renderer.render_page(conferences, areas)

        output_file = self.output_dir / "index.html"
        output_file.write_text(html, encoding="utf-8")

        return output_file

    def _load_all_conferences(self) -> list[dict]:
        """Load all conference YAML files.

        :return: List of conference dictionaries
        """
        conferences = []

        for yaml_file in self.structured_root.glob("*/*.yaml"):
            with open(yaml_file, encoding="utf-8") as f:
                data = yaml.safe_load(f)
                if (
                    data
                    and isinstance(data, dict)
                    and data.get("conference")
                    and data.get("conference") != "UNKNOWN"
                ):
                    rules = data.get("rules", {})
                    if rules and any(
                        r.get("value") not in ["unknown", None, {}]
                        for r in rules.values()
                    ):
                        conferences.append(data)

        conferences.sort(key=lambda c: c.get("conference", ""))

        return conferences

    def _load_conference_metadata(self) -> tuple[dict, dict]:
        """Load conference and area metadata.

        :return: ``(conference_dict, areas_dict)`` where conference_dict maps
                 uppercase short names to metadata, and areas_dict maps area
                 codes to full names.
        """
        conferences_db = {}
        areas_db = {}

        conf_file = self.metadata_dir / "conferences.yaml"
        if conf_file.exists():
            with open(conf_file, encoding="utf-8") as f:
                data = yaml.safe_load(f)
            conferences_db = {
                conf["short"].upper(): conf for conf in data.get("conferences", [])
            }

        areas_file = self.metadata_dir / "areas.yaml"
        if areas_file.exists():
            with open(areas_file, encoding="utf-8") as f:
                data = yaml.safe_load(f)
            areas_db = data.get("areas", {})

        return conferences_db, areas_db

    def _load_homepage_metadata(self) -> dict:
        """Load conference homepage URLs from ``conferences_homepage.yaml``.

        :return: dict mapping conference short names to homepage entries
        """
        homepage_file = self.metadata_dir / "conferences_homepage.yaml"
        if not homepage_file.exists():
            return {}
        with open(homepage_file, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return data.get("conferences", {})

    def _merge_metadata(
        self, conference: dict, metadata_db: dict, homepage_db: dict
    ) -> dict:
        """Merge CFPMonitor rule data with ReviewerCalls metadata.

        :param conference: Conference data
        :param metadata_db: Metadata database
        :param homepage_db: Homepage URL database
        :return: Conference with merged metadata
        """
        short_name = conference.get("conference", "").upper()
        # Create a COPY of metadata to avoid sharing dict objects across conferences
        conference["metadata"] = metadata_db.get(short_name, {}).copy()

        # Add year-specific homepage URL
        year = conference.get("year", "")
        homepage_entry = homepage_db.get(short_name, {})
        domain = homepage_entry.get(f"domain{year}", "")
        conference["homepage"] = f"https://{domain}" if domain else ""

        rules = conference.get("rules", {})
        total_rules = len(rules)
        known_rules = sum(
            1 for rule in rules.values() if rule.get("value") != "unknown"
        )
        conference["completeness_percent"] = (
            int((known_rules / total_rules) * 100) if total_rules else 0
        )

        # Re-normalize location from raw value at build time
        # This ensures normalizer fixes take effect without re-extracting all conferences
        if "metadata" not in conference:
            conference["metadata"] = {}

        location_rule = rules.get("conference_location", {})
        raw_location = location_rule.get("value", "")
        if raw_location and raw_location not in ("unknown", ""):
            city, country, display = extract_location_info(raw_location)
            conference["metadata"]["location"] = {
                "city": city,
                "country": country,
                "display": display,
                "raw": raw_location,
            }
        else:
            conference["metadata"]["location"] = {
                "city": None,
                "country": None,
                "display": "Unknown",
                "raw": raw_location,
            }

        return conference

    @staticmethod
    def _is_visible(conference: dict) -> bool:
        """Check if a conference card should be shown on the site.

        Requires a homepage link, a known location, and a known deadline.

        :param conference: merged conference data
        :return: True if the card should be displayed
        """
        if not conference.get("homepage"):
            return False

        rules = conference.get("rules", {})
        _unknown = ("unknown", "", None)
        location = rules.get("conference_location", {}).get("value", "unknown")
        deadline = rules.get("submission_deadline", {}).get("value", "unknown")
        return location not in _unknown and deadline not in _unknown

    def _generate_schema(self) -> None:
        """Generate JavaScript schema from fields.yaml.

        The generated schema is the canonical source of truth for field definitions
        and ensures the frontend stays in sync with the backend schema.
        """
        output = generate_rule_definitions()
        output_path = self.output_dir / "js" / "generated_schema.js"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(output, encoding="utf-8")
        logger.debug(f"Generated {output_path}")


def build_site(
    structured_root: str = "data/structured",
    output_dir: str = "docs",
    metadata_dir: str = "data/metadata",
) -> Path:
    """Build the CFPMonitor website.

    :param structured_root: Root directory for structured YAML files
    :param output_dir: Output directory
    :param metadata_dir: Path to metadata directory (contains conferences.yaml and areas.yaml)
    :return: Path to generated index.html
    """
    builder = SiteBuilder(structured_root, output_dir, metadata_dir)
    return builder.build()
