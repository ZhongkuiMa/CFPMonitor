"""Test all unified extractors on full dataset.

Run all 3 unified extractors on 665 conferences:
- PageRequirements
- ReviewProcess
- Policy Fields (artifact_evaluation, llm_policy, statements, concurrent_submission)

Run: python -m src.investigation.test_all_unified_extractors
"""

from pathlib import Path
import yaml
from collections import defaultdict
import time

from src.extractor.extractor import extract_rules
from src.extractor.unified_extractors import (
    extract_page_requirements_unified,
    extract_review_process_keywords,
    extract_policy_field,
    extract_statements_required,
)


def load_all_conferences() -> list[dict]:
    """Load all conferences from data/raw/.

    :returns: List of conference dictionaries
    """
    conferences = []
    data_dir = Path(__file__).parent.parent.parent / "data"
    raw_dir = data_dir / "raw"

    for conf_dir in sorted(raw_dir.iterdir()):
        if not conf_dir.is_dir():
            continue

        conf_abbr = conf_dir.name

        for year_dir in sorted(conf_dir.iterdir()):
            if not year_dir.is_dir():
                continue

            try:
                year = int(year_dir.name)
            except ValueError:
                continue

            txt_files = list(year_dir.glob("*.txt"))
            if not txt_files:
                continue

            all_text = "\n\n".join([f.read_text(encoding="utf-8") for f in txt_files])

            wikicfp_file = data_dir / "wikicfp" / conf_abbr / f"{year}.yaml"
            if wikicfp_file.exists():
                with open(wikicfp_file, encoding="utf-8") as f:
                    wikicfp_data = yaml.safe_load(f)
                    cfp_text = str(wikicfp_data.get("cfp_text", "")).strip()
                    if cfp_text and cfp_text != "[Empty]":
                        all_text += "\n\n" + cfp_text

            conferences.append(
                {
                    "name": f"{conf_abbr.upper()} {year}",
                    "abbr": conf_abbr,
                    "year": year,
                    "text": all_text,
                }
            )

    return conferences


def test_conference(conf: dict, data_dir: str) -> dict:
    """Test all unified extractors on single conference.

    :param conf: Conference dictionary
    :param data_dir: Data directory path
    :returns: Test result dictionary
    """
    abbr = conf["abbr"]
    year = conf["year"]
    text = conf["text"]

    old_result = extract_rules(abbr, year, str(data_dir))
    old_rules = old_result.get("rules", {})

    page_req = extract_page_requirements_unified(text)
    review_proc = extract_review_process_keywords(text)
    artifact_eval = extract_policy_field(text, "artifact_evaluation")
    llm_policy = extract_policy_field(text, "llm_policy")
    concurrent_sub = extract_policy_field(text, "concurrent_submission")
    statements = extract_statements_required(text)

    return {
        "name": conf["name"],
        "abbr": abbr,
        "year": year,
        "text_length": len(text),
        "old": {
            "page_limit": old_rules.get("page_limit", {}).get("value", "unknown"),
            "page_limit_exclusions": old_rules.get("page_limit_exclusions", {}).get(
                "value", "unknown"
            ),
            "double_blind": old_rules.get("double_blind", {}).get("value", "unknown"),
            "single_blind": old_rules.get("single_blind", {}).get("value", "unknown"),
            "open_review": old_rules.get("open_review", {}).get("value", "unknown"),
        },
        "new": {
            "page_requirements": {
                "main_limit": page_req.main_limit,
                "exclusions_count": len(page_req.exclusions),
                "confidence": page_req.confidence.value,
            },
            "review_process": {
                "classification": review_proc.classification,
                "confidence": review_proc.confidence.value,
                "nuances_count": len(review_proc.nuances),
            },
            "artifact_evaluation": {
                "value": artifact_eval.value,
                "confidence": artifact_eval.confidence.value,
            },
            "llm_policy": {
                "value": llm_policy.value,
                "confidence": llm_policy.confidence.value,
            },
            "concurrent_submission": {
                "value": concurrent_sub.value,
                "confidence": concurrent_sub.confidence.value,
            },
            "statements": {
                "types": statements.types,
                "count": len(statements.types),
                "confidence": statements.confidence.value,
            },
        },
        "success": True,
    }


