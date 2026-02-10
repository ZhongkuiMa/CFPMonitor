"""CFP rule extractor -- three-phase pipeline.

Phase 1 (Collect): gather raw texts + wikicfp cfp_text + structured sources
Phase 2 (Extract): regex pattern matching on the combined text corpus
Phase 3 (Merge):   structured overrides, conflict detection, quality report
"""

import re
from datetime import datetime
from pathlib import Path

import yaml

from .helpers import extract_context, extract_field_value
from .normalizers import normalize_rules

# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------


def _load_fields() -> dict:
    """Load field configurations from YAML.

    :return: field name -> field config mapping
    """
    path = Path(__file__).parent / "fields.yaml"
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _load_patterns() -> dict:
    """Load pattern definitions from YAML.

    :return: pattern group name -> pattern list mapping
    """
    path = Path(__file__).parent / "patterns.yaml"
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


# ---------------------------------------------------------------------------
# Config caching (Performance optimization)
# ---------------------------------------------------------------------------

_FIELDS_CACHE = None
_PATTERNS_CACHE = None
_COMPILED_PATTERNS_CACHE = None


def _get_fields() -> dict:
    """Load fields once, cache globally.

    :return: cached field configurations
    """
    global _FIELDS_CACHE
    if _FIELDS_CACHE is None:
        _FIELDS_CACHE = _load_fields()
    return _FIELDS_CACHE


def _get_patterns() -> dict:
    """Load patterns once, cache globally.

    :return: cached pattern definitions
    """
    global _PATTERNS_CACHE
    if _PATTERNS_CACHE is None:
        _PATTERNS_CACHE = _load_patterns()
    return _PATTERNS_CACHE


def _get_compiled_patterns() -> dict:
    """Load and compile patterns once, cache globally.

    Pre-compiles all regex patterns to avoid repeated compilation overhead.

    :return: ``{field_name: [{"name": str, "compiled": re.Pattern, "raw_regex": str}]}``
    """
    global _COMPILED_PATTERNS_CACHE
    if _COMPILED_PATTERNS_CACHE is not None:
        return _COMPILED_PATTERNS_CACHE

    patterns = _get_patterns()
    compiled = {}

    for field_name, config in patterns.items():
        field_patterns = config.get("patterns", [])
        compiled[field_name] = [
            {
                "name": p["name"],
                "compiled": re.compile(p["regex"], re.IGNORECASE | re.MULTILINE),
                "raw_regex": p["regex"],  # Keep for debugging
            }
            for p in field_patterns
        ]

    _COMPILED_PATTERNS_CACHE = compiled
    return compiled


# ---------------------------------------------------------------------------
# Phase 1: Collect
# ---------------------------------------------------------------------------


def _load_raw_texts(conf_abbr: str, year: int, archive_root: str) -> dict[str, str]:
    """Load archived .txt files for a conference.

    :param conf_abbr: conference abbreviation (e.g. ``"icml"``)
    :param year: conference year
    :param archive_root: root directory for archived files
    :return: ``{filename_stem: text_content}``
    """
    archive_dir = Path(archive_root) / conf_abbr.lower() / str(year)
    if not archive_dir.exists():
        print(f"  [!] Archive directory not found: {archive_dir}")
        return {}

    txt_files = list(archive_dir.glob("*.txt"))
    if not txt_files:
        print(f"  [!] No files found in {archive_dir}")
        return {}

    texts = {f.stem: f.read_text(encoding="utf-8") for f in txt_files}
    print(f"  [+] Loaded {len(texts)} text files from {archive_dir}")
    return texts


def _load_structured_sources(conf_abbr: str, year: int, data_dir: str) -> dict:
    """Load structured data from ccfddl and wikicfp.

    :param conf_abbr: conference abbreviation
    :param year: conference year
    :param data_dir: root data directory containing ``ccfddl/`` and ``wikicfp/``
    :return: ``{"ccfddl": dict | None, "wikicfp": dict | None}``
    """
    sources = {}
    for name in ("ccfddl", "wikicfp"):
        path = Path(data_dir) / name / conf_abbr.lower() / f"{year}.yaml"
        if path.exists():
            with open(path, encoding="utf-8") as f:
                sources[name] = yaml.safe_load(f)
        else:
            sources[name] = None
    return sources


