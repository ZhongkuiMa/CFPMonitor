#!/usr/bin/env python3
"""Extraction coverage verification and daily monitoring report.

Analyzes extraction coverage across all conferences, diagnoses why
extraction fails (gap analysis), and produces actionable metrics.

Usage:
    python src/verify_extraction.py [--year 2025] [--json]
    python cfpmonitor.py report [--year 2025] [--json]
"""

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import yaml

FIELDS_FILE = Path(__file__).parent / "extractor" / "fields.yaml"
PATTERNS_FILE = Path(__file__).parent / "extractor" / "patterns.yaml"
BASE_DATA_DIR = Path(__file__).parent.parent / "data"


# ------------------------------------------------------------------
# Data loading
# ------------------------------------------------------------------


def _discover_years(data_dir):
    """Return sorted list of available years in structured data."""
    structured = Path(data_dir) / "structured"
    years = set()
    for conf_dir in structured.iterdir():
        if not conf_dir.is_dir():
            continue
        for f in conf_dir.glob("*.yaml"):
            stem = f.stem
            if stem.isdigit():
                years.add(int(stem))
    return sorted(years)


def _load_structured(data_dir, year):
    """Load structured YAML for all conferences in *year*.

    :return: ``{conf_name: data_dict}``
    """
    structured = Path(data_dir) / "structured"
    conferences = {}
    for conf_dir in sorted(structured.iterdir()):
        if not conf_dir.is_dir():
            continue
        path = conf_dir / f"{year}.yaml"
        if path.exists():
            with open(path) as f:
                data = yaml.safe_load(f)
            if data:
                conferences[conf_dir.name] = data
    return conferences


def _load_raw_texts(data_dir, conf_name, year):
    """Concatenate all raw text files for a conference-year."""
    raw_dir = Path(data_dir) / "raw" / conf_name / str(year)
    if not raw_dir.is_dir():
        return ""
    parts = []
    for txt in sorted(raw_dir.glob("*.txt")):
        parts.append(txt.read_text(errors="replace"))
    return "\n".join(parts)


def _load_fields():
    """Load field definitions from fields.yaml."""
    with open(FIELDS_FILE) as f:
        return yaml.safe_load(f)


def _load_pattern_keywords():
    """Load positive_keywords from patterns.yaml for gap analysis."""
    with open(PATTERNS_FILE) as f:
        patterns = yaml.safe_load(f)
    keywords = {}
    for field, cfg in patterns.items():
        kws = cfg.get("positive_keywords", [])
        if kws:
            keywords[field] = [kw.lower() for kw in kws]
    return keywords


# ------------------------------------------------------------------
# Analysis helpers
# ------------------------------------------------------------------


def _field_value(rules, field):
    """Extract the resolved value for a field from rules dict."""
    entry = rules.get(field, {})
    if isinstance(entry, dict):
        return entry.get("value", "unknown")
    return entry


def _is_known(value):
    return value is not None and value not in ("unknown", "Unknown", "")


def _compute_coverage(conferences, fields):
    """Per-field coverage stats.

    :return: ``{field: {extracted, total, percentage}}``
    """
    total = len(conferences)
    coverage = {}
    for field in fields:
        extracted = 0
        for conf_data in conferences.values():
            rules = conf_data.get("rules", {})
            if _is_known(_field_value(rules, field)):
                extracted += 1
        pct = (extracted / total * 100) if total else 0
        coverage[field] = {
            "extracted": extracted,
            "total": total,
            "percentage": round(pct, 1),
        }
    return coverage


def _category_summary(coverage, fields_cfg):
    """Average coverage grouped by category."""
    cats = defaultdict(list)
    for field, cfg in fields_cfg.items():
        cat = cfg.get("category", "uncategorized")
        if field in coverage:
            cats[cat].append(coverage[field]["percentage"])
    summary = {}
    for cat, pcts in sorted(cats.items()):
        summary[cat] = round(sum(pcts) / len(pcts), 1) if pcts else 0
    return summary


