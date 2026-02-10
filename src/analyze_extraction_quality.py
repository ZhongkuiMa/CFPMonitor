#!/usr/bin/env python3
"""Extraction quality assessment with actionable diagnostics.

Examines pattern matching gaps, value quality issues, source agreement,
and produces a per-field summary dashboard.

Usage:
    python src/analyze_extraction_quality.py [--year 2025] [--field double_blind]
    python cfpmonitor.py quality [--year 2025] [--field double_blind]
"""

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

import yaml

FIELDS_FILE = Path(__file__).parent / "extractor" / "fields.yaml"
PATTERNS_FILE = Path(__file__).parent / "extractor" / "patterns.yaml"
BASE_DATA_DIR = Path(__file__).parent.parent / "data"

# Snippet window: chars before/after a keyword match to show context
_SNIPPET_WINDOW = 80


# ------------------------------------------------------------------
# Data loading (shared helpers)
# ------------------------------------------------------------------


def _discover_years(data_dir):
    structured = Path(data_dir) / "structured"
    years = set()
    for conf_dir in structured.iterdir():
        if not conf_dir.is_dir():
            continue
        for f in conf_dir.glob("*.yaml"):
            if f.stem.isdigit():
                years.add(int(f.stem))
    return sorted(years)


def _load_structured(data_dir, year):
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
    raw_dir = Path(data_dir) / "raw" / conf_name / str(year)
    if not raw_dir.is_dir():
        return ""
    parts = []
    for txt in sorted(raw_dir.glob("*.txt")):
        parts.append(txt.read_text(errors="replace"))
    return "\n".join(parts)


def _load_fields():
    with open(FIELDS_FILE) as f:
        return yaml.safe_load(f)


def _load_patterns():
    with open(PATTERNS_FILE) as f:
        return yaml.safe_load(f)


def _field_value(rules, field):
    entry = rules.get(field, {})
    if isinstance(entry, dict):
        return entry.get("value", "unknown")
    return entry


def _is_known(value):
    return value is not None and value not in ("unknown", "Unknown", "")


# ------------------------------------------------------------------
# Pattern gap analysis
# ------------------------------------------------------------------


def _extract_snippets(text, keyword, max_snippets=3):
    """Find text snippets around keyword occurrences."""
    snippets = []
    lower = text.lower()
    kw_lower = keyword.lower()
    start = 0
    while len(snippets) < max_snippets:
        idx = lower.find(kw_lower, start)
        if idx == -1:
            break
        left = max(0, idx - _SNIPPET_WINDOW)
        right = min(len(text), idx + len(keyword) + _SNIPPET_WINDOW)
        snippet = text[left:right].replace("\n", " ").strip()
        if left > 0:
            snippet = "..." + snippet
        if right < len(text):
            snippet = snippet + "..."
        snippets.append(snippet)
        start = idx + len(keyword)
    return snippets


def _pattern_gap_analysis(conferences, data_dir, year, patterns_cfg, field_filter=None):
    """For each field with patterns, find conferences where keywords appear
    in raw text but regex patterns don't match.

    Returns per-field stats with top missed phrasings (actual snippets).
    """
    results = {}
    fields_to_check = [field_filter] if field_filter else list(patterns_cfg.keys())

    for field in fields_to_check:
        if field not in patterns_cfg:
            continue
        cfg = patterns_cfg[field]
        keywords = [kw.lower() for kw in cfg.get("positive_keywords", [])]
        compiled_patterns = []
        for pat in cfg.get("patterns", []):
            try:
                compiled_patterns.append(
                    re.compile(pat["regex"], re.IGNORECASE | re.MULTILINE)
                )
            except re.error:
                pass

        if not keywords and not compiled_patterns:
            continue

        keyword_found = 0
        extracted = 0
        gap_count = 0
        missed_snippets = []

        for conf_name, conf_data in conferences.items():
            rules = conf_data.get("rules", {})
            has_value = _is_known(_field_value(rules, field))
            raw = _load_raw_texts(data_dir, conf_name, year)
            raw_lower = raw.lower()

            has_keyword = any(kw in raw_lower for kw in keywords) if keywords else False
            has_pattern_match = (
                any(p.search(raw) for p in compiled_patterns)
                if compiled_patterns
                else False
            )

            if has_keyword or has_pattern_match:
                keyword_found += 1
            if has_value:
                extracted += 1
            if (has_keyword or has_pattern_match) and not has_value:
                gap_count += 1
                # Collect a snippet showing what was missed
                for kw in keywords:
                    snips = _extract_snippets(raw, kw, max_snippets=1)
                    for s in snips:
                        missed_snippets.append((conf_name, s))
                    if missed_snippets:
                        break

        results[field] = {
            "keyword_in_raw": keyword_found,
            "extracted": extracted,
            "gap": gap_count,
            "missed_snippets": missed_snippets[:10],
        }
    return results


