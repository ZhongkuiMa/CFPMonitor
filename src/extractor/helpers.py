"""Helper functions for CFP rule extraction.

This module provides the public API for field value extraction using a
type-driven architecture. Internal implementation details are kept private.

Public API:
    - extract_field_value: Main entry point for extracting field values
    - extract_context: Extract evidence context from matched text
"""

import re
from datetime import datetime
from typing import Any

# ============================================
# MODULE-LEVEL CONSTANTS (Performance optimization)
# ============================================

# Month abbreviation mapping
_MONTH_ABBRS = {
    "Jan": "January",
    "Feb": "February",
    "Mar": "March",
    "Apr": "April",
    "May": "May",
    "Jun": "June",
    "Jul": "July",
    "Aug": "August",
    "Sep": "September",
    "Sept": "September",
    "Oct": "October",
    "Nov": "November",
    "Dec": "December",
}

# Pre-compiled pattern for month normalization (single pass vs 12 sequential re.sub calls)
_MONTH_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(k) for k in _MONTH_ABBRS.keys()) + r")\b",
    re.IGNORECASE,
)

# Pre-compiled patterns for date cleaning (consolidates multiple regex operations)
_DATE_CLEANUP_PATTERN = re.compile(
    r"(?:Sun|Mon|Tue|Wed|Thu|Fri|Sat)\.?\s+|"  # Day of week
    r"\b(\d+)(st|nd|rd|th)\b|"  # Ordinal suffixes (capture groups 1-2)
    r"\bthe\s+(?=\d)",  # "the" before numbers
    re.IGNORECASE,
)

_DATE_PREFIX_PATTERN = re.compile(
    r"^(?:author response period|response period|rebuttal period|submission period|review period)\s+",
    re.IGNORECASE,
)

# ============================================
# PUBLIC API
# ============================================


def extract_field_value(
    matches: list[dict], text: str, field_config: dict, pattern_config: dict, year: int
) -> Any:
    """Extract value from matches using type handler.

    Main entry point for field value extraction. Uses type-driven architecture
    where each type has a dedicated handler that consolidates extraction,
    cleaning, and validation logic.

    :param matches: List of pattern matches
    :param text: Full text content
    :param field_config: Field schema (type, priority, default, type_config)
    :param pattern_config: Pattern config (patterns, keywords, extractor, cleaner)
    :param year: Conference year for date normalization
    :return: Extracted and cleaned value appropriate for field type
    """
    # Handle special extractors (e.g., page_number with range support)
    extractor_name = pattern_config.get("extractor")
    if extractor_name and matches:
        extractor = _SPECIAL_EXTRACTORS.get(extractor_name)
        if extractor:
            return extractor(matches[0]["matched_text"])

    # Use type handler for standard extraction + cleaning
    field_type = field_config["type"]
    handler = _get_type_handler(field_type)
    value = handler(matches, text, field_config, pattern_config)

    # Validate string fields that have quality issues
    # Currently only validating conference_location
    if field_type == "string" and isinstance(value, str) and value != "unknown":
        # Get field name from description (workaround for lack of field_name param)
        description = field_config.get("description", "").lower()
        if "conference" in description and "location" in description:
            if not _validate_location_value(value):
                value = "unknown"

    # Normalize date values: standardize format, add year if missing, validate year
    if field_type == "date" and value not in ["unknown", None, ""]:
        if isinstance(value, str):
            # Normalize format (handles various formats and adds year if missing)
            value = _normalize_date_format(value, conference_year=year)

            # Validate year - reject dates more than 2 years in the past
            # (likely stale/cached data)
            if value != "unknown":
                year_match = re.search(r"\b(20\d{2})\b", value)
                if year_match:
                    extracted_year = int(year_match.group(1))
                    current_year = datetime.now().year
                    # Reject if extracted year is >2 years old
                    if extracted_year < current_year - 2:
                        value = "unknown"

    return value


