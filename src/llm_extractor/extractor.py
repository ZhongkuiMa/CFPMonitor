"""LLM extraction pipeline.

Sends all data sources (raw crawled files, ccfddl, wikicfp) to an Ollama
LLM without preprocessing. Splits into batches only when the combined
data exceeds the model context window. LLM output has highest priority.
"""

import re
from datetime import datetime, timezone
from pathlib import Path

import yaml

from src.extractor.normalizers import normalize_rules

from .client import OllamaClient
from .config import load_config
from .preprocessor import load_raw_texts, load_structured_sources
from .prompt import (
    SYSTEM_PROMPT,
    build_user_prompt,
    format_structured_as_text,
    header_size,
)

_FIELDS_CACHE: dict | None = None


def _load_fields() -> dict:
    """Load field definitions from ``src/extractor/fields.yaml`` (cached)."""
    global _FIELDS_CACHE
    if _FIELDS_CACHE is None:
        path = Path(__file__).parent.parent / "extractor" / "fields.yaml"
        with open(path, encoding="utf-8") as f:
            _FIELDS_CACHE = yaml.safe_load(f)
    return _FIELDS_CACHE


# -- Evidence cleaning -------------------------------------------------------

_EVIDENCE_STRIP_RE = re.compile(r"\*{1,3}|#+\s*|`|~")
_PIPE_RE = re.compile(r"\s*\|\s*")
_WHITESPACE_RE = re.compile(r"\s+")
_MAX_EVIDENCE_LEN = 150


def _clean_evidence(text: str) -> str:
    """Normalize evidence to a single clean line, max 150 chars."""
    if not text:
        return ""
    s = str(text).replace("\n", " ").replace("\r", " ").replace("\xa0", " ")
    s = _EVIDENCE_STRIP_RE.sub("", s)
    s = _PIPE_RE.sub(", ", s).strip(", ")
    s = _WHITESPACE_RE.sub(" ", s).strip()
    if len(s) > _MAX_EVIDENCE_LEN:
        s = s[:_MAX_EVIDENCE_LEN].rsplit(" ", 1)[0] + "..."
    return s


# -- Conflict detection ------------------------------------------------------

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


def _normalize_for_comparison(value: str) -> str:
    """Normalize a value string for conflict comparison."""
    if not value:
        return ""
    s = str(value).lower().strip()
    for abbr, full in _MONTH_ABBRS.items():
        s = re.sub(rf"\b{abbr}\b\.?", full, s)
    s = re.sub(r"[,;:()\"']", "", s)
    return re.sub(r"\s+", " ", s).strip()


def _has_conflict(values: dict[str, str]) -> bool:
    """Return True if source values disagree after normalization."""
    normalized = {
        _normalize_for_comparison(v) for v in values.values() if v and v != "unknown"
    }
    return len(normalized) > 1


# -- Batching ----------------------------------------------------------------


def _build_data_sections(
    raw_texts: dict[str, str],
    structured: dict,
) -> tuple[str, list[str]]:
    """Build structured text and per-file raw sections.

    :param raw_texts: ``{filename: raw_text}`` mapping.
    :param structured: ``{"ccfddl": dict | None, "wikicfp": dict | None}``.
    :returns: ``(structured_text, [raw_file_sections])``.
    """
    structured_parts = []
    for name in ("ccfddl", "wikicfp"):
        data = structured.get(name)
        if data:
            text = format_structured_as_text(name, data)
            if text.strip():
                structured_parts.append(text)
    structured_text = "\n\n".join(structured_parts)

    raw_sections = [
        f"=== {name} ===\n{raw_texts[name]}"
        for name in sorted(raw_texts)
        if raw_texts[name].strip()
    ]
    return structured_text, raw_sections


def _create_batches(
    structured_text: str,
    raw_sections: list[str],
    max_chars: int,
) -> list[str]:
    """Split data into batches that fit the context window.

    If everything fits, returns a single batch. Otherwise raw files are
    distributed across batches with structured data repeated in each.

    :param structured_text: Formatted structured data (repeated per batch).
    :param raw_sections: Per-file raw text sections.
    :param max_chars: Max characters available for data per batch.
    :returns: List of data text strings.
    """
    all_parts = ([structured_text] if structured_text else []) + raw_sections
    combined = "\n\n".join(all_parts)
    if len(combined) <= max_chars:
        return [combined]

    struct_overhead = len(structured_text) + 2 if structured_text else 0
    budget = max_chars - struct_overhead
    if budget <= 0:
        batches = [structured_text] if structured_text else []
        batches.extend(raw_sections)
        return batches

    batches: list[str] = []
    current: list[str] = []
    current_size = 0

    for section in raw_sections:
        size = len(section) + 2
        if current_size + size > budget and current:
            parts = ([structured_text] if structured_text else []) + current
            batches.append("\n\n".join(parts))
            current = []
            current_size = 0
        current.append(section)
        current_size += size

    if current:
        parts = ([structured_text] if structured_text else []) + current
        batches.append("\n\n".join(parts))

    return batches


