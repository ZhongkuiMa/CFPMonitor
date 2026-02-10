#!/usr/bin/env python3
"""CFPMonitor - Conference Submission Policy Tracker

Commands:
    search   - Search and archive CFP pages
    extract  - Extract rules from archived pages
    build    - Build comparison website
    all      - Run complete pipeline

Examples:
    python cfpmonitor.py all
    python cfpmonitor.py search --conference ICML --year 2025
    python cfpmonitor.py all --rank A
"""

import argparse
import sys
import time
from pathlib import Path

import yaml

from src.site.build import build_site


def _load_conferences(conf_file: Path, conference: str = None, rank: str = None):
    """Load conference metadata with optional filtering.

    :param conf_file: Path to conference metadata YAML file
    :param conference: Filter by specific conference abbreviation
    :param rank: Filter by conference rank (e.g., 'A', 'B')
    :return: List of conference dictionaries
    """
    if not conf_file.exists():
        raise FileNotFoundError(f"Conference file not found: {conf_file}")

    with open(conf_file) as f:
        data = yaml.safe_load(f)

    conferences = data.get("conferences", [])

    if conference:
        conferences = [
            c for c in conferences if c["short"].upper() == conference.upper()
        ]
        if not conferences:
            raise ValueError(f"Conference not found: {conference}")

    if rank:
        conferences = [
            c
            for c in conferences
            if c.get("rank", {}).get("ccf", "").upper() == rank.upper()
        ]

    return conferences


def discover_archived_conferences(data_dir: str, year: int):
    """Discover conferences from archived data directory.

    :param data_dir: Root data directory
    :param year: Filter by year (0 for all years)
    :return: List of conference dictionaries with 'abbr' and 'year' keys
    """
    raw_dir = Path(data_dir) / "raw"
    conferences = []

    for conf_dir in raw_dir.iterdir():
        if not conf_dir.is_dir() or conf_dir.name.startswith("."):
            continue

        for year_dir in conf_dir.iterdir():
            if year_dir.is_dir() and year_dir.name.isdigit():
                conf_year = int(year_dir.name)
                if year == 0 or conf_year == year:
                    conferences.append(
                        {"abbr": conf_dir.name.upper(), "year": conf_year}
                    )

    return conferences


def cmd_search(args):
    """Search and archive conference CFP pages.

    Orchestration flow:
    1. Load conference metadata
    2. CCFDDLCrawler: fill empty homepage entries, fetch deadline/date data + link pages
    3. ConfCrawler: BFS crawl conference websites (seeded with ccfddl links)
    4. WikiCFPCrawler: fetch complementary data

    :param args: Command line arguments
    :return: Exit code (0 for success)
    """
    from src.crawler import CCFDDLCrawler, ConfCrawler, WikiCFPCrawler

    conf_file = Path("data/metadata/conferences.yaml")
    conferences = _load_conferences(conf_file, args.conference, args.rank)

    total = len(conferences)
    print(f"\n=== Searching {total} conference(s) ===\n")
    search_t0 = time.time()

    ccfddl = CCFDDLCrawler(data_dir=args.data_dir)

    if not args.no_ccfddl:
        ccfddl.update_homepage_yaml(args.year, conferences)
        ccfddl.crawl_all(args.year, conferences)

    if not args.no_search_homepage:
        conf_crawler = ConfCrawler(
            data_dir=args.data_dir,
            use_search_engine=not args.no_search_engine,
        )
        conf_success = 0
        conf_failed = 0
        conf_t0 = time.time()
        for i, conf in enumerate(conferences, 1):
            abbr = conf["short"]
            name = conf["name"]
            t1 = time.time()
            print(f"[{i}/{total}] {abbr} {args.year}")
            result = conf_crawler.crawl(abbr, args.year, conf_name=name)
            elapsed = time.time() - t1
            if result["success"]:
                conf_success += 1
            else:
                conf_failed += 1
            print(f"  [{elapsed:.1f}s]\n")
        conf_time = time.time() - conf_t0
        print(
            f"=== Homepage: {conf_success} succeeded, {conf_failed} failed "
            f"out of {total} ({conf_time:.1f}s) ===\n"
        )

    if not args.no_wikicfp:
        wiki = WikiCFPCrawler(data_dir=args.data_dir)
        wiki.crawl_all(args.year, conferences)

    search_time = time.time() - search_t0
    print(f"\n=== Search complete: {total} conference(s) in {search_time:.1f}s ===")
    return 0


