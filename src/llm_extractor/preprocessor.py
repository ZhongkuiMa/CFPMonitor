"""Data loaders for the LLM extraction pipeline.

Loads raw crawled text files and structured sources (ccfddl, wikicfp)
without any filtering or cleaning.
"""

from pathlib import Path

import yaml


def load_raw_texts(conf_abbr: str, year: int, data_dir: str) -> dict[str, str]:
    """Load all raw crawled text files for a conference.

    :param conf_abbr: Conference abbreviation (e.g. "icml").
    :param year: Conference year.
    :param data_dir: Root data directory.
    :returns: ``{filename_stem: raw_text}`` for non-empty files.
    """
    archive_dir = Path(data_dir) / "raw" / conf_abbr.lower() / str(year)
    if not archive_dir.exists():
        return {}
    texts = {}
    for f in archive_dir.glob("*.txt"):
        content = f.read_text(encoding="utf-8")
        if content.strip():
            texts[f.stem] = content
    return texts


def load_structured_sources(conf_abbr: str, year: int, data_dir: str) -> dict:
    """Load ccfddl and wikicfp structured data for a conference.

    :param conf_abbr: Conference abbreviation.
    :param year: Conference year.
    :param data_dir: Root data directory.
    :returns: ``{"ccfddl": dict | None, "wikicfp": dict | None}``.
    """
    result = {}
    for name in ("ccfddl", "wikicfp"):
        path = Path(data_dir) / name / conf_abbr.lower() / f"{year}.yaml"
        if path.exists():
            with open(path, encoding="utf-8") as f:
                result[name] = yaml.safe_load(f)
        else:
            result[name] = None
    return result
