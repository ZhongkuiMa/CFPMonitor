"""Data normalizers for CFP extraction pipeline.

Provides normalization functions for various extracted fields:
- Location: City/country extraction and formatting
- Dates: Date format standardization
- Page limits: Numeric normalization
- Other fields: Future normalizations

These normalizers run after extraction to clean and standardize data before
saving to structured YAML files.

The location normalization follows a clean 4-phase approach:
1. Normalize Input: Convert to lowercase, clean strings
2. Split and Parse: Split by delimiters systematically
3. Extract City/Country: Apply pattern matching
4. Format Output: Apply proper capitalization at the end
"""

import re
from typing import Optional, Tuple, Dict, Any, List

# ==============================================================================
# Data Structures (All Lowercase for Matching)
# ==============================================================================

# Country normalization map (lowercase keys)
COUNTRY_MAP_LOWER = {
    # USA variations
    "us": "US",  # Already normalized form
    "usa": "US",
    "usa.": "US",
    "u.s.a": "US",
    "u.s.a.": "US",
    "u.s.": "US",
    "united states": "US",
    "united states of america": "US",
    "florida usa": "US",  # State + USA format
    "south carolina usa": "US",  # State + USA format
    # UK variations
    "uk": "UK",  # Already normalized form
    "u.k.": "UK",
    "united kingdom": "UK",
    "united kindom": "UK",  # Common typo
    "england": "UK",
    "scotland": "UK",
    "wales": "UK",
    "northern ireland": "UK",
    # UAE variations
    "uae": "UAE",  # Already normalized form
    "u.a.e": "UAE",
    "u.a.e.": "UAE",
    "united arab emirates": "UAE",
    # China and territorial variations
    "china": "China",
    "p.r. china": "China",  # People's Republic of China
    "taiwan": "Taiwan, China",
    "hong kong": "Hong Kong, China",
    "hong kong sar": "Hong Kong, China",
    "macao": "Macao, China",
    "macau": "Macao, China",
    "macao sar": "Macao, China",
    "macau sar": "Macao, China",
    # South Korea variations
    "korea": "South Korea",
    "s.korea": "South Korea",
    "s. korea": "South Korea",
    "republic of korea": "South Korea",
    "south korea": "South Korea",
    "south korea.": "South Korea",  # With period typo
    # Canada variations
    "canada": "Canada",
    "canada.": "Canada",  # With period typo
    "vancouver bc canada": "Canada",  # City + Province + Country
    # Mexico variations
    "mexico": "Mexico",
    "méxico": "Mexico",  # Spanish spelling
    # Czech Republic variations
    "czech republic": "Czech Republic",
    "czechia": "Czech Republic",
    # Turkey variations (including official Turkish name)
    "turkey": "Turkey",
    "türkiye": "Turkey",
    "türki̇ye": "Turkey",  # Lowercased from "Türkİye" (dotted capital İ)
    # Caribbean
    "curaçao": "Curacao",
    "curacao": "Curacao",
    # Venue/tourism phrases wrongly used as country
    "home of robin hood": "UK",  # Nottingham tourism tagline
    "minato city": "Japan",  # Ward of Tokyo
}

# US states (lowercase for matching)
US_STATES_LOWER = {
    "alabama",
    "alaska",
    "arizona",
    "arkansas",
    "california",
    "colorado",
    "connecticut",
    "delaware",
    "florida",
    "georgia",
    "hawaii",
    "idaho",
    "illinois",
    "indiana",
    "iowa",
    "kansas",
    "kentucky",
    "louisiana",
    "maine",
    "maryland",
    "massachusetts",
    "michigan",
    "minnesota",
    "mississippi",
    "missouri",
    "montana",
    "nebraska",
    "nevada",
    "new hampshire",
    "new jersey",
    "new mexico",
    "new york",
    "north carolina",
    "north dakota",
    "ohio",
    "oklahoma",
    "oregon",
    "pennsylvania",
    "rhode island",
    "south carolina",
    "south dakota",
    "tennessee",
    "texas",
    "utah",
    "vermont",
    "virginia",
    "washington",
    "west virginia",
    "wisconsin",
    "wyoming",
    "district of columbia",
    "dc",
}