def cmd_extract(args):
    """Extract submission rules from archived CFP pages.

    :param args: Command line arguments
    :return: Exit code (0 for success)
    """
    from src.extractor import extract_and_save

    if args.conference:
        conf_file = Path("data/metadata/conferences.yaml")
        conferences = _load_conferences(conf_file, args.conference, args.rank)
        conferences = [{"abbr": c["short"], "year": args.year} for c in conferences]
    else:
        conferences = discover_archived_conferences(args.data_dir, args.year)

    total = len(conferences)
    print(f"\n=== Extracting {total} conference(s) ===\n")

    t0 = time.time()
    for i, conf in enumerate(conferences, 1):
        abbr = conf["abbr"]
        year = conf.get("year", args.year)
        t1 = time.time()

        print(f"[{i}/{total}] {abbr.upper()} {year}")

        extract_and_save(abbr.lower(), year, args.data_dir)

        elapsed = time.time() - t1
        print(f"  [{elapsed:.1f}s]\n")

    total_time = time.time() - t0
    print(f"=== Extract complete: {total} conference(s) in {total_time:.1f}s ===")
    return 0


def cmd_llm_extract(args):
    """Extract submission rules using LLM via Ollama.

    :param args: Command line arguments
    :return: Exit code (0 for success, 1 for failure)
    """
    from src.llm_extractor import llm_extract_and_save
    from src.llm_extractor.client import OllamaClient
    from src.llm_extractor.config import load_config

    # Load config and health check first (fail fast)
    try:
        config = load_config()
    except FileNotFoundError as e:
        print(f"\n[!] {e}")
        return 1

    client = OllamaClient(config)
    if not client.health_check():
        print("\n[!] Ollama health check failed. Is the SSH tunnel running?")
        print("    ssh -L 11434:localhost:11434 zhongkui@10.35.12.183")
        return 1

    if args.conference:
        conf_file = Path("data/metadata/conferences.yaml")
        conferences = _load_conferences(conf_file, args.conference, args.rank)
        conferences = [{"abbr": c["short"], "year": args.year} for c in conferences]
    else:
        conferences = discover_archived_conferences(args.data_dir, args.year)

    total = len(conferences)
    print(f"\n=== LLM Extracting {total} conference(s) ===\n")

    t0 = time.time()
    for i, conf in enumerate(conferences, 1):
        abbr = conf["abbr"]
        year = conf.get("year", args.year)
        t1 = time.time()

        print(f"[{i}/{total}] {abbr.upper()} {year}")

        llm_extract_and_save(abbr.lower(), year, args.data_dir)

        elapsed = time.time() - t1
        print(f"  [{elapsed:.1f}s]\n")

    total_time = time.time() - t0
    print(f"=== LLM Extract complete: {total} conference(s) in {total_time:.1f}s ===")
    return 0


def cmd_build(args):
    """Build comparison website from structured data.

    :param args: Command line arguments
    :return: Exit code (0 for success, 1 for failure)
    """
    build_site(structured_root=f"{args.data_dir}/structured", output_dir="docs")
    return 0


def cmd_all(args):
    """Run complete pipeline: search, extract, build.

    :param args: Command line arguments
    :return: Exit code from build step
    """
    t0 = time.time()
    cmd_search(args)
    cmd_extract(args)
    result = cmd_build(args)
    total_time = time.time() - t0
    print(f"\n=== Pipeline complete in {total_time:.1f}s ===")
    return result


def main():
    """Main entry point for CFPMonitor CLI."""
    parser = argparse.ArgumentParser(
        description="CFPMonitor - Conference Submission Policy Tracker",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parent_parser = argparse.ArgumentParser(add_help=False)
    parent_parser.add_argument(
        "--conference", type=str, help="Specific conference (e.g., ICML)"
    )
    parent_parser.add_argument(
        "--year", type=int, default=2026, help="Target year (default: 2026)"
    )
    parent_parser.add_argument(
        "--rank", type=str, help="Filter by rank (e.g., A, A*, B)"
    )
    parent_parser.add_argument(
        "--data-dir", type=str, default="data", help="Data directory (default: data)"
    )
    parent_parser.add_argument(
        "--no-search-engine",
        action="store_true",
        help="Skip conferences without a known homepage (do not use DuckDuckGo)",
    )
    parent_parser.add_argument(
        "--no-search-homepage",
        action="store_true",
        help="Skip BFS crawling of conference websites",
    )
    parent_parser.add_argument(
        "--no-ccfddl",
        action="store_true",
        help="Skip fetching data from ccfddl GitHub",
    )
    parent_parser.add_argument(
        "--no-wikicfp",
        action="store_true",
        help="Skip fetching data from WikiCFP",
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    subparsers.add_parser(
        "search", parents=[parent_parser], help="Search and archive CFP pages"
    )
    subparsers.add_parser(
        "extract", parents=[parent_parser], help="Extract rules from archived pages"
    )
    subparsers.add_parser(
        "llm_extract",
        parents=[parent_parser],
        help="Extract rules using LLM (requires Ollama)",
    )
    subparsers.add_parser(
        "build", parents=[parent_parser], help="Build comparison website"
    )
    subparsers.add_parser("all", parents=[parent_parser], help="Run complete pipeline")

    args = parser.parse_args()

    if args.command == "search":
        return cmd_search(args)
    elif args.command == "extract":
        return cmd_extract(args)
    elif args.command == "llm_extract":
        return cmd_llm_extract(args)
    elif args.command == "build":
        return cmd_build(args)
    elif args.command == "all":
        return cmd_all(args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