# ------------------------------------------------------------------
# Value validation
# ------------------------------------------------------------------


def _validate_values(conferences, fields_cfg):
    """Check extracted values for common quality issues.

    Returns ``{issue_type: [(conf, field, value, detail), ...]}``
    """
    issues = defaultdict(list)
    current_year = 2026

    for conf_name, conf_data in conferences.items():
        rules = conf_data.get("rules", {})

        # Date validation: flag obviously wrong dates
        date_fields = [f for f, c in fields_cfg.items() if c.get("type") == "date"]
        for field in date_fields:
            val = _field_value(rules, field)
            if not _is_known(val) or not isinstance(val, str):
                continue
            # Check for past-year dates in a future conference
            for old_year in range(2015, current_year - 1):
                if str(old_year) in val:
                    issues["stale_date"].append(
                        (conf_name, field, val, f"contains year {old_year}")
                    )
                    break

        # Location validation: too short or contains boilerplate
        loc_val = _field_value(rules, "conference_location")
        if _is_known(loc_val) and isinstance(loc_val, str):
            if len(loc_val) < 3:
                issues["location_too_short"].append(
                    (conf_name, "conference_location", loc_val, "")
                )
            boilerplate = ["of the", "such as", "including", "submission"]
            for bp in boilerplate:
                if bp in loc_val.lower():
                    issues["location_boilerplate"].append(
                        (
                            conf_name,
                            "conference_location",
                            loc_val[:60],
                            f"contains '{bp}'",
                        )
                    )
                    break

        # Boolean field vs evidence contradiction
        for field in [f for f, c in fields_cfg.items() if c.get("type") == "boolean"]:
            entry = rules.get(field, {})
            if not isinstance(entry, dict):
                continue
            val = entry.get("value")
            evidence = str(entry.get("evidence", "")).lower()
            if val is True and any(
                neg in evidence for neg in ["not ", "no ", "without"]
            ):
                issues["boolean_evidence_conflict"].append(
                    (conf_name, field, str(val), evidence[:60])
                )
            elif val is False and not any(
                neg in evidence for neg in ["not ", "no ", "without", "single"]
            ):
                issues["boolean_evidence_conflict"].append(
                    (conf_name, field, str(val), evidence[:60])
                )

    return issues


# ------------------------------------------------------------------
# Source agreement
# ------------------------------------------------------------------


def _source_agreement(conferences, fields_cfg):
    """For fields with multiple sources, compute agreement rate.

    Returns ``{field: {total_multi_source, agree, disagree, agreement_pct}}``
    """
    results = {}
    for field in fields_cfg:
        total_multi = 0
        agree = 0
        disagree = 0
        for conf_data in conferences.values():
            rules = conf_data.get("rules", {})
            entry = rules.get(field, {})
            if not isinstance(entry, dict):
                continue
            sources = entry.get("_sources", {})
            source_vals = []
            for src, src_data in sources.items():
                v = src_data.get("value") if isinstance(src_data, dict) else src_data
                if v is not None and v not in ("unknown", "Unknown", ""):
                    source_vals.append(str(v).lower().strip())
            if len(source_vals) >= 2:
                total_multi += 1
                if len(set(source_vals)) == 1:
                    agree += 1
                else:
                    disagree += 1
        if total_multi > 0:
            results[field] = {
                "total_multi_source": total_multi,
                "agree": agree,
                "disagree": disagree,
                "agreement_pct": round(agree / total_multi * 100, 1),
            }
    return results


# ------------------------------------------------------------------
# Output
# ------------------------------------------------------------------