# US state abbreviations (lowercase for matching)
US_STATE_ABBREV_LOWER = {
    "al",
    "ak",
    "az",
    "ar",
    "ca",
    "co",
    "ct",
    "de",
    "fl",
    "ga",
    "hi",
    "id",
    "il",
    "in",
    "ia",
    "ks",
    "ky",
    "la",
    "me",
    "md",
    "ma",
    "mi",
    "mn",
    "ms",
    "mo",
    "mt",
    "ne",
    "nv",
    "nh",
    "nj",
    "nm",
    "ny",
    "nc",
    "nd",
    "oh",
    "ok",
    "or",
    "pa",
    "ri",
    "sc",
    "sd",
    "tn",
    "tx",
    "ut",
    "vt",
    "va",
    "wa",
    "wv",
    "wi",
    "wy",
    "dc",
}

# City-states (lowercase for matching)
CITY_STATES_LOWER = {"singapore", "monaco", "vatican city"}

# China special administrative regions and territories (lowercase for matching)
CHINA_TERRITORIES_LOWER = {
    "hong kong",
    "hong kong sar",
    "taiwan",
    "macao",
    "macau",
    "macau sar",
    "macao sar",
}

# Canonical territory name mapping (SAR variants → canonical)
_TERRITORY_CANONICAL = {
    "hong kong sar": "hong kong",
    "macau sar": "macau",
    "macao sar": "macao",
}

# Venue indicators (lowercase for matching)
VENUE_INDICATORS_LOWER = {
    "centre",
    "center",
    "convention",
    "hotel",
    "resort",
    "spa",
    "university",
    "palace",
    "exhibition",
    "congress",
    "marriott",
    "hilton",
    "sheraton",
    "hyatt",
    "westin",
    "conference",
    "school",
    "campus",
    "building",
    "hall",
    "complex",
}

# ==============================================================================
# Phase 1: Normalize Input
# ==============================================================================


def _clean_location_string(location: str) -> str:
    """Clean location string (input is already lowercase).

    Removes:
    - Parenthetical info: (hybrid), (virtual)
    - "and online", "and virtual" suffixes
    - Short venue prefixes: "ticc,", "icc,"
    - Converts " - " to ", " for city-country format

    Args:
        location: Lowercase location string

    Returns:
        Cleaned lowercase location string
    """
    # Remove parentheses and content
    location = re.sub(r"\s*\([^)]*\)\s*", " ", location)

    # Remove "and online/virtual" and "& virtual" suffixes
    location = re.sub(r"\s+(and|&)\s+(online|virtual)\s*$", "", location)
    location = re.sub(r"\s+/\s+virtual.*$", "", location)  # Remove "/ Virtual Venue"

    # Remove short acronym prefixes (2-4 letters followed by comma)
    # e.g., "ticc, brisbane" -> "brisbane", "icc, sydney" -> "sydney"
    # Limited to 2-4 letters to avoid removing real city names like "paris"
    location = re.sub(r"^[a-z]{2,4},\s+", "", location)

    # Convert " - " to ", " for city-country format
    # e.g., "agadir - morocco" -> "agadir, morocco"
    if " - " in location and "," not in location:
        location = location.replace(" - ", ", ")

    return location.strip()


# ==============================================================================
# Phase 2: Split and Parse
# ==============================================================================