def _gap_analysis(conferences, data_dir, year, pattern_keywords):
    """For each field, count conferences that have keywords in raw text but no extraction.

    :return: ``{field: {keyword_in_raw, extracted, gap, gap_conferences}}``
    """
    gaps = {}
    for field, keywords in pattern_keywords.items():
        keyword_found = 0
        extracted = 0
        gap_confs = []
        for conf_name, conf_data in conferences.items():
            rules = conf_data.get("rules", {})
            has_value = _is_known(_field_value(rules, field))
            raw = _load_raw_texts(data_dir, conf_name, year).lower()
            has_keyword = any(kw in raw for kw in keywords)
            if has_keyword:
                keyword_found += 1
            if has_value:
                extracted += 1
            if has_keyword and not has_value:
                gap_confs.append(conf_name)
        gaps[field] = {
            "keyword_in_raw": keyword_found,
            "extracted": extracted,
            "gap": len(gap_confs),
            "gap_conferences": gap_confs[:10],
        }
    return gaps


def _per_conference_health(conferences, fields_cfg):
    """Return conferences sorted by completeness (ascending).

    :return: list of ``(conf_name, known, total, pct)``
    """
    all_fields = list(fields_cfg.keys())
    results = []
    for conf_name, conf_data in conferences.items():
        rules = conf_data.get("rules", {})
        known = sum(1 for f in all_fields if _is_known(_field_value(rules, f)))
        total = len(all_fields)
        pct = round(known / total * 100, 1) if total else 0
        results.append((conf_name, known, total, pct))
    results.sort(key=lambda x: x[3])
    return results


def _conflict_summary(conferences):
    """Count and list field conflicts across all conferences."""
    conflicts = []
    for conf_name, conf_data in conferences.items():
        quality = conf_data.get("quality", {})
        for conflict in quality.get("conflicts", []):
            conflicts.append(
                {
                    "conference": conf_name,
                    "field": conflict.get("field", ""),
                    "values": conflict.get("values", {}),
                }
            )
    return conflicts


# ------------------------------------------------------------------
# Output formatters
# ------------------------------------------------------------------


def _print_report(
    year, conferences, coverage, cat_summary, gaps, health, conflicts, fields_cfg
):
    total = len(conferences)
    print()
    print("=" * 70)
    print(f"  EXTRACTION COVERAGE REPORT — {year}  ({total} conferences)")
    print("=" * 70)

    # 1. Category summary
    print("\n1. COVERAGE BY CATEGORY:\n")
    for cat, avg in sorted(cat_summary.items(), key=lambda x: x[1], reverse=True):
        bar = "#" * int(avg / 2)
        print(f"   {cat.replace('_', ' ').title():40s} {avg:5.1f}%  {bar}")

    # 2. Per-field coverage
    print("\n2. PER-FIELD COVERAGE:\n")
    print(f"   {'Field':<40s} {'Extracted':>9s} {'Total':>6s} {'Coverage':>9s}")
    print(f"   {'-' * 40} {'-' * 9} {'-' * 6} {'-' * 9}")
    for field in sorted(
        coverage.keys(), key=lambda f: coverage[f]["percentage"], reverse=True
    ):
        c = coverage[field]
        print(
            f"   {field:<40s} {c['extracted']:>9d} {c['total']:>6d} {c['percentage']:>8.1f}%"
        )

    # 3. Gap analysis (fields with <50% coverage that have keywords)
    gap_fields = {f: g for f, g in gaps.items() if g["gap"] > 0}
    if gap_fields:
        print("\n3. GAP ANALYSIS (keyword in raw text but extraction failed):\n")
        print(f"   {'Field':<35s} {'Keyword':>8s} {'Extracted':>10s} {'Gap':>5s}")
        print(f"   {'-' * 35} {'-' * 8} {'-' * 10} {'-' * 5}")
        for field, g in sorted(
            gap_fields.items(), key=lambda x: x[1]["gap"], reverse=True
        ):
            print(
                f"   {field:<35s} {g['keyword_in_raw']:>8d} {g['extracted']:>10d} {g['gap']:>5d}"
            )
            if g["gap_conferences"]:
                confs_str = ", ".join(g["gap_conferences"][:5])
                extra = f" (+{g['gap'] - 5} more)" if g["gap"] > 5 else ""
                print(f"     missed: {confs_str}{extra}")

    # 4. Low-health conferences (<20% completeness)
    low_health = [(n, k, t, p) for n, k, t, p in health if p < 20]
    if low_health:
        print(
            f"\n4. LOW-HEALTH CONFERENCES (<20% completeness, {len(low_health)} total):\n"
        )
        for name, known, tot, pct in low_health[:15]:
            print(f"   {name:<30s} {known:>3d}/{tot} ({pct:5.1f}%)")
        if len(low_health) > 15:
            print(f"   ... and {len(low_health) - 15} more")

    # 5. Conflicts
    if conflicts:
        print(f"\n5. FIELD CONFLICTS ({len(conflicts)} total):\n")
        for c in conflicts[:10]:
            vals = ", ".join(f"{src}: {v}" for src, v in c["values"].items())
            print(f"   {c['conference']:<20s} {c['field']:<30s} {vals[:60]}")
        if len(conflicts) > 10:
            print(f"   ... and {len(conflicts) - 10} more")

    # 6. Summary stats
    avg_coverage = (
        sum(c["percentage"] for c in coverage.values()) / len(coverage)
        if coverage
        else 0
    )
    zero_fields = [f for f, c in coverage.items() if c["percentage"] == 0]
    print("\n6. SUMMARY:\n")
    print(f"   Conferences:           {total}")
    print(f"   Fields tracked:        {len(coverage)}")
    print(f"   Average field coverage: {avg_coverage:.1f}%")
    print(f"   Zero-coverage fields:  {len(zero_fields)}")
    if zero_fields:
        print(f"     {', '.join(sorted(zero_fields))}")
    print(f"   Total conflicts:       {len(conflicts)}")
    print()