def _collect_all_sources(conf_abbr: str, year: int, data_dir: str) -> dict:
    """Collect all text and structured sources for extraction.

    Raw texts are namespaced as ``raw/<stem>``.  If wikicfp has non-empty
    ``cfp_text``, it is added as ``wikicfp/cfp_text`` so regex patterns
    can match against it.

    :param conf_abbr: conference abbreviation
    :param year: conference year
    :param data_dir: root data directory
    :return: ``{"texts": {key: text}, "structured": {"ccfddl": ..., "wikicfp": ...}}``
    """
    raw = _load_raw_texts(conf_abbr, year, f"{data_dir}/raw")
    texts = {f"raw/{k}": v for k, v in raw.items()}

    structured = _load_structured_sources(conf_abbr, year, data_dir)

    wikicfp = structured.get("wikicfp") or {}
    cfp_text = str(wikicfp.get("cfp_text", "")).strip()
    if cfp_text and cfp_text != "[Empty]":
        texts["wikicfp/cfp_text"] = cfp_text
        print(f"  [+] Added wikicfp cfp_text ({len(cfp_text)} chars)")

    return {"texts": texts, "structured": structured}


# ---------------------------------------------------------------------------
# Phase 2: Extract (regex)
# ---------------------------------------------------------------------------


def _create_default_tag(field_config: dict) -> dict:
    """Create a default rule entry with unknown value.

    :param field_config: field schema configuration
    :return: rule dict with default value
    """
    return {
        "value": field_config.get("default", "unknown"),
        "evidence": "",
        "category": field_config.get("category"),
        "priority": field_config.get("priority"),
    }


def _find_matches(text: str, patterns: list[dict]) -> list[dict]:
    """Return first pattern match in text.

    :param text: text to search
    :param patterns: list of compiled pattern dicts with ``name`` and ``compiled`` keys
    :return: single-element list with match info, or empty list
    """
    for pattern in patterns:
        m = pattern["compiled"].search(text)
        if m:
            return [
                {
                    "matched_text": m.group(0),
                    "start": m.start(),
                    "end": m.end(),
                    "pattern_name": pattern["name"],
                }
            ]
    return []


def _extract_rules(
    texts: dict[str, str], fields: dict, patterns: dict, year: int
) -> dict:
    """Extract rules by running regex patterns over concatenated texts.

    :param texts: ``{filename: text_content}``
    :param fields: field schema definitions
    :param patterns: pattern extraction config
    :param year: conference year for date normalization
    :return: ``{field_name: {value, evidence, category, priority}}``
    """
    rules = {}
    all_text = "\n\n".join(f"=== {name} ===\n{text}" for name, text in texts.items())

    # Get pre-compiled patterns for performance
    compiled_patterns = _get_compiled_patterns()

    for field_name, field_config in fields.items():
        pattern_config = patterns.get(field_name, {})
        compiled_field_patterns = compiled_patterns.get(field_name, [])

        if not compiled_field_patterns:
            rules[field_name] = _create_default_tag(field_config)
            continue

        matches = _find_matches(all_text, compiled_field_patterns)
        if not matches:
            rules[field_name] = _create_default_tag(field_config)
            continue

        value = extract_field_value(
            matches, all_text, field_config, pattern_config, year
        )
        match = matches[0]
        rules[field_name] = {
            "value": value,
            "category": field_config.get("category"),
            "priority": field_config.get("priority"),
            "evidence": extract_context(all_text, match["start"], match["end"]),
        }

    return rules


# ---------------------------------------------------------------------------
# Phase 3: Merge structured overrides + conflict detection
# ---------------------------------------------------------------------------

_STRUCTURED_FIELD_MAP = {
    "conference_dates": {"ccfddl": "date", "wikicfp": "dates"},
    "conference_location": {"ccfddl": "place", "wikicfp": "location"},
    "submission_deadline": {
        "ccfddl": "timeline.deadline",
        "wikicfp": "submission_deadline",
    },
    "abstract_deadline": {"ccfddl": "timeline.abstract_deadline"},
    "notification_date": {"wikicfp": "notification"},
    "camera_ready_deadline": {"wikicfp": "camera_ready"},
    "submission_system": {"ccfddl": "timeline._system"},
}

_KNOWN_SYSTEMS = ("OpenReview", "EasyChair", "CMT", "SoftConf", "HotCRP")

_MONTH_ABBRS = {
    "jan": "january",
    "feb": "february",
    "mar": "march",
    "apr": "april",
    "jun": "june",
    "jul": "july",
    "aug": "august",
    "sep": "september",
    "sept": "september",
    "oct": "october",
    "nov": "november",
    "dec": "december",
}