def _print_quality_report(
    year,
    conferences,
    gap_results,
    validation_issues,
    agreement,
    fields_cfg,
    field_filter,
):
    total = len(conferences)
    print()
    print("=" * 70)
    title = f"  EXTRACTION QUALITY REPORT — {year}  ({total} conferences)"
    if field_filter:
        title += f"  [field: {field_filter}]"
    print(title)
    print("=" * 70)

    # 1. Summary dashboard
    all_fields = list(fields_cfg.keys())
    print("\n1. FIELD SUMMARY DASHBOARD:\n")
    print(
        f"   {'Field':<35s} {'Coverage':>9s} {'Gap':>5s} {'Agree%':>7s} {'Issue':>6s}"
    )
    print(f"   {'-' * 35} {'-' * 9} {'-' * 5} {'-' * 7} {'-' * 6}")

    for field in all_fields:
        if field_filter and field != field_filter:
            continue
        # Coverage
        extracted = sum(
            1
            for cd in conferences.values()
            if _is_known(_field_value(cd.get("rules", {}), field))
        )
        cov_pct = round(extracted / total * 100, 1) if total else 0

        # Gap
        gap = gap_results.get(field, {}).get("gap", "-")

        # Agreement
        agr = agreement.get(field, {})
        agr_str = f"{agr['agreement_pct']}%" if agr else "-"

        # Issues count
        issue_count = sum(
            1
            for items in validation_issues.values()
            for _, f, _, _ in items
            if f == field
        )
        issue_str = str(issue_count) if issue_count else "-"

        print(
            f"   {field:<35s} {cov_pct:>8.1f}% {str(gap):>5s} {agr_str:>7s} {issue_str:>6s}"
        )

    # 2. Pattern gap analysis detail
    gap_with_data = {f: g for f, g in gap_results.items() if g["gap"] > 0}
    if gap_with_data:
        print("\n2. PATTERN GAP ANALYSIS (keyword found but no extraction):\n")
        for field, g in sorted(
            gap_with_data.items(), key=lambda x: x[1]["gap"], reverse=True
        ):
            print(
                f"   {field}: {g['gap']} missed "
                f"(keyword in {g['keyword_in_raw']}, extracted {g['extracted']})"
            )
            if g["missed_snippets"]:
                print("   Top missed phrasings:")
                seen = set()
                for conf, snippet in g["missed_snippets"][:5]:
                    # Deduplicate very similar snippets
                    short = snippet[:60]
                    if short not in seen:
                        seen.add(short)
                        print(f"     [{conf}] {snippet[:120]}")
            print()

    # 3. Value validation issues
    if validation_issues:
        print("\n3. VALUE VALIDATION ISSUES:\n")
        for issue_type, items in sorted(validation_issues.items()):
            filtered = items
            if field_filter:
                filtered = [(c, f, v, d) for c, f, v, d in items if f == field_filter]
            if not filtered:
                continue
            print(f"   {issue_type} ({len(filtered)} instances):")
            for conf, field, value, detail in filtered[:5]:
                extra = f" — {detail}" if detail else ""
                print(f"     {conf:<25s} {field:<30s} {value[:30]}{extra}")
            if len(filtered) > 5:
                print(f"     ... and {len(filtered) - 5} more")
            print()

    # 4. Source agreement
    multi_source = {f: a for f, a in agreement.items() if a["total_multi_source"] > 0}
    if multi_source:
        print("\n4. SOURCE AGREEMENT (fields with multi-source data):\n")
        print(
            f"   {'Field':<35s} {'Multi':>6s} {'Agree':>6s} {'Disagree':>9s} {'Rate':>7s}"
        )
        print(f"   {'-' * 35} {'-' * 6} {'-' * 6} {'-' * 9} {'-' * 7}")
        for field, a in sorted(
            multi_source.items(), key=lambda x: x[1]["agreement_pct"]
        ):
            if field_filter and field != field_filter:
                continue
            print(
                f"   {field:<35s} {a['total_multi_source']:>6d} "
                f"{a['agree']:>6d} {a['disagree']:>9d} {a['agreement_pct']:>6.1f}%"
            )

    print()


# ------------------------------------------------------------------
# Main entry point
# ------------------------------------------------------------------


def run_quality(year=None, data_dir=None, field=None):
    """Run the extraction quality analysis.

    :param year: Target year (None = latest available)
    :param data_dir: Data directory path
    :param field: Optional field name to focus on
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
    patterns_cfg = _load_patterns()

    gap_results = _pattern_gap_analysis(
        conferences, data_dir, year, patterns_cfg, field_filter=field
    )
    validation_issues = _validate_values(conferences, fields_cfg)
    agreement = _source_agreement(conferences, fields_cfg)

    _print_quality_report(
        year,
        conferences,
        gap_results,
        validation_issues,
        agreement,
        fields_cfg,
        field_filter=field,
    )
    return 0


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Extraction quality analysis")
    parser.add_argument(
        "--year", type=int, default=None, help="Target year (default: latest available)"
    )
    parser.add_argument(
        "--field",
        type=str,
        default=None,
        help="Focus on a specific field (e.g., double_blind)",
    )
    parser.add_argument(
        "--data-dir", type=str, default=None, help="Data directory (default: data/)"
    )
    args = parser.parse_args()
    sys.exit(run_quality(year=args.year, data_dir=args.data_dir, field=args.field))


if __name__ == "__main__":
    main()