# -- LLM response parsing ---------------------------------------------------


_BOOL_TRUE = {"true", "yes", "1"}
_BOOL_FALSE = {"false", "no", "0"}


def _normalize_value(value, field_type: str):
    """Normalize an LLM-returned value based on field type.

    - Boolean fields: string "true"/"false" → Python bool, null-like → None.
    - Enum fields: "unknown"/"null" → None, valid strings pass through.
    - Other fields: "unknown"/"null" → None, rest pass through.

    :returns: Normalized value, or None to skip this field.
    """
    if value is None:
        return None

    if field_type == "boolean":
        if isinstance(value, bool):
            return value
        s = str(value).strip().lower()
        if s in _BOOL_TRUE:
            return True
        if s in _BOOL_FALSE:
            return False
        # "not_mentioned", "unknown", etc. → skip
        return None

    if field_type == "enum":
        if isinstance(value, str):
            s = value.strip().lower()
            if s in ("unknown", "null", ""):
                return None
            return value
        return value

    # string, date, list — pass through unless clearly null-like
    if isinstance(value, str) and value.strip().lower() in ("unknown", "null", ""):
        return None
    return value


def _parse_response(response: dict, fields: dict) -> dict[str, dict]:
    """Parse an LLM JSON response into extracted field values.

    Normalizes values based on field type (boolean coercion, null-like
    filtering) and only returns fields with non-null values.

    :param response: Raw JSON dict from LLM.
    :param fields: Field definitions from fields.yaml.
    :returns: ``{field_name: {"value": ..., "evidence": ...}}``.
    """
    extracted = {}
    for name, cfg in fields.items():
        entry = response.get(name)
        if entry is None:
            continue

        if isinstance(entry, dict) and "value" in entry:
            value = entry["value"]
            evidence = entry.get("evidence", "")
        else:
            value = entry
            evidence = ""

        value = _normalize_value(value, cfg.get("type", "string"))
        if value is None:
            continue

        extracted[name] = {
            "value": value,
            "evidence": _clean_evidence(evidence),
        }
    return extracted


# -- Merge -------------------------------------------------------------------


def _merge_extractions(extractions: list[dict], fields: dict) -> dict:
    """Merge extractions from one or more LLM calls into final rules.

    Later extractions override earlier ones (last-write-wins).

    :param extractions: List of partial extraction dicts.
    :param fields: Field definitions from fields.yaml.
    :returns: Complete rules dict with ``_sources`` and ``_conflict``.
    """
    rules = {
        name: {
            "value": cfg.get("default", "unknown"),
            "evidence": "",
            "category": cfg.get("category"),
            "priority": cfg.get("priority"),
        }
        for name, cfg in fields.items()
    }

    seen: dict[str, dict[str, str]] = {name: {} for name in fields}

    for idx, extracted in enumerate(extractions):
        label = "llm" if len(extractions) == 1 else f"llm_batch{idx + 1}"
        for name, data in extracted.items():
            if name not in rules:
                continue
            rules[name]["value"] = data["value"]
            rules[name]["evidence"] = data["evidence"]
            seen[name][label] = str(data["value"])

    for name, sources in seen.items():
        if not sources:
            continue
        rules[name]["_sources"] = {k: {"value": v} for k, v in sources.items()}
        if _has_conflict(sources):
            rules[name]["_conflict"] = True

    return rules


# -- Quality report ----------------------------------------------------------