def _build_json_report(
    year, conferences, coverage, cat_summary, gaps, health, conflicts
):
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "year": year,
        "conference_count": len(conferences),
        "coverage": coverage,
        "category_summary": cat_summary,
        "gap_analysis": {
            f: {k: v for k, v in g.items() if k != "gap_conferences"}
            for f, g in gaps.items()
        },
        "low_health_conferences": [
            {"conference": n, "known": k, "total": t, "percentage": p}
            for n, k, t, p in health
            if p < 20
        ],
        "conflict_count": len(conflicts),
        "conflicts": conflicts[:50],
    }


# ------------------------------------------------------------------
# Main entry point
# ------------------------------------------------------------------


def run_report(year=None, data_dir=None, json_output=False):
    """Run the extraction coverage report.

    :param year: Target year (None = latest available)
    :param data_dir: Data directory path
    :param json_output: If True, write JSON report to data/reports/
    :return: 0 on success
    """
    data_dir = str(data_dir or BASE_DATA_DIR)

    available_years = _discover_years(data_dir)
    if not available_years:
        print("No structured data found.")
        return 1

    if year is None:
        year = available_years[-1]
    elif year not in available_years:
        print(f"Year {year} not found. Available: {available_years}")
        return 1

    conferences = _load_structured(data_dir, year)
    if not conferences:
        print(f"No conferences found for {year}.")
        return 1

    fields_cfg = _load_fields()
    pattern_keywords = _load_pattern_keywords()

    coverage = _compute_coverage(conferences, fields_cfg.keys())
    cat_summary = _category_summary(coverage, fields_cfg)
    gaps = _gap_analysis(conferences, data_dir, year, pattern_keywords)
    health = _per_conference_health(conferences, fields_cfg)
    conflicts = _conflict_summary(conferences)

    if json_output:
        report = _build_json_report(
            year, conferences, coverage, cat_summary, gaps, health, conflicts
        )
        reports_dir = Path(data_dir) / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        date_str = datetime.now().strftime("%Y%m%d")
        out_path = reports_dir / f"coverage_{year}_{date_str}.json"
        with open(out_path, "w") as f:
            json.dump(report, f, indent=2, default=str)
        print(f"JSON report written to {out_path}")
    else:
        _print_report(
            year,
            conferences,
            coverage,
            cat_summary,
            gaps,
            health,
            conflicts,
            fields_cfg,
        )

    return 0


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Extraction coverage report")
    parser.add_argument(
        "--year", type=int, default=None, help="Target year (default: latest available)"
    )
    parser.add_argument(
        "--json", action="store_true", help="Write JSON report to data/reports/"
    )
    parser.add_argument(
        "--data-dir", type=str, default=None, help="Data directory (default: data/)"
    )
    args = parser.parse_args()
    sys.exit(run_report(year=args.year, data_dir=args.data_dir, json_output=args.json))


if __name__ == "__main__":
    main()