def extract_context(text: str, start: int, end: int, max_length: int = 150) -> str:
    """Extract sentence or word window containing the match (optimized).

    Tries to extract the sentence containing the match. If the sentence is
    too long (e.g., in tables or long paragraphs), falls back to extracting
    3 words before + match + 3 words after.

    :param text: Full text content
    :param start: Match start position
    :param end: Match end position
    :param max_length: Max sentence length before falling back to word window
    :return: Context string with "..." prefix and suffix
    """
    sent_chars = ".!?\n"
    search_window = 200  # Limit search window for performance

    # Search backward for sentence start (limited window)
    search_start = max(0, start - search_window)
    sent_start = start
    for i in range(start - 1, search_start - 1, -1):
        if text[i] in sent_chars:
            sent_start = i + 1
            # Skip leading whitespace
            while sent_start < start and text[sent_start].isspace():
                sent_start += 1
            break

    # Search forward for sentence end (limited window)
    search_end = min(len(text), end + search_window)
    sent_end = end
    for i in range(end, search_end):
        if text[i] in sent_chars:
            sent_end = i + 1
            break

    sentence = text[sent_start:sent_end].strip()

    # Only normalize whitespace if double spaces exist (quick check)
    if "  " in sentence:
        sentence = re.sub(r"\s+", " ", sentence)

    # If sentence is reasonable length, return it
    if len(sentence) <= max_length:
        return f"...{sentence}..."

    # Fallback: extract 3 words before + match + 3 words after
    matched_text = text[start:end]

    # Limit slicing to search windows instead of full text
    before_window = max(0, start - search_window)
    after_window = min(len(text), end + search_window)

    words_before = re.findall(r"\S+", text[before_window:start])
    before_context = (
        " ".join(words_before[-3:])
        if len(words_before) >= 3
        else text[before_window:start].strip()
    )

    words_after = re.findall(r"\S+", text[end:after_window])
    after_context = (
        " ".join(words_after[:3])
        if len(words_after) >= 3
        else text[end:after_window].strip()
    )

    context = f"{before_context} {matched_text} {after_context}".strip()
    return f"...{context}..."


# ============================================
# PRIVATE: Type Handlers
# ============================================


def _handle_boolean_type(
    matches: list[dict], full_text: str, field_config: dict, pattern_config: dict
) -> bool | str:
    """Extract and validate boolean value.

    Strategy:
    1. Use pattern name to determine True/False (primary signal)
    2. Use keywords as quick sanity check only (secondary validation)
    3. Check for negation in context as fallback
    """
    if not matches:
        return field_config.get("default", "unknown")

    match = matches[0]
    matched_text = match["matched_text"]
    pattern_name = match.get("pattern_name", "")

    # Step 1: Determine value based on pattern name (primary signal)
    # Negative patterns (indicate False/prohibition)
    negative_pattern_indicators = [
        "not_allowed",
        "not_permitted",
        "prohibited",
        "forbidden",
        "not_double_blind",
        "single_blind",
        "not_required",
        "may_not",
        "cannot",
        "no_",
        "without",
    ]

    # Check if pattern name indicates a negative/prohibition
    pattern_lower = pattern_name.lower()
    for indicator in negative_pattern_indicators:
        if indicator in pattern_lower:
            return False

    # Step 2: Quick keyword sanity check (optional validation)
    positive_kw = pattern_config.get("positive_keywords", [])
    negative_kw = pattern_config.get("negative_keywords", [])

    # If negative keywords present in matched text, likely False
    if negative_kw:
        for neg_kw in negative_kw:
            if neg_kw.lower() in matched_text.lower():
                return False

    # Step 3: Check for negation in surrounding context
    if positive_kw:
        type_config = field_config.get("type_config", {})
        negation_window = type_config.get("negation_window", 50)

        for pos_kw in positive_kw:
            if pos_kw.lower() in matched_text.lower():
                if _detect_negation(full_text, pos_kw, window_size=negation_window):
                    return False
                # Found positive keyword without negation - likely True
                return True

    # Step 4: Evidence validation - check if boolean value makes sense
    # If the matched text contains the field's positive keywords WITHOUT negation words,
    # it should be True. If it contains negation words, it should be False.
    evidence_lower = matched_text.lower()

    # Check for explicit affirmative statements
    affirmative_indicators = [
        r"\bis\s+",  # "is double-blind"
        r"\bare\s+",  # "are single-blind"
        r"\bwill\s+be\s+",  # "will be required"
        r"\bmust\s+be\s+",  # "must be submitted"
        r"\bsubject\s+to\s+",  # "subject to double-blind review"
        r"\buse\s+",  # "use double-blind"
        r"\bemploy\s+",  # "employ single-blind"
    ]

    # If evidence has affirmative language, strongly prefer True
    for indicator in affirmative_indicators:
        if re.search(indicator, evidence_lower):
            # But still check for negation
            common_negations = ["not", "no ", "without", "never"]
            has_negation = any(neg in evidence_lower for neg in common_negations)
            if not has_negation:
                return True

    # Step 5: Default - if pattern matched and no negative signals, assume True
    # (the pattern itself matched something relevant, so it's likely affirmative)
    return True


