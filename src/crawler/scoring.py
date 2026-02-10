"""Page relevance scoring for CFP content."""

POSITIVE_URL_PATTERNS = [
    ("call", 50),
    ("cfp", 60),
    ("submit", 45),  # Match "submit" (e.g., /submit-to-siggraph/)
    ("submission", 40),
    ("contribute", 40),  # Alternative to "submit"
    ("author", 35),
    ("paper", 30),
    ("deadline", 40),
    ("guideline", 30),
    ("instruction", 25),
    ("review", 20),
    ("abstract", 25),
    ("notification", 35),
]

LOWER_PRIORITY_URL_PATTERNS = [
    ("sponsor", 5),
    ("blog", 10),
    ("news", 15),
]

POSITIVE_CONTENT_KEYWORDS = {
    "call for papers": 100,
    "submission deadline": 80,
    "submission due": 75,
    "deadline": 50,
    "important dates": 70,
    "paper submission": 60,
    "papers due": 65,
    "notification": 60,
    "camera ready": 50,
    "abstract deadline": 50,
    "conference dates": 55,
    "author guidelines": 50,
    "author instructions": 50,
    "submission requirements": 50,
    "page limit": 45,
    "review process": 40,
    "double blind": 50,
    "double-blind": 50,
    "single blind": 30,
    "rebuttal": 40,
    "desk reject": 35,
    "ethics statement": 40,
    "artifact submission": 35,
    "code submission": 35,
    "reproducibility": 30,
    "submission system": 40,
    "openreview": 40,
    "easychair": 40,
}

LOW_RELEVANCE_PATTERNS = {
    "index of /": 0,
    "login required": 5,
    "page not found": 0,
    "coming soon": 0,
    "404": 0,
}

NEGATIVE_CONTENT_KEYWORDS = {
    "accommodation": -30,
    "hotel information": -30,
    "travel information": -25,
    "visitor information": -25,
    "student volunteer": -25,
    "social event": -20,
    "banquet dinner": -20,
    "visa information": -20,
    "code of conduct": -20,
    "frequently asked questions": -15,
    "expo": -15,
    "sponsorship": -20,
}

# Negative patterns for non-CFP content (accepted papers, venue info, etc.)
NEGATIVE_URL_PATTERNS = [
    # Accepted papers/proceedings pages
    ("accepted-papers", -100),
    ("accepted_papers", -100),
    ("acceptedpapers", -100),
    ("technical-sessions", -100),
    ("technical-session", -100),
    ("proceedings", -80),
    ("program-schedule", -80),
    ("program-at-a-glance", -70),
    ("paper-list", -100),
    ("paperlist", -100),
    ("main-track-accepted", -100),
    ("session-details", -80),
    # Venue/travel/registration pages (not CFP content)
    ("registration", -50),
    ("venue", -40),
    ("hotel", -60),
    ("travel", -50),
    ("accommodation", -60),
    ("know-before-you-go", -40),
    ("visitor-information", -40),
    ("code-of-conduct", -30),
    ("diversity", -20),
    ("ethics-guidelines", -30),
    ("banquet", -40),
    ("visa", -50),
]


def score_by_size(size_bytes: int) -> float:
    """Score page by content size. 3-30 KB is the sweet spot for CFP pages."""
    if 3000 <= size_bytes <= 30000:
        return 30
    if 1000 <= size_bytes < 3000:
        return 15
    if 30000 < size_bytes <= 100000:
        return 10
    return 0


def score_page(page: dict, text: str, depth: int) -> float:
    """Compute CFP relevance score from URL patterns, content keywords,
    page size, and crawl depth.

    Returns negative score for accepted papers/proceedings pages to filter them out.
    """
    url = page["url"].lower()
    text_lower = text.lower()

    score = 0.0
    score += sum(w for p, w in POSITIVE_URL_PATTERNS if p in url)
    score += sum(w for p, w in LOWER_PRIORITY_URL_PATTERNS if p in url)
    score += sum(
        w for p, w in NEGATIVE_URL_PATTERNS if p in url
    )  # Penalize non-CFP pages
    score += sum(w for kw, w in POSITIVE_CONTENT_KEYWORDS.items() if kw in text_lower)
    score += sum(w for kw, w in NEGATIVE_CONTENT_KEYWORDS.items() if kw in text_lower)
    score += sum(w for kw, w in LOW_RELEVANCE_PATTERNS.items() if kw in text_lower)
    score += score_by_size(len(text))
    score += {0: 20, 1: 10}.get(depth, 0)
    return score
