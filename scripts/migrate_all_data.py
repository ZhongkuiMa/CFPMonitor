#!/usr/bin/env python3
"""Re-extract all conferences using unified extractors.

Run:
    python scripts/migrate_all_data.py [--dry-run] [--backup]
"""

import argparse
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.extractor.extractor import extract_and_save


def create_backup(data_dir: Path) -> Path | None:
    """Create backup of structured data directory.

    :param data_dir: Root data directory
    :return: Path to backup directory or None if failed
    """
    structured_dir = data_dir / "structured"
    if not structured_dir.exists():
        print(f"No structured directory at {structured_dir}")
        return None

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = data_dir / f"structured.backup_{timestamp}"

    print(f"Creating backup at {backup_dir}...")
    shutil.copytree(structured_dir, backup_dir)
    print("Backup created")
    return backup_dir


def discover_conferences(data_dir: Path) -> list[tuple[str, int]]:
    """Discover all conferences from structured data directory.

    :param data_dir: Root data directory
    :return: List of (conference_abbr, year) tuples
    """
    structured_dir = data_dir / "structured"
    conferences = []

    for conf_dir in sorted(structured_dir.iterdir()):
        if not conf_dir.is_dir() or conf_dir.name.startswith("."):
            continue

        for yaml_file in sorted(conf_dir.glob("*.yaml")):
            if yaml_file.stem.isdigit():
                conferences.append((conf_dir.name, int(yaml_file.stem)))

    return conferences


def main() -> int:
    """Main migration function.

    :return: Exit code
    """
    parser = argparse.ArgumentParser(
        description="Re-extract all conferences using unified extractors"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Show what would be migrated"
    )
    parser.add_argument(
        "--backup", action="store_true", help="Create backup before migration"
    )
    parser.add_argument("--no-backup", action="store_true", help="Skip backup creation")
    parser.add_argument(
        "--data-dir", type=str, default="data", help="Root data directory"
    )
    args = parser.parse_args()

    data_dir = Path(args.data_dir)

    print("=" * 80)
    print("Conference Data Migration: Unified Extractors")
    print("=" * 80)
    print()

    conferences = discover_conferences(data_dir)

    if not conferences:
        print("No conferences found")
        return 1

    print(f"Found {len(conferences)} conferences")
    print()

    if args.dry_run:
        print("DRY RUN MODE - No changes will be made")
        print()
        print("Conferences to re-extract:")
        for i, (abbr, year) in enumerate(conferences, 1):
            print(f"  {i:3d}. {abbr.upper()} {year}")
        print()
        print(f"Total: {len(conferences)} conferences")
        return 0

    if args.backup and not args.no_backup:
        backup_dir = create_backup(data_dir)
        if not backup_dir:
            print("Backup failed - aborting")
            print("Use --no-backup to skip backup")
            return 1
        print()
    elif not args.no_backup:
        print("No backup will be created")
        print("Use --backup to create backup")
        print("Use --no-backup to skip this warning")
        print()
        response = input("Continue without backup? [y/N]: ").strip().lower()
        if response != "y":
            print("Migration cancelled")
            return 0
        print()

    print("=" * 80)
    print("Starting Migration")
    print("=" * 80)
    print()

    start_time = time.time()
    success_count = 0
    errors = []

    for i, (abbr, year) in enumerate(conferences, 1):
        print(f"[{i}/{len(conferences)}] {abbr.upper()} {year}...", end=" ", flush=True)

        try:
            extract_and_save(abbr, year, str(data_dir))
            success_count += 1
            print("OK")
        except Exception as e:
            errors.append((abbr, year, str(e)))
            print(f"ERROR: {e}")

    elapsed = time.time() - start_time

    print()
    print("=" * 80)
    print("Migration Complete")
    print("=" * 80)
    print()
    total = len(conferences)
    error_count = len(errors)
    print(f"Total conferences: {total}")
    print(f"  Successful: {success_count} ({success_count / total * 100:.1f}%)")
    print(f"  Errors: {error_count} ({error_count / total * 100:.1f}%)")
    print(f"Time elapsed: {elapsed:.1f}s")
    print()

    if errors:
        print("Errors encountered:")
        for abbr, year, error in errors:
            print(f"  - {abbr.upper()} {year}: {error}")
        print()
        print("Migration completed with errors")
        return 1

    print("Migration completed successfully")
    print()
    print("Next steps:")
    print("  1. python -m src.verify_extraction")
    print("  2. python -m src.analyze_extraction_quality")
    print("  3. python cfpmonitor.py build")
    print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