def _handle_enum_type(
    matches: list[dict], full_text: str, field_config: dict, pattern_config: dict
) -> str:
    """Extract and validate enum value."""
    if not matches:
        return field_config.get("default", "unknown")

    matched_text = matches[0]["matched_text"]
    allowed_values = pattern_config.get("allowed_values", [])

    # Apply specialized cleaner if specified (e.g., for artifact_evaluation, llm_policy)
    cleaner_name = pattern_config.get("cleaner")
    if cleaner_name:
        cleaner = _SPECIALIZED_CLEANERS.get(cleaner_name)
        if cleaner:
            cleaned_value = cleaner(matched_text)
            # If cleaner returns a valid enum value, use it
            if cleaned_value in allowed_values:
                return cleaned_value
            # Otherwise continue with standard logic below
            matched_text = cleaned_value

    matched_lower = matched_text.lower()

    # Try to match against allowed values first
    for allowed_val in allowed_values:
        if allowed_val.lower() in matched_lower:
            return allowed_val

    # Fallback to common enum patterns
    if "required" in matched_lower or "mandatory" in matched_lower:
        return "required"
    elif "optional" in matched_lower or "encouraged" in matched_lower:
        return "optional"

    return "unknown"


def _normalize_season_to_date(value: str) -> str:
    """Convert season mentions to approximate month ranges."""
    season_map = {
        "spring": "March-May",
        "summer": "June-August",
        "fall": "September-November",
        "autumn": "September-November",
        "winter": "December-February",
    }

    value_lower = value.lower()
    for season, months in season_map.items():
        if season in value_lower:
            # Extract year if present
            year_match = re.search(r"\d{4}", value)
            if year_match:
                return f"{months} {year_match.group()}"
            return f"{months}"

    return value


def _is_valid_date_range(value: str) -> bool:
    """Validate that a date range looks legitimate (for conference_dates)."""
    if not value or value == "unknown":
        return False

    value_lower = value.lower()

    # Must contain month names or numbers
    months = [
        "january",
        "february",
        "march",
        "april",
        "may",
        "june",
        "july",
        "august",
        "september",
        "october",
        "november",
        "december",
    ]

    has_month = any(month[:3] in value_lower for month in months)
    has_year = bool(re.search(r"\d{4}", value))

    if not (has_month or has_year):
        return False

    # Reject garbage patterns
    garbage_indicators = [
        "at short notice",
        "available at",
        "devoted to",
        "subject to",
        "open to",
    ]

    for indicator in garbage_indicators:
        if indicator in value_lower:
            return False

    # Length checks
    if len(value) < 6 or len(value) > 100:
        return False

    return True


def _normalize_date_range(date_text: str) -> str:
    """Normalize date range to canonical format.

    Handles variations like:
    - "January 20 – January 27, 2026" (em-dash, full month repeated)
    - "January 20 - 27, 2026" (hyphen, abbreviated)
    - "Jan 20, 2026 - Jan 27, 2026" (month abbreviation, repeated)
    - "July 13 through July 19, 2025" (through instead of dash)

    Returns normalized format: "Month DD - DD, YYYY" or "Month DD - Month DD, YYYY"
    """
    # First normalize all separators to hyphen surrounded by spaces
    # Handle em-dash (–), en-dash (−), hyphen (-), "to", "through"
    normalized = re.sub(r"\s*[–−]\s*|\s+to\s+|\s+through\s+", " - ", date_text)

    # Pattern to match date ranges
    # Format: Month DD - Month DD, YYYY or Month DD - DD, YYYY
    range_pattern = (
        r"([A-Z][a-z]+)\s+(\d{1,2})\s*-\s*(?:([A-Z][a-z]+)\s+)?(\d{1,2}),?\s+(\d{4})"
    )
    match = re.search(range_pattern, normalized)

    if not match:
        # Not a date range, return as is
        return date_text

    month1 = match.group(1)
    day1 = match.group(2)
    month2 = match.group(3)  # May be None for abbreviated form
    day2 = match.group(4)
    year = match.group(5)

    # If second month is missing, use first month
    if not month2:
        month2 = month1

    # Normalize format
    if month1 == month2:
        # Same month: "Month DD - DD, YYYY"
        return f"{month1} {day1} - {day2}, {year}"
    else:
        # Different months: "Month DD - Month DD, YYYY"
        return f"{month1} {day1} - {month2} {day2}, {year}"