def _format_deadline(timestamp: str) -> str:
    """Convert ccfddl timestamp to human-readable date.

    :param timestamp: e.g. ``"2023-08-15 23:59:59"``
    :return: e.g. ``"August 15, 2023"``, or ``""`` on parse failure
    """
    try:
        dt = datetime.strptime(timestamp.strip(), "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return ""
    return dt.strftime("%B %-d, %Y")


def _extract_system_from_comments(timeline: list[dict]) -> str:
    """Extract submission system name from ccfddl timeline comments.

    :param timeline: list of timeline entry dicts
    :return: canonical system name, or ``""``
    """
    for entry in timeline:
        comment = entry.get("comment", "").lower()
        for system in _KNOWN_SYSTEMS:
            if system.lower() in comment:
                return system
    return ""


def _normalize_for_comparison(value: str) -> str:
    """Normalize a value for conflict comparison.

    Lowercases, expands month abbreviations, strips punctuation.

    :param value: raw value string
    :return: normalized string
    """
    if not value:
        return ""
    s = str(value).lower().strip()
    for abbr, full in _MONTH_ABBRS.items():
        s = re.sub(rf"\b{abbr}\b\.?", full, s)
    s = re.sub(r"[,;:()\"']", "", s)
    return re.sub(r"\s+", " ", s).strip()


def _has_conflict(values: dict[str, str]) -> bool:
    """Check whether source values disagree after normalization.

    :param values: ``{source_name: raw_value}``
    :return: True if two or more distinct normalized values exist
    """
    normalized = {
        _normalize_for_comparison(v) for v in values.values() if v and v != "unknown"
    }
    return len(normalized) > 1


def _resolve_value(data: dict, key: str) -> str:
    """Resolve a value from a structured source dict.

    Handles top-level keys (``"date"``, ``"place"``) and ``timeline.*``
    keys that read from ``timeline[0]``.  The special key
    ``timeline._system`` scans all timeline comments for system names.

    :param data: source data dict (ccfddl or wikicfp)
    :param key: key path
    :return: resolved string, or ``""``
    """
    if not key.startswith("timeline."):
        raw = data.get(key, "")
        return str(raw).strip() if raw else ""

    timeline = data.get("timeline") or []
    subkey = key[len("timeline.") :]

    if subkey == "_system":
        return _extract_system_from_comments(timeline)

    first = timeline[0] if timeline else {}
    raw = first.get(subkey, "")
    if not raw:
        return ""
    if subkey in ("deadline", "abstract_deadline"):
        return _format_deadline(str(raw))
    return str(raw).strip()


def _merge_with_structured(
    rules: dict, structured: dict, exclude_fields: set = None
) -> None:
    """Merge structured overrides into regex-extracted rules (in place).

    Priority: ccfddl > wikicfp > regex.
    Annotates each mapped field with ``_sources`` provenance and
    ``_conflict`` flag when sources disagree.

    :param rules: regex-extracted rules dict (modified in place)
    :param structured: ``{"ccfddl": dict | None, "wikicfp": dict | None}``
    :param exclude_fields: Set of field names to exclude from merging (e.g., unified extractor results)
    """
    if exclude_fields is None:
        exclude_fields = set()
    source_data = {
        "ccfddl": structured.get("ccfddl") or {},
        "wikicfp": structured.get("wikicfp") or {},
    }

    for field, source_map in _STRUCTURED_FIELD_MAP.items():
        if field not in rules:
            continue
        if field in exclude_fields:
            continue

        regex_val = rules[field].get("value")
        regex_evidence = rules[field].get("evidence", "")

        candidates = {}
        for src_name in ("ccfddl", "wikicfp"):
            src_key = source_map.get(src_name)
            if src_key and source_data[src_name]:
                val = _resolve_value(source_data[src_name], src_key)
                if val:
                    candidates[src_name] = val

        all_values = dict(candidates)
        if regex_val and regex_val not in ("unknown", ""):
            all_values["regex"] = regex_val

        sources_meta = {}
        if "regex" in all_values:
            sources_meta["regex"] = {"value": regex_val, "evidence": regex_evidence}
        for src_name, val in candidates.items():
            sources_meta[src_name] = {"value": val}

        for src_name in ("ccfddl", "wikicfp"):
            if src_name in candidates:
                rules[field]["value"] = candidates[src_name]
                rules[field]["evidence"] = src_name
                break

        if sources_meta:
            rules[field]["_sources"] = sources_meta
        if _has_conflict(all_values):
            rules[field]["_conflict"] = True


def _calculate_quality_report(rules: dict) -> tuple[dict, dict]:
    """Calculate completeness and quality metrics.

    :param rules: rules dict with ``_sources``/``_conflict`` annotations
    :return: ``(completeness, quality)`` dicts
    """
    total = len(rules)
    known = sum(
        1 for r in rules.values() if r.get("value") not in ("unknown", None, "", [])
    )

    completeness = {
        "known": known,
        "total": total,
        "percentage": round(known / total * 100, 1) if total else 0.0,
    }

    conflicts = []
    source_coverage = {"regex": 0, "ccfddl": 0, "wikicfp": 0}
    for field_name, rule in rules.items():
        sources_meta = rule.get("_sources", {})
        for src in source_coverage:
            if src in sources_meta:
                source_coverage[src] += 1
        if rule.get("_conflict"):
            values = {s: m["value"] for s, m in sources_meta.items() if "value" in m}
            conflicts.append({"field": field_name, "values": values})

    quality = {
        "conflict_count": len(conflicts),
        "conflicts": conflicts,
        "source_coverage": source_coverage,
    }

    print(f"  [+] Extracted {known}/{total} fields")
    if conflicts:
        print(f"  [!] {len(conflicts)} conflict(s) detected")

    return completeness, quality


# ---------------------------------------------------------------------------
# Unified Extraction
# ---------------------------------------------------------------------------


def _extract_unified_fields(texts: list[str], year: int) -> dict[str, dict]:
    """Extract fields using unified extractors and convert to legacy format.

    :param texts: List of CFP text sources
    :param year: Conference year
    :returns: Dictionary of rules in legacy format
    """
    from .unified_extractors import (
        extract_page_requirements_unified,
        extract_review_process_keywords,
        extract_policy_field,
        extract_statements_required,
        extract_submission_requirements,
        extract_conference_logistics,
        extract_track_detection,
    )

    all_text = "\n\n".join(texts)
    legacy_rules = {}

    page_req = extract_page_requirements_unified(all_text)
    legacy_rules.update(page_req.to_legacy_format())

    review = extract_review_process_keywords(all_text)
    legacy_rules.update(review.to_legacy_format())

    for policy_type in [
        "artifact_evaluation",
        "llm_policy",
        "concurrent_submission",
        "arxiv_preprint",
    ]:
        policy = extract_policy_field(all_text, policy_type)
        legacy_rules.update(policy.to_legacy_format(policy_type))

    statements = extract_statements_required(all_text)
    legacy_rules.update(statements.to_legacy_format())

    submit_req = extract_submission_requirements(all_text)
    legacy_rules.update(submit_req.to_legacy_format())

    logistics = extract_conference_logistics(all_text)
    legacy_rules.update(logistics.to_legacy_format())

    tracks = extract_track_detection(all_text)
    legacy_rules.update(tracks.to_legacy_format())

    return legacy_rules


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def extract_rules(conf_abbr: str, year: int, data_dir: str) -> dict:
    """Extract rules for a conference using the five-phase pipeline.

    1. **Collect** -- raw texts + wikicfp cfp_text + structured sources
    2. **Extract (Old)** -- regex pattern matching on combined text corpus
    3. **Extract (Unified)** -- unified extractors with confidence scoring
    4. **Merge** -- structured overrides, conflict detection
    5. **Normalize** -- standardize location, dates, and other fields

    :param conf_abbr: conference abbreviation (e.g. ``"ICML"``)
    :param year: conference year
    :param data_dir: root data directory
    :return: dict with ``rules``, ``completeness``, and ``quality``
    """
    sources = _collect_all_sources(conf_abbr, year, data_dir)
    if not sources["texts"]:
        return {}

    fields = _get_fields()
    patterns = _get_patterns()
    rules = _extract_rules(sources["texts"], fields, patterns, year)

    unified_rules = _extract_unified_fields(sources["texts"], year)
    unified_field_names = set()
    for field_name, rule_data in unified_rules.items():
        if rule_data.get("value") not in ("unknown", "", False):
            rules[field_name] = rule_data
            unified_field_names.add(field_name)

    _merge_with_structured(
        rules, sources["structured"], exclude_fields=unified_field_names
    )

    # Phase 5: Normalize extracted data
    rules = normalize_rules(rules)

    completeness, quality = _calculate_quality_report(rules)

    return {
        "conference": conf_abbr.upper(),
        "year": year,
        "last_checked": datetime.utcnow().isoformat() + "Z",
        "completeness": completeness,
        "quality": quality,
        "rules": rules,
    }


def save_rules(data: dict, output_root: str = "data/structured") -> Path:
    """Save extracted rules as YAML.

    :param data: complete extraction result dict
    :param output_root: root directory for output files
    :return: path to saved YAML file
    """
    output_dir = Path(output_root) / data["conference"].lower()
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"{data['year']}.yaml"

    with open(output_file, "w", encoding="utf-8") as f:
        yaml.dump(
            data, f, default_flow_style=False, allow_unicode=True, sort_keys=False
        )

    print(f"  [+] Saved to {output_file}")
    return output_file


def extract_and_save(conf_abbr: str, year: int, data_dir: str) -> Path | None:
    """Extract rules and save to YAML.

    :param conf_abbr: conference abbreviation (e.g. ``"ICML"``)
    :param year: conference year
    :param data_dir: root data directory
    :return: path to saved file, or ``None`` if extraction failed
    """
    print(f"Extracting rules for {conf_abbr.upper()} {year}...")
    data = extract_rules(conf_abbr, year, data_dir)

    if not data or not data.get("rules"):
        print("  [!] No rules extracted")
        return None

    return save_rules(data, f"{data_dir}/structured")