def _is_corrupted(parts: List[str]) -> bool:
    """Check if location parts are corrupted data (all lowercase).

    Detects:
    - Sentence fragments: "viewed", "backdrop", "from", "acronyms", "instance", "between"
    - Month names: "january" through "december"
    - Day names: "monday" through "sunday"
    - Common words: "authors", "the", "they", "for"
    - Concatenated words: "chinaasiacrypt", "australiamaria"
    - Person names: "john smith" followed by random chars
    - Pipe characters: "|"
    - Just numbers or conference acronym + year

    Args:
        parts: List of lowercase location parts

    Returns:
        True if data is corrupted
    """
    combined = " ".join(parts)

    # Sentence fragment indicators and common words
    corruption_words = [
        "viewed",
        "backdrop",
        "acronyms",
        "against this",
        "instance",
        "between",
        "authors",
        "for",
        "they",
        "the",
        "virtual",
        "online",
        "hybrid",
    ]
    if any(word in combined for word in corruption_words):
        return True

    # Check if any part is exactly "virtual", "online", or "hybrid"
    for part in parts:
        if part.strip() in ["virtual", "online", "hybrid"]:
            return True

    # Month names (common corruption pattern like "USA, May" or "United Kingdom, December")
    month_names = [
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
    # Check if any part is exactly a month name
    for part in parts:
        if part.strip() in month_names:
            return True

    # Day names (e.g., "CanadaMonday, June")
    day_names = [
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
        "sunday",
    ]
    for part in parts:
        if part.strip() in day_names:
            return True
        # Check for concatenated day names (e.g., "canadamonday")
        if any(day in part for day in day_names):
            return True

    # Concatenated country names (lowercase patterns)
    # e.g., "chinaasiacrypt", "australiamaria", "canadamonday"
    if re.search(
        r"(china|australia|portugal|japan|france|germany|italy|spain|india|korea|canada|brazil)[a-z]{5,}",
        combined,
    ):
        return True

    # Pipe characters indicate corrupted data
    if "|" in combined:
        return True

    # Check for venue names that are clearly not locations
    # e.g., "5* St. Raphael Resort", "University in Siedlce"
    venue_patterns = [
        r"\d+\*",  # Star ratings like "5*"
        r"^university\s+(in|of)\s+",  # "University in/of X" as the whole location
        r"^\d+\s+",  # Starts with a number
    ]
    for pattern in venue_patterns:
        if re.search(pattern, combined):
            return True

    # Check if the location is ONLY a venue (single part that is a venue)
    if len(parts) == 1 and _is_venue(parts[0]):
        # Allow known city-states even if they contain venue indicators
        if parts[0] not in CITY_STATES_LOWER:
            return True

    # Check for unusually long single words (likely concatenated/corrupted)
    # e.g., "chinaasiacrypt" - but allow multi-word parts like "united states of america"
    for part in parts:
        # Only check single words (no spaces)
        if " " not in part and len(part) > 20 and part not in CITY_STATES_LOWER:
            return True

    # Just numbers
    if re.match(r"^\d+$", combined):
        return True

    # Conference acronym + year (e.g., "acl 2024")
    if re.match(r"^[a-z]+\s+\d{4}$", combined):
        return True

    return False


# ==============================================================================
# Phase 3: Extract City and Country
# ==============================================================================


def _is_venue(text: str) -> bool:
    """Check if text looks like a venue name (input is lowercase).

    Args:
        text: Lowercase text to check

    Returns:
        True if text contains venue indicators
    """
    # Check for venue indicators
    if any(indicator in text for indicator in VENUE_INDICATORS_LOWER):
        return True

    # Check for verbose venue descriptions
    if text.startswith(("conference center", "convention center", "exhibition hall")):
        return True

    # Check if text is unusually long (likely a full venue description)
    if len(text) > 40:
        return True

    return False


def _handle_single_part(part: str) -> Tuple[Optional[str], Optional[str]]:
    """Handle single-part location (lowercase input).

    Checks for:
    - China territories (e.g., "hong kong")
    - City-states (e.g., "singapore")
    - Country names

    Args:
        part: Single lowercase location part

    Returns:
        Tuple of (city_lower, country_lower)
    """
    # Check if it's a China territory
    if part in CHINA_TERRITORIES_LOWER:
        canonical = _TERRITORY_CANONICAL.get(part, part)
        return (canonical, canonical)

    # Check if it's a city-state
    if part in CITY_STATES_LOWER:
        return (part, part)

    # Check if it contains a China territory name (e.g., "hong kong disneyland")
    for territory in CHINA_TERRITORIES_LOWER:
        if territory in part:
            canonical = _TERRITORY_CANONICAL.get(territory, territory)
            return (canonical, canonical)

    # Check if it contains a city-state name (e.g., "singapore expo")
    for city_state in CITY_STATES_LOWER:
        if city_state in part:
            return (city_state, city_state)

    # Check if it's multiple words (e.g., "sacramento united states")
    words = part.split()
    if len(words) == 2:
        # Check if second word is a country or US state
        if words[1] in COUNTRY_MAP_LOWER:
            country = words[1]
            return (words[0], country)
        if words[1] in US_STATES_LOWER or words[1] in US_STATE_ABBREV_LOWER:
            return (words[0], "us")
        # If second word is not a known country/state, it's likely a multi-word city name
        # e.g., "San Francisco", "New Delhi", "Buenos Aires"
        return (None, None)

    if len(words) > 2:
        # Multiple words, check if last part is a country
        potential_country = " ".join(words[1:])
        if potential_country in COUNTRY_MAP_LOWER:
            return (words[0], potential_country)
        # If not a known country, it's likely a multi-word city/place name
        return (None, None)

    # Single word that's not a known location type
    # If it's a single word and not in our country list, it's likely a city name
    # without country info, so mark as unknown
    if len(words) == 1:
        # List of common/known countries (beyond the normalization map)
        known_countries = {
            "afghanistan",
            "albania",
            "algeria",
            "andorra",
            "angola",
            "argentina",
            "armenia",
            "australia",
            "austria",
            "azerbaijan",
            "bahamas",
            "bahrain",
            "bangladesh",
            "barbados",
            "belarus",
            "belgium",
            "belize",
            "benin",
            "bhutan",
            "bolivia",
            "bosnia",
            "botswana",
            "brazil",
            "brunei",
            "bulgaria",
            "burkina",
            "burundi",
            "cambodia",
            "cameroon",
            "canada",
            "cape",
            "central",
            "chad",
            "chile",
            "china",
            "colombia",
            "comoros",
            "congo",
            "costa",
            "croatia",
            "cuba",
            "cyprus",
            "czechia",
            "denmark",
            "djibouti",
            "dominica",
            "dominican",
            "ecuador",
            "egypt",
            "estonia",
            "ethiopia",
            "fiji",
            "finland",
            "france",
            "gabon",
            "gambia",
            "georgia",
            "germany",
            "ghana",
            "greece",
            "grenada",
            "guatemala",
            "guinea",
            "guyana",
            "haiti",
            "honduras",
            "hungary",
            "iceland",
            "india",
            "indonesia",
            "iran",
            "iraq",
            "ireland",
            "israel",
            "italy",
            "jamaica",
            "japan",
            "jordan",
            "kazakhstan",
            "kenya",
            "kiribati",
            "korea",
            "kosovo",
            "kuwait",
            "kyrgyzstan",
            "laos",
            "latvia",
            "lebanon",
            "lesotho",
            "liberia",
            "libya",
            "liechtenstein",
            "lithuania",
            "luxembourg",
            "madagascar",
            "malawi",
            "malaysia",
            "maldives",
            "mali",
            "malta",
            "marshall",
            "mauritania",
            "mauritius",
            "mexico",
            "micronesia",
            "moldova",
            "monaco",
            "mongolia",
            "montenegro",
            "morocco",
            "mozambique",
            "myanmar",
            "namibia",
            "nauru",
            "nepal",
            "netherlands",
            "nicaragua",
            "niger",
            "nigeria",
            "norway",
            "oman",
            "pakistan",
            "palau",
            "palestine",
            "panama",
            "papua",
            "paraguay",
            "peru",
            "philippines",
            "poland",
            "portugal",
            "qatar",
            "romania",
            "russia",
            "rwanda",
            "samoa",
            "san",
            "saudi",
            "senegal",
            "serbia",
            "seychelles",
            "sierra",
            "slovakia",
            "slovenia",
            "solomon",
            "somalia",
            "south",
            "spain",
            "sri",
            "sudan",
            "suriname",
            "sweden",
            "switzerland",
            "syria",
            "taiwan",
            "tajikistan",
            "tanzania",
            "thailand",
            "timor",
            "togo",
            "tonga",
            "trinidad",
            "tunisia",
            "turkey",
            "turkmenistan",
            "tuvalu",
            "uganda",
            "ukraine",
            "uruguay",
            "uzbekistan",
            "vanuatu",
            "vatican",
            "venezuela",
            "vietnam",
            "yemen",
            "zambia",
            "zimbabwe",
        }

        if part not in known_countries and part not in COUNTRY_MAP_LOWER:
            # Unknown single word - likely a city name
            return (None, None)

    # Otherwise treat as country
    return (None, part)


def _handle_two_parts(parts: List[str]) -> Tuple[Optional[str], Optional[str]]:
    """Handle two-part location (lowercase input).

    Handles:
    - "city, country" (e.g., "vienna, austria")
    - "city, state" (e.g., "austin, texas")
    - "venue, city" (skip venue)

    Args:
        parts: Two lowercase location parts

    Returns:
        Tuple of (city_lower, country_lower)
    """
    city = parts[0]
    country = parts[1]

    # If first part is a venue, try to extract city from it
    if _is_venue(city):
        # Try to extract city from venue name
        # For now, skip the venue and use the second part if it's not a country alone
        if country not in COUNTRY_MAP_LOWER and country not in US_STATES_LOWER:
            # The second part might be the city
            return (country, None)
        else:
            # Can't extract city, just use country
            return (None, country)

    # Check if first part (city) is a China territory
    if city in CHINA_TERRITORIES_LOWER:
        canonical = _TERRITORY_CANONICAL.get(city, city)
        return (canonical, canonical)

    # Check if second part is a China territory
    if country in CHINA_TERRITORIES_LOWER:
        return (city, country)

    # Check if second part is a US state
    if country in US_STATES_LOWER or country in US_STATE_ABBREV_LOWER:
        return (city, "us")

    # Standard city, country
    return (city, country)


def _handle_multi_parts(parts: List[str]) -> Tuple[Optional[str], Optional[str]]:
    """Handle three or more part location (lowercase input).

    Handles:
    - "city, state, usa" (e.g., "denver, colorado, united states")
    - "venue, city, country" (e.g., "icc, berlin, germany")
    - "city, region, country"

    Args:
        parts: Three or more lowercase location parts

    Returns:
        Tuple of (city_lower, country_lower)
    """
    # Check for "City, State, USA" pattern
    if len(parts) == 3:
        last_part = parts[2]
        if last_part in COUNTRY_MAP_LOWER and COUNTRY_MAP_LOWER[last_part] == "US":
            # Check if middle part is a US state
            if parts[1] in US_STATES_LOWER or parts[1] in US_STATE_ABBREV_LOWER:
                return (parts[0], "us")

    # Check if first part is a venue
    if _is_venue(parts[0]):
        # Skip venue, use second part as city
        city = parts[1]
        country = parts[-1]
        return (city, country)

    # Standard extraction: first part is city, last part is country
    city = parts[0]
    country = parts[-1]

    return (city, country)


def _extract_city_country(parts: List[str]) -> Tuple[Optional[str], Optional[str]]:
    """Extract city and country from parts (all lowercase).

    Handles:
    - 1 part: Check if city-state or country
    - 2 parts: city, country OR city, state
    - 3+ parts: city, state, country OR venue, city, country

    Args:
        parts: List of lowercase location parts

    Returns:
        Tuple of (city_lower, country_lower)
    """
    if len(parts) == 1:
        return _handle_single_part(parts[0])
    elif len(parts) == 2:
        return _handle_two_parts(parts)
    else:  # 3+ parts
        return _handle_multi_parts(parts)


# ==============================================================================
# Phase 4: Format Output
# ==============================================================================


def _normalize_and_format_country(country_lower: str) -> str:
    """Normalize and format country name.

    Steps:
    1. Look up in normalization map (lowercase keys)
    2. If US state, return "US"
    3. Apply title case for output
    4. Special handling for abbreviations (US, UK, UAE - all caps)

    Args:
        country_lower: Lowercase country name

    Returns:
        Formatted country name
    """
    # Check normalization map
    if country_lower in COUNTRY_MAP_LOWER:
        return COUNTRY_MAP_LOWER[country_lower]

    # Check if it's a US state
    if country_lower in US_STATES_LOWER or country_lower in US_STATE_ABBREV_LOWER:
        return "US"

    # Apply title case
    return country_lower.title()


def _format_city_name(city_lower: str) -> str:
    """Format city name with proper capitalization.

    Args:
        city_lower: Lowercase city name

    Returns:
        Formatted city name with title case
    """
    return city_lower.title()


def _create_display_string(city: Optional[str], country: Optional[str]) -> str:
    """Create display string from city and country.

    Args:
        city: Formatted city name (or None)
        country: Formatted country name (or None)

    Returns:
        Display string
    """
    if not city and not country:
        return "Unknown"

    # City-state exception: single word display
    if city and country and city == country:
        return city

    # China territory exception: display only country
    # If city is a China territory and country contains ", China", show only country
    if city and country and ", China" in country:
        # Check if city (lowercase) is a China territory
        if city.lower() in CHINA_TERRITORIES_LOWER:
            return country

    # Standard display
    if city and country:
        return f"{city}, {country}"
    elif city:
        return city
    elif country:
        return country
    else:
        return "Unknown"


# ==============================================================================
# Main Function
# ==============================================================================


def extract_location_info(
    location_str: str,
) -> Tuple[Optional[str], Optional[str], str]:
    """Extract city, country, and formatted display from location string.

    Uses a clean 4-phase approach:
    1. Normalize to lowercase, clean string
    2. Split by delimiters
    3. Extract city and country
    4. Format output with proper capitalization

    Args:
        location_str: Raw location string from conference data

    Returns:
        Tuple of (city, country, display_string) where:
        - city: Extracted city name (title case)
        - country: Normalized country name
        - display_string: Formatted as "{city}, {country}" or just city for city-states
                         Returns "Unknown" if extraction fails
    """
    # Phase 1: Normalize Input
    # 1. Early exit for empty/unknown
    if not location_str or location_str.strip() in ("", "unknown", "Unknown"):
        return (None, None, "Unknown")

    # 2. Normalize to lowercase
    location = location_str.strip().lower()

    # 3. Clean: remove parentheses, "and online", etc.
    location = _clean_location_string(location)

    # Phase 2: Split and Parse
    # 4. Split by comma
    parts = [p.strip() for p in location.split(",") if p.strip()]

    if len(parts) == 0:
        return (None, None, "Unknown")

    # 5. Check for corrupted data (all lowercase now)
    if _is_corrupted(parts):
        return (None, None, "Unknown")

    # Phase 3: Extract City and Country
    # 6. Apply pattern matching (all lowercase)
    city_lower, country_lower = _extract_city_country(parts)

    if not city_lower and not country_lower:
        return (None, None, "Unknown")

    # Phase 4: Format Output
    # 7. Apply proper capitalization
    city = _format_city_name(city_lower) if city_lower else None
    country = _normalize_and_format_country(country_lower) if country_lower else None

    # 8. Create display string
    display = _create_display_string(city, country)

    return (city, country, display)


# ==============================================================================
# Public API - Normalize all rules
# ==============================================================================


def normalize_location_rule(rule: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize a location rule with structured location data.

    Args:
        rule: Rule dict with 'value' key containing location string

    Returns:
        Updated rule dict with normalized location metadata
    """
    if not rule or "value" not in rule:
        return rule

    location_str = rule.get("value", "")
    if not location_str or location_str == "unknown":
        return rule

    city, country, display = extract_location_info(location_str)

    # Add normalized location metadata to rule
    rule["normalized"] = {
        "city": city,
        "country": country,
        "display": display,
        "raw": location_str,
    }

    return rule


def normalize_rules(rules: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Normalize all extractable fields in rules dict.

    This is the main entry point for normalization, called after extraction
    and merging phases.

    Args:
        rules: Dict of {field_name: rule_dict}

    Returns:
        Updated rules dict with normalized data
    """
    # Normalize location
    if "conference_location" in rules:
        rules["conference_location"] = normalize_location_rule(
            rules["conference_location"]
        )

    # Future normalizations can be added here:
    # - Date normalization
    # - Page limit normalization
    # - etc.

    return rules