def _handle_date_type(
    matches: list[dict], full_text: str, field_config: dict, pattern_config: dict
) -> str:
    """Extract and clean date value with TBD support and validation."""
    if not matches:
        return field_config.get("default", "unknown")

    matched_text = matches[0]["matched_text"].strip()

    # Handle TBD/TBA cases early
    tbd_indicators = ["tbd", "tba", "to be announced", "coming soon"]
    if any(ind in matched_text.lower() for ind in tbd_indicators):
        return "TBD"

    # Apply specialized cleaner if specified (e.g., for deadline/notification dates)
    cleaner_name = pattern_config.get("cleaner")
    if cleaner_name:
        cleaner = _SPECIALIZED_CLEANERS.get(cleaner_name)
        if cleaner:
            matched_text = cleaner(matched_text)

    # Strip everything before the last colon (removes field labels)
    # E.g., "Submission Deadline: Jan 30, 2025" -> "Jan 30, 2025"
    if ":" in matched_text:
        matched_text = matched_text.split(":")[-1].strip()

    # Remove common date prefixes (consolidated single pass)
    matched_text = _DATE_PREFIX_PATTERN.sub("", matched_text)

    # Combined cleanup: weekdays, ordinals, "the" (single pass optimization)
    def _cleanup_replacer(m):
        # If we matched ordinal suffix (group 1 exists), keep just the number
        if m.group(1):
            return m.group(1)
        # Otherwise, remove the match entirely (weekday or "the")
        return ""

    matched_text = _DATE_CLEANUP_PATTERN.sub(_cleanup_replacer, matched_text)

    # Normalize abbreviated month names to full names (single-pass optimization)
    matched_text = _MONTH_PATTERN.sub(
        lambda m: _MONTH_ABBRS[m.group(1).title()], matched_text
    )

    # Clean whitespace
    matched_text = re.sub(r"\s+", " ", matched_text).strip()

    # For conference_dates specifically, normalize format and validate
    field_name = field_config.get(
        "description", ""
    )  # Use description as proxy for field name
    if "conference" in field_name.lower() and "date" in field_name.lower():
        # Normalize date range format (handles em-dash, abbreviated ranges, etc.)
        matched_text = _normalize_date_range(matched_text)

        if not _is_valid_date_range(matched_text):
            return "unknown"

    # Handle season dates - convert to month ranges
    if any(
        season in matched_text.lower()
        for season in ["spring", "summer", "fall", "winter", "autumn"]
    ):
        matched_text = _normalize_season_to_date(matched_text)

    return matched_text


def _handle_number_type(
    matches: list[dict], full_text: str, field_config: dict, pattern_config: dict
) -> int | str:
    """Extract and validate number value."""
    if not matches:
        return field_config.get("default", "unknown")

    matched_text = matches[0]["matched_text"]
    numbers = re.findall(r"\d+", matched_text)

    if not numbers:
        return "unknown"

    value = int(numbers[0])

    # Optional range validation
    type_config = field_config.get("type_config", {})
    min_value = type_config.get("min_value")
    max_value = type_config.get("max_value")

    if min_value is not None and value < min_value:
        return "unknown"
    if max_value is not None and value > max_value:
        return "unknown"

    return value


def _validate_location_value(value: str) -> bool:
    """Validate if a location string looks legitimate.

    Rejects:
    - Single words or too many words
    - Text fragments without proper capitalization
    - Date-like patterns (months, days, times)
    - Academic/organizational patterns
    - Common garbage patterns
    - Text that's too short or too long
    """
    if not value or value == "unknown":
        return False

    # Must have reasonable length (at least 5 chars, at most 100)
    if len(value) < 5 or len(value) > 100:
        return False

    # Must contain at least one comma (city, country or city, state)
    if "," not in value:
        return False

    value_lower = value.lower()

    # Reject if starts with day of week (Tuesday, January)
    days_of_week = [
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
        "sunday",
    ]
    first_word = value_lower.split(",")[0].strip()
    if first_word in days_of_week:
        return False

    # Reject if starts with month name (January, 2026)
    months = [
        "january",
        "february",
        "march",
        "april",
        "may",
        "june",
        "july",
        "august",
        "september",
        "october",
        "november",
        "december",
    ]
    if first_word in months:
        return False

    # Reject strong date-like patterns (only full month names, not abbreviations)
    # This filters out extracted date ranges like "October 13 - October 20, 2025"
    month_pattern = r"\b(?:january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{1,2}\s*(?:-|to|through)\b"
    if re.search(month_pattern, value_lower):
        return False

    # Reject obvious garbage patterns
    garbage_patterns = [
        "of the ",  # "of the case"
        "such ",  # "such submissions"
        " you",  # "However, you"
        "research",  # "research results"
        "job fair",  # "the Job Fair"
        "attend ",  # "attend SIGGRAPH"
        "paper",  # various paper-related text
        "submission",  # submission-related text
        "abstract",  # abstract-related
        "however",  # transition words
        "thus",  # "Thus, in"
        "question",  # "time for questions"
    ]

    for pattern in garbage_patterns:
        if pattern in value_lower:
            return False

    # Check word count - should be 2-5 words max for location
    words = value.split()
    if len(words) < 2 or len(words) > 5:
        return False

    # Must start with capitalized word (city name)
    if not value[0].isupper():
        return False

    return True


