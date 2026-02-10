"""Validate unified extraction system.

Run:
    python -m src.investigation.validate_migration
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.extractor.extractor import extract_rules


SAMPLE_CONFERENCES = [
    ("neurips", 2024),
    ("icml", 2024),
    ("iclr", 2024),
    ("aaai", 2024),
    ("cvpr", 2024),
    ("eccv", 2024),
    ("acl", 2024),
    ("emnlp", 2024),
    ("naacl", 2024),
    ("chi", 2024),
    ("uist", 2024),
    ("www", 2024),
    ("sigir", 2024),
    ("coling", 2024),
    ("icra", 2024),
    ("ijcai", 2024),
    ("vldb", 2024),
    ("fse", 2024),
    ("issta", 2024),
    ("ase", 2024),
]

UNIFIED_FIELDS = [
    "page_limit",
    "page_limit_exclusions",
    "double_blind",
    "single_blind",
    "open_review",
    "rebuttal_allowed",
    "desk_rejection",
    "reciprocal_review",
    "artifact_evaluation",
    "llm_policy",
    "concurrent_submission",
    "arxiv_preprint",
    "statements",
    "template_required",
    "supplementary_material",
    "presentation_format",
    "financial_aid",
    "workshops",
    "conference_format",
]


def validate_extraction(
    conf_abbr: str, year: int, data_dir: str = "data"
) -> dict[str, str | int | dict]:
    """Validate extraction for a single conference.

    :param conf_abbr: Conference abbreviation
    :param year: Conference year
    :param data_dir: Data directory
    :return: Validation results dictionary
    """
    result = extract_rules(conf_abbr, year, data_dir)

    if not result or not result.get("rules"):
        return {
            "status": "failed",
            "error": "No rules extracted",
            "fields_extracted": 0,
        }

    rules = result["rules"]
    fields_extracted = sum(1 for f in rules if rules[f].get("value") != "unknown")
    unified_fields_extracted = sum(
        1 for f in UNIFIED_FIELDS if f in rules and rules[f].get("value") != "unknown"
    )

    return {
        "status": "success",
        "fields_extracted": fields_extracted,
        "total_fields": len(rules),
        "unified_fields_extracted": unified_fields_extracted,
        "unified_fields_total": len(UNIFIED_FIELDS),
        "completeness": result.get("completeness", {}),
        "quality": result.get("quality", {}),
    }


def main() -> int:
    """Run validation on sample conferences.

    :return: Exit code (0 for success, 1 for failure)
    """
    print("=" * 80)
    print("Unified Extraction System Validation")
    print("=" * 80)
    print()

    results = []
    for conf_abbr, year in SAMPLE_CONFERENCES:
        print(f"Testing {conf_abbr.upper()} {year}...", end=" ")

        try:
            result = validate_extraction(conf_abbr, year)
        except Exception as e:
            result = {
                "status": "error",
                "error": str(e),
                "fields_extracted": 0,
            }

        status = result["status"]
        if status == "success":
            print(
                f"OK {result['fields_extracted']}/{result['total_fields']} fields "
                f"({result['unified_fields_extracted']}/{result['unified_fields_total']} unified)"
            )
        elif status == "failed":
            print(f"FAIL {result['error']}")
        else:
            print(f"ERROR: {result['error']}")

        results.append({"conference": conf_abbr, "year": year, **result})

    print()
    print("=" * 80)
    print("Summary")
    print("=" * 80)

    successful = [r for r in results if r["status"] == "success"]
    failed = [r for r in results if r["status"] == "failed"]
    errors = [r for r in results if r["status"] == "error"]

    total = len(results)
    print(f"Total conferences tested: {total}")
    print(f"  Successful: {len(successful)} ({len(successful) / total * 100:.1f}%)")
    print(f"  Failed: {len(failed)} ({len(failed) / total * 100:.1f}%)")
    print(f"  Errors: {len(errors)} ({len(errors) / total * 100:.1f}%)")

    if successful:
        avg_fields = sum(r["fields_extracted"] for r in successful) / len(successful)
        avg_unified = sum(r["unified_fields_extracted"] for r in successful) / len(
            successful
        )
        print(f"\nAverage fields extracted: {avg_fields:.1f}")
        print(f"Average unified fields extracted: {avg_unified:.1f}")

    if errors:
        print("\nErrors:")
        for r in errors:
            print(f"  - {r['conference'].upper()} {r['year']}: {r['error']}")

    print()
    print("=" * 80)

    tested_conferences = total - len(failed)
    if tested_conferences > 0:
        success_rate = len(successful) / tested_conferences * 100
        print(f"\nSuccess rate (excluding missing data): {success_rate:.1f}%")

    if not errors:
        print("PASS: No extraction errors")
        return 0

    if len(errors) / total <= 0.05:
        print(f"PASS WITH WARNINGS: {len(errors)} extraction errors")
        return 0

    print(f"FAIL: {len(errors)} extraction errors")
    return 1


if __name__ == "__main__":
    sys.exit(main())
