"""URL and content-type filtering for the crawler."""

EXCLUDED_DOMAINS = [
    "wikicfp.com",
    "wikipedia.org",
    "paperswithcode.com",
    "conferencelist.info",
    "medium.com",
    "reddit.com",
    "twitter.com",
    "facebook.com",
    "mlscientist.com",
    "aclanthology.org",
    "openreview.net",
    "aideadlines.org",
    "journalsearches.com",
    "swoogo.com",
    "grokipedia.com",
]

SKIP_FILE_EXTENSIONS = {
    ".pdf",
    ".doc",
    ".docx",
    ".txt",
    ".rtf",
    ".zip",
    ".tar",
    ".gz",
    ".rar",
    ".7z",
    ".ppt",
    ".pptx",
    ".xls",
    ".xlsx",
    ".mp3",
    ".mp4",
    ".wav",
    ".avi",
    ".mov",
    ".exe",
    ".dmg",
    ".pkg",
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".svg",
}

SKIP_CONTENT_TYPES = {
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument",
    "application/zip",
    "application/x-rar-compressed",
    "application/gzip",
    "image/",
    "video/",
    "audio/",
}

_SKIP_URL_PATTERNS = ["arxiv.org", "researchgate.net", "scholar.google"]

# URL patterns for accepted papers/proceedings pages (not CFP content)
_SKIP_ACCEPTED_PAPERS_PATTERNS = [
    "accepted-papers",
    "accepted_papers",
    "acceptedpapers",
    "technical-sessions",
    "technical-session",
    "proceedings",
    "program-schedule",
    "program-at-a-glance",
    "paper-list",
    "paperlist",
    "main-track-accepted",
    "accepted-abstracts",
    "full-program",
    "session-details",
]


def should_skip_url(url: str) -> bool:
    """Return True if *url* points to a non-HTML resource (PDF, paper site, etc.)."""
    url_lower = url.lower()
    if any(url_lower.endswith(ext) for ext in SKIP_FILE_EXTENSIONS):
        return True
    if any(p in url_lower for p in _SKIP_URL_PATTERNS):
        return True
    # Skip accepted papers/proceedings pages
    if any(p in url_lower for p in _SKIP_ACCEPTED_PAPERS_PATTERNS):
        return True
    return False


def should_skip_content_type(content_type: str) -> bool:
    """Return True if *content_type* is not an HTML-like MIME type."""
    if not content_type:
        return False

    ct = content_type.lower()
    if "text/html" in ct or "application/xhtml" in ct:
        return False
    if any(skip in ct for skip in SKIP_CONTENT_TYPES):
        return True
    return "text/" not in ct


def is_obviously_non_cfp(text: str) -> bool:
    """Return True if *text* is empty, a 404 page, or a placeholder."""
    if len(text) < 50:
        return True
    t = text.lower()
    if ("page not found" in t or "404" in t) and len(text) < 300:
        return True
    if "coming soon" in t and len(text) < 200:
        return True
    return False


def has_obvious_wrong_year(text: str, target_year: int) -> bool:
    """Return True if *text* is dominated by a different year."""
    t = text.lower()
    year_str = str(target_year)
    next_year = str(target_year + 1)

    if next_year in t and t.count(next_year) > t.count(year_str) * 2:
        return True
    return any(p in t for p in ["historical record", "proceedings are available"])


def is_accepted_papers_page(text: str) -> bool:
    """Return True if page appears to be an accepted papers/proceedings list.

    These pages list hundreds of accepted papers with abstracts, which are
    not relevant for CFP extraction and can be very large (>1 MB).
    """
    if len(text) < 1000:  # Too short to be a paper list
        return False

    t = text.lower()

    # Strong indicators: excessive occurrences of "abstract"
    # A typical paper list has 100+ papers, each with "Abstract:"
    abstract_count = t.count("abstract")
    if abstract_count > 100:
        return True

    # Check for multiple indicators of accepted papers page
    indicators = [
        ("accepted papers", 2),
        ("technical sessions", 2),
        ("proceedings", 1),
        ("paper presentations", 2),
        ("session schedule", 1),
        ("list of keywords", 1),  # Papers often list keywords
    ]

    indicator_score = sum(weight for phrase, weight in indicators if phrase in t)

    # If we have strong indicators AND the page is very large, it's likely a paper list
    # Large pages (>500 KB) with "accepted papers" in title are almost certainly paper lists
    if len(text) > 500000 and "accepted papers" in t:  # >500 KB
        return True

    if indicator_score >= 2 and len(text) > 100000:  # >100 KB
        return True

    return False