def _handle_string_type(
    matches: list[dict], full_text: str, field_config: dict, pattern_config: dict
) -> str:
    """Extract and clean string value."""
    if not matches:
        return field_config.get("default", "unknown")

    value = matches[0]["matched_text"].strip()
    value = re.sub(r"\s+", " ", value)

    # Apply specialized cleaner if specified
    cleaner_name = pattern_config.get("cleaner")
    if cleaner_name:
        cleaner = _SPECIALIZED_CLEANERS.get(cleaner_name)
        if cleaner:
            return cleaner(value)

    # Special handling for conference_location field
    # Strip common location labels that might appear at the beginning
    if ":" in value:
        # Check if it starts with a location label
        prefix = value.split(":")[0].lower()
        if any(label in prefix for label in ["location", "venue", "place", "city"]):
            value = value.split(":", 1)[-1].strip()

    # Remove common prefixes for locations
    location_prefixes = [
        r"^will\s+be\s+held\s+(?:in|at)\s+",
        r"^held\s+(?:in|at)\s+",
        r"^takes?\s+place\s+in\s+",
        r"^to\s+be\s+held\s+(?:in|at)\s+",
    ]
    for prefix_pattern in location_prefixes:
        value = re.sub(prefix_pattern, "", value, flags=re.IGNORECASE)

    # Remove common prefix words that got included by greedy patterns
    # E.g., "Place San Diego, CA" -> "San Diego, CA"
    prefix_words = ["Place", "Location", "Venue", "City", "At", "In"]
    for prefix in prefix_words:
        if value.startswith(prefix + " "):
            value = value[len(prefix) + 1 :].strip()

    # Remove common trailing text patterns for locations
    # E.g., "Rotterdam, the Netherlands from" -> "Rotterdam, the Netherlands"
    value = re.sub(r"\s+(?:from|on|during|at)\s*$", "", value, flags=re.IGNORECASE)

    # Remove trailing articles and common suffixes
    # E.g., "Hong Kong, China The" -> "Hong Kong, China"
    # E.g., "Tangier, Morocco AISTATS" -> "Tangier, Morocco"
    trailing_words = ["The", "A", "An", "And", "Or", "For", "In", "At", "On"]
    for suffix in trailing_words:
        if value.endswith(" " + suffix):
            value = value[: -len(suffix) - 1].strip()

    # Remove trailing conference acronyms (all caps, 3-10 letters)
    # E.g., "Tangier, Morocco AISTATS" -> "Tangier, Morocco"
    value = re.sub(r"\s+[A-Z]{3,10}$", "", value)

    # Remove trailing punctuation
    value = value.rstrip(",;.")

    return value


def _handle_list_type(
    matches: list[dict], full_text: str, field_config: dict, pattern_config: dict
) -> list[str]:
    """Extract list of values from matches."""
    if not matches:
        default = field_config.get("default", "unknown")
        return default if default == "unknown" else [default]

    # Get configurable limit (default to 5)
    type_config = field_config.get("type_config", {})
    max_items = type_config.get("max_items", 5)

    return [m["matched_text"].strip() for m in matches[:max_items]]


# Type handler registry
_TYPE_HANDLERS = {
    "boolean": _handle_boolean_type,
    "enum": _handle_enum_type,
    "date": _handle_date_type,
    "number": _handle_number_type,
    "string": _handle_string_type,
    "list": _handle_list_type,
}


def _get_type_handler(field_type: str):
    """Get type handler function for a field type."""
    return _TYPE_HANDLERS.get(field_type, _handle_string_type)


# ============================================
# PRIVATE: Special Extractors
# ============================================


def _extract_page_number(matched_text: str) -> str:
    """Extract page number from matched text.

    Handles formats: "8 pages", "between 8 and 12 pages", "8-12 pages", "eight pages"
    """
    range_patterns = [
        r"between\s+(\d+)\s+and\s+(\d+)",
        r"(\d+)\s*-\s*(\d+)",
        r"(\d+)\s+to\s+(\d+)",
    ]

    for range_pattern in range_patterns:
        range_match = re.search(range_pattern, matched_text, re.IGNORECASE)
        if range_match:
            return f"{range_match.group(1)}-{range_match.group(2)} pages"

    # Word to number conversion
    word_to_num = {
        "one": "1",
        "two": "2",
        "three": "3",
        "four": "4",
        "five": "5",
        "six": "6",
        "seven": "7",
        "eight": "8",
        "nine": "9",
        "ten": "10",
        "eleven": "11",
        "twelve": "12",
    }

    numbers = re.findall(r"\d+", matched_text)
    if numbers:
        return f"{numbers[0]} pages"

    matched_lower = matched_text.lower()
    for word, num in word_to_num.items():
        if word in matched_lower:
            return f"{num} pages"

    return "unknown"