def _quality_report(rules: dict) -> tuple[dict, dict]:
    """Calculate completeness and quality metrics.

    :param rules: Rules dict with ``_sources`` / ``_conflict``.
    :returns: ``(completeness_dict, quality_dict)``.
    """
    total = len(rules)
    known = sum(
        1 for r in rules.values() if r.get("value") not in ("unknown", None, "", [])
    )

    conflicts = []
    coverage = {"llm": 0}
    for name, rule in rules.items():
        sources = rule.get("_sources", {})
        if sources:
            coverage["llm"] += 1
        if rule.get("_conflict"):
            vals = {s: m["value"] for s, m in sources.items() if "value" in m}
            conflicts.append({"field": name, "values": vals})

    completeness = {
        "known": known,
        "total": total,
        "percentage": round(known / total * 100, 1) if total else 0.0,
    }
    quality = {
        "conflict_count": len(conflicts),
        "conflicts": conflicts,
        "source_coverage": coverage,
    }

    print(f"  [+] Extracted {known}/{total} fields")
    if conflicts:
        print(f"  [!] {len(conflicts)} conflict(s) detected")

    return completeness, quality


# -- Public API --------------------------------------------------------------

_CLIENT: OllamaClient | None = None
_CONFIG: dict | None = None


def _get_client() -> tuple[OllamaClient, dict]:
    """Return a cached (client, config) pair."""
    global _CLIENT, _CONFIG
    if _CLIENT is None:
        _CONFIG = load_config()
        _CLIENT = OllamaClient(_CONFIG)
    return _CLIENT, _CONFIG


def llm_extract_rules(conf_abbr: str, year: int, data_dir: str) -> dict:
    """Extract rules for a conference via LLM.

    Sends all data (raw + structured) without preprocessing. Splits
    into batches only when data exceeds the context window.

    :param conf_abbr: Conference abbreviation (e.g. "ICML").
    :param year: Conference year.
    :param data_dir: Root data directory.
    :returns: Dict with conference, year, completeness, quality, rules.
              Empty dict if no data is available.
    """
    client, config = _get_client()
    num_ctx = config["ollama"].get("options", {}).get("num_ctx", 32768)
    max_data = int(num_ctx * 3.5) - header_size(conf_abbr, year)

    raw_texts = load_raw_texts(conf_abbr, year, data_dir)
    structured = load_structured_sources(conf_abbr, year, data_dir)

    if not raw_texts and not any(structured.values()):
        print("  [!] No data available for extraction")
        return {}

    if raw_texts:
        print(f"  [+] Loaded {len(raw_texts)} raw text files")

    fields = _load_fields()
    structured_text, raw_sections = _build_data_sections(raw_texts, structured)
    total_chars = len(structured_text) + sum(len(s) for s in raw_sections)
    print(f"  [+] Total data: {total_chars} chars (limit: {max_data} chars)")

    batches = _create_batches(structured_text, raw_sections, max_data)
    if len(batches) == 1:
        print("  [+] Sending all data in 1 call...")
    else:
        print(f"  [+] Splitting into {len(batches)} batches")

    extractions = []
    for i, batch in enumerate(batches):
        prompt = build_user_prompt(conf_abbr, year, batch)
        if len(batches) > 1:
            print(f"  [+] Batch {i + 1}/{len(batches)}: {len(prompt)} chars...")
        else:
            print(f"  [+] Sending to LLM ({len(prompt)} chars)...")

        response = client.extract(SYSTEM_PROMPT, prompt)
        if response:
            extracted = _parse_response(response, fields)
            extractions.append(extracted)
            print(f"      -> {len(extracted)} fields extracted")

    if not extractions:
        print("  [!] All LLM calls failed")
        return {}

    rules = _merge_extractions(extractions, fields)
    rules = normalize_rules(rules)
    completeness, quality = _quality_report(rules)

    return {
        "conference": conf_abbr.upper(),
        "year": year,
        "last_checked": datetime.now(timezone.utc).isoformat(),
        "completeness": completeness,
        "quality": quality,
        "rules": rules,
    }


def llm_extract_and_save(conf_abbr: str, year: int, data_dir: str) -> Path | None:
    """Extract rules via LLM and save to YAML.

    :param conf_abbr: Conference abbreviation.
    :param year: Conference year.
    :param data_dir: Root data directory.
    :returns: Path to saved file, or None on failure.
    """
    from src.extractor.extractor import save_rules

    print(f"Extracting rules for {conf_abbr.upper()} {year} (LLM)...")
    data = llm_extract_rules(conf_abbr, year, data_dir)

    if not data or not data.get("rules"):
        print("  [!] No rules extracted")
        return None

    return save_rules(data, f"{data_dir}/structured")
