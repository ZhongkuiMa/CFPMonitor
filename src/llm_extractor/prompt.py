"""Prompt templates for LLM extraction.

Builds system and user prompts with field definitions loaded from
``src/extractor/fields.yaml``.
"""

from pathlib import Path

import yaml

SYSTEM_PROMPT = (
    "You are an expert at extracting conference submission policy information. "
    "You will receive data sources for a conference. "
    "Extract ONLY information about the MAIN CONFERENCE track. "
    "Ignore workshops, tutorials, demos, doctoral consortium, student abstracts, "
    "co-located events, and any child/satellite tracks "
    "(e.g. for AAAI, ignore EAAI/IAAI; for ACL, ignore findings-only or SRW). "
    "EXCEPTION: For fields starting with 'has_', report whether that track/event "
    "is mentioned anywhere in the data (true/false). "
    "Use your own judgement to determine the correct value when sources conflict. "
    "For fields not mentioned in ANY source, use null. "
    "Return valid JSON only, no markdown or explanation."
)

_FIELDS_CACHE: dict | None = None

_TYPE_HINTS = {
    "date": 'string (e.g. "August 18, 2025")',
    "boolean": "true/false",
    "string": "string",
    "enum": "string (one of the allowed values)",
    "list": "list of strings",
}


def _load_fields() -> dict:
    """Load field definitions from ``src/extractor/fields.yaml`` (cached)."""
    global _FIELDS_CACHE
    if _FIELDS_CACHE is None:
        path = Path(__file__).parent.parent / "extractor" / "fields.yaml"
        with open(path, encoding="utf-8") as f:
            _FIELDS_CACHE = yaml.safe_load(f)
    return _FIELDS_CACHE


def _build_header(conf_abbr: str, year: int) -> str:
    """Build the instruction portion of the user prompt."""
    fields = _load_fields()
    field_lines = "\n".join(
        f'  - "{name}" ({_TYPE_HINTS.get(cfg["type"], "string")}): '
        f"{cfg.get('description', '')}"
        for name, cfg in fields.items()
    )

    return (
        f"Conference: {conf_abbr.upper()} {year}\n\n"
        f"Extract the following fields from ALL provided data sources.\n"
        f"For each field, return a JSON object with:\n"
        f'  "field_name": {{"value": <extracted value or null>, '
        f'"evidence": "<short quote>"}}\n\n'
        f"Fields to extract:\n{field_lines}\n\n"
        f"CRITICAL -- Scope:\n"
        f"- Extract ONLY for the MAIN CONFERENCE track of "
        f"{conf_abbr.upper()} {year}\n"
        f"- IGNORE workshops, tutorials, demos, doctoral consortium, "
        f"co-located events, and child tracks\n"
        f"- If the data mixes main track and other tracks, "
        f"use only the main track information\n"
        f"- EXCEPTION: 'has_*' fields detect whether a track/event "
        f"EXISTS anywhere in the data (true/false)\n\n"
        f"CRITICAL -- Output format (you MUST follow these exactly):\n"
        f'- Date fields MUST use "Month Day, Year" '
        f'(e.g. "January 30, 2025"). '
        f"No ISO format, timestamps, or abbreviations\n"
        f'- Date ranges: "Month Day-Day, Year" '
        f'(e.g. "July 13-19, 2025")\n'
        f"- Boolean fields: JSON true/false (not strings). "
        f"null if not stated\n"
        f"- page_limit: include number and qualifier "
        f'(e.g. "8 pages")\n'
        f"- artifact_evaluation: mandatory/optional/none\n"
        f"- llm_policy: allowed/required_disclosure/forbidden\n"
        f"- conference_format: in-person/virtual/hybrid\n"
        f"- submission_system: "
        f"OpenReview/EasyChair/CMT/SoftConf/HotCRP\n"
        f"- Evidence MUST be a single short sentence "
        f"(max 20 words, one line, no newlines)\n"
        f"- If not mentioned in ANY source, "
        f'set value to null and evidence to ""\n\n'
    )


def header_size(conf_abbr: str, year: int) -> int:
    """Return the character count of system prompt + user prompt header.

    Used to calculate remaining room for data in the context window.
    """
    return len(SYSTEM_PROMPT) + len(_build_header(conf_abbr, year))


def build_user_prompt(conf_abbr: str, year: int, data_text: str) -> str:
    """Build the complete user prompt with data appended.

    :param conf_abbr: Conference abbreviation.
    :param year: Conference year.
    :param data_text: Combined raw + structured data text.
    :returns: Formatted user prompt string.
    """
    return (
        f"{_build_header(conf_abbr, year)}--- DATA ---\n{data_text}\n--- END DATA ---"
    )


def format_structured_as_text(name: str, data: dict) -> str:
    """Format a ccfddl or wikicfp dict as readable text for the LLM.

    :param name: Source name ("ccfddl" or "wikicfp").
    :param data: Parsed YAML data dict.
    :returns: Formatted text block, or empty string if no data.
    """
    if not data:
        return ""

    lines = [f"=== {name} ==="]

    for key in (
        "title",
        "description",
        "date",
        "dates",
        "place",
        "location",
        "submission_deadline",
        "notification",
        "camera_ready",
        "link",
    ):
        val = data.get(key)
        if val and str(val).strip() and str(val) != "[Empty]":
            lines.append(f"  {key}: {val}")

    rank = data.get("rank")
    if isinstance(rank, dict):
        parts = [f"{k}={v}" for k, v in rank.items() if v]
        if parts:
            lines.append(f"  rank: {', '.join(parts)}")

    timeline = data.get("timeline")
    if isinstance(timeline, list):
        for entry in timeline:
            for key in ("deadline", "abstract_deadline", "comment"):
                val = entry.get(key, "")
                if val:
                    lines.append(f"  {key}: {val}")

    cfp_text = str(data.get("cfp_text", "")).strip()
    if cfp_text and cfp_text != "[Empty]":
        lines.append(f"  cfp_text:\n{cfp_text}")

    return "\n".join(lines)