# Special extractors registry
_SPECIAL_EXTRACTORS = {
    "extract_page_number": _extract_page_number,
}


# ============================================
# PRIVATE: Specialized Cleaners
# ============================================


def _clean_file_size(value: str) -> str:
    """Normalize file size to standard format (e.g., "10MB")."""
    if not value or value == "unknown":
        return value

    match = re.search(r"(\d+)\s*(MB|mb|megabytes?|Mb)", value, re.IGNORECASE)
    if match:
        return f"{match.group(1)}MB"

    return value


def _clean_page_count(value: str) -> str:
    """Normalize page count to standard format (e.g., "8 pages")."""
    if not value or value == "unknown":
        return value

    word_to_num = {
        "one": "1",
        "two": "2",
        "three": "3",
        "four": "4",
        "five": "5",
        "six": "6",
        "seven": "7",
        "eight": "8",
        "nine": "9",
        "ten": "10",
        "eleven": "11",
        "twelve": "12",
    }

    value_lower = value.lower()
    for word, num in word_to_num.items():
        if word in value_lower:
            value = re.sub(rf"\b{word}\b", num, value, flags=re.IGNORECASE)

    value = re.sub(r"\bpage\b", "pages", value, flags=re.IGNORECASE)
    value = re.sub(r"(\d+)([- ])?pages", r"\1 pages", value, flags=re.IGNORECASE)

    return value.strip()


def _clean_system_name(value: str) -> str:
    """Normalize submission system names (e.g., "OpenReview", "EasyChair")."""
    if not value or value == "unknown":
        return value

    system_names = {
        "openreview": "OpenReview",
        "easychair": "EasyChair",
        "cmt": "CMT",
        "softconf": "SoftConf",
        "hotcrp": "HotCRP",
    }

    value_lower = value.lower().strip()
    return system_names.get(value_lower, value)


def _clean_publication_venue(value: str) -> str:
    """Normalize publication venue names to standard forms."""
    if not value or value == "unknown":
        return value

    # Remove common prefixes
    value = re.sub(
        r"^(?:published?\s+(?:in|by|through|via)\s+(?:the\s+)?)",
        "",
        value,
        flags=re.IGNORECASE,
    )
    value = value.strip()

    # Normalize to standard venue names
    venue_mappings = {
        # Machine Learning
        r"(?:proceedings\s+of\s+)?machine\s+learning\s+research": "PMLR",
        r"pmlr": "PMLR",
        # ACM
        r"acm\s+digital\s+library": "ACM Digital Library",
        r"acm\s+dl": "ACM Digital Library",
        # IEEE
        r"ieee\s+xplore": "IEEE Xplore",
        r"ieee": "IEEE",
        # Springer
        r"springer": "Springer",
        r"lecture\s+notes\s+in\s+computer\s+science": "LNCS",
        r"lncs": "LNCS",
        # Journals
        r"journal\s+of\s+machine\s+learning\s+research": "JMLR",
        r"jmlr": "JMLR",
    }

    value_lower = value.lower()
    for pattern, normalized in venue_mappings.items():
        if re.search(pattern, value_lower):
            return normalized

    # Capitalize properly if not matched
    return value.strip()


def _clean_deadline_date(value: str) -> str:
    """Remove label text from deadline dates.

    Examples:
        "Submission Deadline February 14, 2025" → "February 14, 2025"
        "paper submission August 7, 2024" → "August 7, 2024"
    """
    if not value or value == "unknown":
        return value

    # Remove common deadline label prefixes
    label_patterns = [
        r"^(?:paper\s+)?submission\s+(?:deadline\s+)?",
        r"^(?:papers?\s+)?due\s+",
        r"^deadline\s+",
        r"^manuscripts?\s+(?:due\s+)?",
        r"^submit\s+(?:by\s+)?",
    ]

    for pattern in label_patterns:
        value = re.sub(pattern, "", value, flags=re.IGNORECASE)

    # Remove "is/was/at" connectors
    value = re.sub(r"^(?:is|was|at)\s+", "", value, flags=re.IGNORECASE)

    # Normalize date format
    return _normalize_date_format(value.strip())