def main():
    """Run full dataset validation."""
    print("=" * 80)
    print("UNIFIED EXTRACTORS - FULL DATASET VALIDATION")
    print("=" * 80)
    print("\nLoading all conferences from data/raw/...")

    conferences = load_all_conferences()
    total = len(conferences)
    data_dir = Path(__file__).parent.parent.parent / "data"

    print(f"Found {total} conferences to test")
    print("\nTesting all 3 unified extractors on full dataset...")
    print("This may take several minutes...\n")

    results = []
    stats = {
        "page_requirements": defaultdict(int),
        "review_process": defaultdict(int),
        "artifact_evaluation": defaultdict(int),
        "llm_policy": defaultdict(int),
        "concurrent_submission": defaultdict(int),
        "statements_count": defaultdict(int),
        "confidence": {
            "page": defaultdict(int),
            "review": defaultdict(int),
        },
    }

    start_time = time.time()

    for i, conf in enumerate(conferences, 1):
        if i % 50 == 0:
            elapsed = time.time() - start_time
            per_conf = elapsed / i
            remaining = (total - i) * per_conf
            print(
                f"  Progress: {i}/{total} ({i / total * 100:.1f}%) - Est. {remaining / 60:.1f} min remaining"
            )

        result = test_conference(conf, str(data_dir))
        results.append(result)

        if not result.get("success", False):
            continue

        new = result["new"]

        if new["page_requirements"]["main_limit"] != "unknown":
            stats["page_requirements"]["found"] += 1
        else:
            stats["page_requirements"]["not_found"] += 1
        stats["confidence"]["page"][new["page_requirements"]["confidence"]] += 1

        if new["review_process"]["classification"] != "unknown":
            stats["review_process"][new["review_process"]["classification"]] += 1
        else:
            stats["review_process"]["unknown"] += 1
        stats["confidence"]["review"][new["review_process"]["confidence"]] += 1

        stats["artifact_evaluation"][new["artifact_evaluation"]["value"]] += 1
        stats["llm_policy"][new["llm_policy"]["value"]] += 1
        stats["concurrent_submission"][new["concurrent_submission"]["value"]] += 1

        stmt_count = new["statements"]["count"]
        stats["statements_count"][stmt_count if stmt_count > 0 else 0] += 1

    elapsed = time.time() - start_time
    tested = len([r for r in results if r.get("success", False)])

    print(f"\n{'=' * 80}")
    print(
        f"Testing complete! Processed {tested} conferences in {elapsed / 60:.1f} minutes"
    )
    print(f"Average: {elapsed / tested:.2f} seconds per conference")

    print("\n" + "=" * 80)
    print("EXTRACTION RESULTS")
    print("=" * 80)

    print("\nPage Requirements:")
    found = stats["page_requirements"]["found"]
    not_found = stats["page_requirements"]["not_found"]
    total_valid = found + not_found
    print(f"   Found: {found}/{total_valid} ({found / total_valid * 100:.1f}%)")
    print("   Confidence distribution:")
    for conf_level in ["high", "medium", "low"]:
        count = stats["confidence"]["page"][conf_level]
        print(f"      {conf_level:8}: {count:4} ({count / total_valid * 100:5.1f}%)")

    print("\nReview Process:")
    for mode in ["double_blind", "single_blind", "open_review", "unknown"]:
        count = stats["review_process"][mode]
        print(f"   {mode:15}: {count:4} ({count / tested * 100:5.1f}%)")
    total_found = sum(
        stats["review_process"][m]
        for m in ["double_blind", "single_blind", "open_review"]
    )
    print(f"   TOTAL FOUND:    {total_found:4} ({total_found / tested * 100:5.1f}%)")
    print("   Confidence distribution:")
    for conf_level in ["high", "medium", "low"]:
        count = stats["confidence"]["review"][conf_level]
        print(f"      {conf_level:8}: {count:4} ({count / tested * 100:5.1f}%)")

    print("\nArtifact Evaluation:")
    for value in ["required", "optional", "encouraged", "not_mentioned"]:
        count = stats["artifact_evaluation"][value]
        if count > 0:
            print(f"   {value:15}: {count:4} ({count / tested * 100:5.1f}%)")

    print("\nLLM Policy:")
    for value in [
        "prohibited",
        "allowed",
        "discouraged",
        "allowed_with_disclosure",
        "not_mentioned",
    ]:
        count = stats["llm_policy"][value]
        if count > 0:
            print(f"   {value:25}: {count:4} ({count / tested * 100:5.1f}%)")

    print("\nConcurrent Submission:")
    for value in ["not_allowed", "allowed", "not_mentioned"]:
        count = stats["concurrent_submission"][value]
        if count > 0:
            print(f"   {value:15}: {count:4} ({count / tested * 100:5.1f}%)")

    print("\nStatements Required:")
    total_with_statements = sum(
        count
        for stmt_count, count in stats["statements_count"].items()
        if stmt_count > 0
    )
    print(
        f"   Conferences with statements: {total_with_statements}/{tested} ({total_with_statements / tested * 100:.1f}%)"
    )
    print("   Distribution:")
    for stmt_count in sorted(stats["statements_count"].keys()):
        count = stats["statements_count"][stmt_count]
        if stmt_count == 0:
            print(f"      No statements: {count:4} ({count / tested * 100:5.1f}%)")
        else:
            print(
                f"      {stmt_count} statement(s): {count:4} ({count / tested * 100:5.1f}%)"
            )

    print("\n" + "=" * 80)
    print("OVERALL SUMMARY")
    print("=" * 80)

    conferences_with_policies = sum(
        1
        for r in results
        if r.get("success")
        and (
            r["new"]["page_requirements"]["main_limit"] != "unknown"
            or r["new"]["review_process"]["classification"] != "unknown"
            or r["new"]["artifact_evaluation"]["value"] != "not_mentioned"
            or r["new"]["llm_policy"]["value"] != "not_mentioned"
            or r["new"]["concurrent_submission"]["value"] != "not_mentioned"
            or r["new"]["statements"]["count"] > 0
        )
    )

    print(f"\nConferences tested: {tested}")
    print(
        f"Conferences with at least one extraction: {conferences_with_policies} ({conferences_with_policies / tested * 100:.1f}%)"
    )

    page_coverage = stats["page_requirements"]["found"]
    review_coverage = total_found
    artifact_coverage = sum(
        stats["artifact_evaluation"][v] for v in ["required", "optional", "encouraged"]
    )
    llm_coverage = sum(
        stats["llm_policy"][v]
        for v in ["prohibited", "allowed", "discouraged", "allowed_with_disclosure"]
    )
    concurrent_coverage = sum(
        stats["concurrent_submission"][v] for v in ["not_allowed", "allowed"]
    )
    statements_coverage = total_with_statements

    print("\nField coverage:")
    print(
        f"   Page requirements:     {page_coverage:4}/{tested} ({page_coverage / tested * 100:5.1f}%)"
    )
    print(
        f"   Review process:        {review_coverage:4}/{tested} ({review_coverage / tested * 100:5.1f}%)"
    )
    print(
        f"   Artifact evaluation:   {artifact_coverage:4}/{tested} ({artifact_coverage / tested * 100:5.1f}%)"
    )
    print(
        f"   LLM policy:            {llm_coverage:4}/{tested} ({llm_coverage / tested * 100:5.1f}%)"
    )
    print(
        f"   Concurrent submission: {concurrent_coverage:4}/{tested} ({concurrent_coverage / tested * 100:5.1f}%)"
    )
    print(
        f"   Statements:            {statements_coverage:4}/{tested} ({statements_coverage / tested * 100:5.1f}%)"
    )

    output_file = (
        Path(__file__).parent.parent.parent
        / "data"
        / "investigation"
        / "all_unified_extractors_results.yaml"
    )
    output_file.parent.mkdir(parents=True, exist_ok=True)

    summary_data = {
        "summary": {
            "total_conferences": tested,
            "conferences_with_policies": conferences_with_policies,
            "coverage_pct": conferences_with_policies / tested * 100,
            "avg_time_per_conference": elapsed / tested,
        },
        "coverage": {
            "page_requirements": page_coverage,
            "review_process": review_coverage,
            "artifact_evaluation": artifact_coverage,
            "llm_policy": llm_coverage,
            "concurrent_submission": concurrent_coverage,
            "statements": statements_coverage,
        },
        "stats": {
            "page_requirements": dict(stats["page_requirements"]),
            "review_process": dict(stats["review_process"]),
            "artifact_evaluation": dict(stats["artifact_evaluation"]),
            "llm_policy": dict(stats["llm_policy"]),
            "concurrent_submission": dict(stats["concurrent_submission"]),
            "statements_count": dict(stats["statements_count"]),
            "confidence": {
                "page": dict(stats["confidence"]["page"]),
                "review": dict(stats["confidence"]["review"]),
            },
        },
    }

    with open(output_file, "w", encoding="utf-8") as f:
        yaml.dump(summary_data, f, default_flow_style=False)

    print(f"\nDetailed results saved to: {output_file}")

    print("\n" + "=" * 80)
    print("FINAL ASSESSMENT")
    print("=" * 80)

    avg_coverage = (
        (
            page_coverage / tested
            + review_coverage / tested
            + artifact_coverage / tested
            + llm_coverage / tested
            + concurrent_coverage / tested
            + statements_coverage / tested
        )
        / 6
        * 100
    )

    print(f"\nAverage field coverage: {avg_coverage:.1f}%")

    if avg_coverage >= 60:
        print("EXCELLENT - High extraction coverage across all fields")
    elif avg_coverage >= 45:
        print("GOOD - Solid extraction coverage")
    elif avg_coverage >= 30:
        print("FAIR - Moderate extraction coverage")
    else:
        print("NEEDS WORK - Low extraction coverage")

    print(f"\nAll 3 unified extractors tested successfully on {tested} conferences!")
    print(f"Processing time: {elapsed / 60:.1f} minutes")
    print(f"Average: {elapsed / tested:.2f} seconds per conference")


if __name__ == "__main__":
    main()