def _clean_notification_date(value: str) -> str:
    """Remove label text from notification dates.

    Examples:
        "notification October 13, 2025" → "October 13, 2025"
        "Notification January 16, 2025" → "January 16, 2025"
    """
    if not value or value == "unknown":
        return value

    # Remove common notification label prefixes
    label_patterns = [
        r"^(?:acceptance\s+)?notification\s+(?:date\s+)?",
        r"^(?:acceptance\s+)?decisions?\s+(?:announced|sent|released)\s+",
        r"^authors?\s+(?:will\s+be\s+)?notified\s+(?:by|in)\s+",
    ]

    for pattern in label_patterns:
        value = re.sub(pattern, "", value, flags=re.IGNORECASE)

    value = re.sub(r"^(?:is|was|on)\s+", "", value, flags=re.IGNORECASE)

    # Normalize date format
    return _normalize_date_format(value.strip())


def _normalize_date_format(value: str, conference_year: int = None) -> str:
    """Normalize various date formats to consistent format: Month DD, YYYY.

    Handles:
        - "February 14, 2025" → "February 14, 2025"
        - "Feb 14, 2025" → "February 14, 2025"
        - "14 Feb 2025" → "February 14, 2025"
        - "2025-02-14" → "February 14, 2025"
        - "02/14/2025" → "February 14, 2025"
        - "February 14" (no year) → "February 14, {conference_year}"
        - Strips timezone info (PST, UTC, etc.)

    Args:
        value: Date string to normalize
        conference_year: Year of the conference (for adding missing years)

    Returns:
        Normalized date string in "Month DD, YYYY" format, or "unknown" if invalid
    """
    if not value or value == "unknown":
        return "unknown"

    value = value.strip()

    # Remove timezone indicators (PST, UTC, AOE, etc.)
    value = re.sub(
        r"\s+(?:PST|UTC|EST|CST|MST|PDT|EDT|CDT|MDT|AOE|GMT)$",
        "",
        value,
        flags=re.IGNORECASE,
    )

    # Try format: YYYY-MM-DD or YYYY/MM/DD
    match = re.match(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", value)
    if match:
        year, month, day = match.groups()
        month_name = _get_month_name(int(month))
        if month_name:
            return f"{month_name} {int(day)}, {year}"

    # Try format: MM/DD/YYYY or MM-DD-YYYY
    match = re.match(r"(\d{1,2})[-/](\d{1,2})[-/](\d{4})", value)
    if match:
        month, day, year = match.groups()
        month_name = _get_month_name(int(month))
        if month_name:
            return f"{month_name} {int(day)}, {year}"

    # Try format: DD Month YYYY or DD Month, YYYY
    match = re.match(r"(\d{1,2})\s+([A-Za-z]+),?\s+(\d{4})", value)
    if match:
        day, month_str, year = match.groups()
        month_name = _expand_month_abbr(month_str)
        return f"{month_name} {int(day)}, {year}"

    # Try format: Month DD, YYYY (already correct, just expand abbreviation)
    match = re.match(r"([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})", value)
    if match:
        month_str, day, year = match.groups()
        month_name = _expand_month_abbr(month_str)
        return f"{month_name} {int(day)}, {year}"

    # Try format: Month DD (no year)
    match = re.match(r"([A-Za-z]+)\s+(\d{1,2})(?:,\s*)?$", value)
    if match and conference_year:
        month_str, day = match.groups()
        month_name = _expand_month_abbr(month_str)
        return f"{month_name} {int(day)}, {conference_year}"

    # Try format: DD Month (no year)
    match = re.match(r"(\d{1,2})\s+([A-Za-z]+)(?:,\s*)?$", value)
    if match and conference_year:
        day, month_str = match.groups()
        month_name = _expand_month_abbr(month_str)
        return f"{month_name} {int(day)}, {conference_year}"

    # Could not parse - return original value
    return value


def _get_month_name(month_num: int) -> str:
    """Convert month number (1-12) to month name."""
    months = [
        "",
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December",
    ]
    if 1 <= month_num <= 12:
        return months[month_num]
    return ""


def _expand_month_abbr(month_str: str) -> str:
    """Expand month abbreviation to full month name.

    Examples:
        "Feb" → "February"
        "February" → "February"
        "feb" → "February"
    """
    # Try exact match in dictionary (case-insensitive)
    for abbr, full_name in _MONTH_ABBRS.items():
        if month_str.lower() == abbr.lower():
            return full_name
        if month_str.lower() == full_name.lower():
            return full_name

    # No match - return original (might already be full name)
    return month_str.capitalize()


def _clean_artifact_evaluation(value: str) -> str:
    """Map artifact evaluation text to enum values (required/optional/unknown).

    Examples:
        "code submission is required" → "required"
        "artifacts are optional" → "optional"
        "artifact evaluation badge" → "optional"
        "artifact submission" → "optional"
    """
    if not value or value == "unknown":
        return "unknown"

    value_lower = value.lower()

    # Check for required/mandatory indicators
    required_keywords = ["required", "mandatory", "must submit", "must provide"]
    for keyword in required_keywords:
        if keyword in value_lower:
            return "required"

    # Check for optional/encouraged indicators or any artifact mention
    optional_keywords = [
        "optional",
        "encouraged",
        "artifact",
        "code submission",
        "reproducibility",
        "badge",
        "code availability",
    ]
    for keyword in optional_keywords:
        if keyword in value_lower:
            return "optional"

    # If artifact-related text found but unclear, default to optional
    return "optional"


def _clean_llm_policy(value: str) -> str:
    """Map LLM policy text to standardized values (allowed/discouraged/prohibited/must_disclose/unknown).

    Examples:
        "LLM usage must be disclosed" → "must_disclose"
        "ChatGPT is allowed" → "allowed"
        "AI-generated content prohibited" → "prohibited"
        "LLM disclosure" → "must_disclose"
    """
    if not value or value == "unknown":
        return "unknown"

    value_lower = value.lower()

    # Check for prohibition
    prohibited_keywords = [
        "prohibited",
        "not allowed",
        "forbidden",
        "banned",
        "not permitted",
    ]
    for keyword in prohibited_keywords:
        if keyword in value_lower:
            return "prohibited"

    # Check for disclosure requirement (most common policy)
    disclosure_keywords = [
        "must be disclosed",
        "disclosure required",
        "must disclose",
        "should disclose",
        "disclosure",
        "must be marked",
        "must mark",
    ]
    for keyword in disclosure_keywords:
        if keyword in value_lower:
            return "must_disclose"

    # Check for discouraged
    discouraged_keywords = ["discouraged", "not recommended", "should not"]
    for keyword in discouraged_keywords:
        if keyword in value_lower:
            return "discouraged"

    # Check for allowed/permitted
    allowed_keywords = ["allowed", "permitted", "acceptable", "can use", "may use"]
    for keyword in allowed_keywords:
        if keyword in value_lower:
            return "allowed"

    # If LLM/AI mentioned but policy unclear, default to must_disclose
    # (most conferences require disclosure even if allowed)
    return "must_disclose"


# Specialized cleaners registry
_SPECIALIZED_CLEANERS = {
    "clean_file_size": _clean_file_size,
    "clean_page_count": _clean_page_count,
    "clean_system_name": _clean_system_name,
    "clean_publication_venue": _clean_publication_venue,
    "clean_deadline_date": _clean_deadline_date,
    "clean_notification_date": _clean_notification_date,
    "clean_artifact_evaluation": _clean_artifact_evaluation,
    "clean_llm_policy": _clean_llm_policy,
}


# ============================================
# PRIVATE: Helper Functions
# ============================================


def _detect_negation(text: str, keyword: str, window_size: int = 50) -> bool:
    """Detect if a keyword appears in a negated context."""
    text_lower = text.lower()
    keyword_lower = keyword.lower()

    keyword_pos = text_lower.find(keyword_lower)
    if keyword_pos == -1:
        return False

    start = max(0, keyword_pos - window_size)
    end = min(len(text_lower), keyword_pos + len(keyword_lower) + window_size)
    context = text_lower[start:end]

    negation_patterns = [
        r"\bnot\b",
        r"\bno\b",
        r"\bnever\b",
        r"\bwithout\b",
        r"\bneither\b",
        r"\bnor\b",
        r"\bcannot\b",
        r"\bcan\'t\b",
        r"\bwon\'t\b",
        r"\bwill not\b",
        r"\bdo not\b",
        r"\bdon\'t\b",
        r"\bdoes not\b",
        r"\bdoesn\'t\b",
        r"\bshould not\b",
        r"\bshouldn\'t\b",
        r"\bmust not\b",
        r"\bmustn\'t\b",
        r"\bmay not\b",
        r"\bmight not\b",
        r"\bforbid",
        r"\bprohibit",
        r"\bdisallow",
        r"\bban\b",
        r"\bunaccept",
        r"\bimpermiss",
    ]

    keyword_rel_pos = context.find(keyword_lower)
    context_before = context[: keyword_rel_pos + len(keyword_lower)]

    for neg_pattern in negation_patterns:
        if re.search(neg_pattern, context_before):
            return True

    if re.search(r"\bno\s+" + re.escape(keyword_lower), context):
        return True

    return False
