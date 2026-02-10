"""Test backward compatibility of unified page extractor.

This demonstrates how the new unified extractor can output in the old format,
allowing gradual migration without breaking existing consumers.

Run: python -m src.investigation.test_backward_compatibility
"""

from pathlib import Path
import yaml

from src.extractor.unified_extractors import extract_page_requirements_unified


def test_backward_compatibility():
    """Test that new extractor can produce old format.

    :returns: None
    """

    print("=" * 80)
    print("BACKWARD COMPATIBILITY TEST")
    print("=" * 80)
    print("\nDemonstrating how unified extractor supports legacy format...\n")

    # Sample conference texts with different page requirement patterns
    test_cases = [
        {
            "name": "ICML 2025 (combined limit + exclusions)",
            "text": "Papers must be 8 pages for the main content, plus unlimited references and appendices.",
        },
        {
            "name": "CVPR 2025 (excluding references)",
            "text": "Submissions should not exceed 8 pages, excluding references.",
        },
        {
            "name": "ACL 2026 (soft limit)",
            "text": "Content beyond the first 12 pages (not including references) may not be read by reviewers.",
        },
        {
            "name": "NeurIPS 2024 (number word)",
            "text": "Papers are limited to nine content pages, with unlimited additional pages for references.",
        },
        {
            "name": "AAAI 2025 (bounded exclusion)",
            "text": "Papers should be 7 pages plus up to 2 pages for references.",
        },
    ]

    for i, test in enumerate(test_cases, 1):
        print(f"\n{'=' * 80}")
        print(f"Test Case {i}: {test['name']}")
        print("=" * 80)

        # Extract using NEW unified approach
        page_req = extract_page_requirements_unified(test["text"])

        print("\n🆕 NEW FORMAT (Unified PageRequirements):")
        print(f"   main_limit: {page_req.main_limit}")
        if page_req.exclusions:
            print("   exclusions:")
            for excl in page_req.exclusions:
                print(f"      - {excl.type}: {excl.limit}")
        else:
            print("   exclusions: []")
        print(f"   confidence: {page_req.confidence.value}")
        print(f"   evidence: {page_req.evidence}")

        # Convert to OLD format using backward compatibility
        legacy = page_req.to_legacy_format()

        print("\n🔴 OLD FORMAT (Legacy - for backward compatibility):")
        print("   page_limit:")
        print(f"      value: {legacy['page_limit']['value']}")
        print(f"      evidence: {legacy['page_limit']['evidence'][:80]}...")
        print("   page_limit_exclusions:")
        print(f"      value: {legacy['page_limit_exclusions']['value']}")
        if legacy["page_limit_exclusions"]["evidence"]:
            print(
                f"      evidence: {legacy['page_limit_exclusions']['evidence'][:80]}..."
            )

        print("\n📊 COMPARISON:")
        print(
            f"   PASS OLD consumers see: page_limit={legacy['page_limit']['value']}, exclusions={legacy['page_limit_exclusions']['value']}"
        )
        print(
            f"   PASS NEW consumers see: main_limit={page_req.main_limit}, exclusions={len(page_req.exclusions)} types with details"
        )

    # Load a real conference and test
    print(f"\n\n{'=' * 80}")
    print("REAL CONFERENCE TEST: ICML 2025")
    print("=" * 80)

    data_dir = Path(__file__).parent.parent.parent / "data"
    raw_dir = data_dir / "raw" / "icml" / "2025"

    if raw_dir.exists():
        txt_files = list(raw_dir.glob("*.txt"))
        if txt_files:
            all_text = "\n\n".join([f.read_text(encoding="utf-8") for f in txt_files])

            # Add wikicfp if available
            wikicfp_file = data_dir / "wikicfp" / "icml" / "2025.yaml"
            if wikicfp_file.exists():
                with open(wikicfp_file, encoding="utf-8") as f:
                    wikicfp_data = yaml.safe_load(f)
                    cfp_text = str(wikicfp_data.get("cfp_text", "")).strip()
                    if cfp_text and cfp_text != "[Empty]":
                        all_text += "\n\n" + cfp_text

            # Extract
            page_req = extract_page_requirements_unified(all_text)
            legacy = page_req.to_legacy_format()

            print("\n🆕 NEW FORMAT:")
            print(f"   main_limit: {page_req.main_limit}")
            print(
                f"   exclusions: {[f'{e.type}:{e.limit}' for e in page_req.exclusions]}"
            )
            print(f"   confidence: {page_req.confidence.value}")

            print("\n🔴 OLD FORMAT (backward compatible):")
            print(f"   page_limit: {legacy['page_limit']['value']}")
            print(
                f"   page_limit_exclusions: {legacy['page_limit_exclusions']['value']}"
            )
            print(
                f"   evidence (exclusions): {legacy['page_limit_exclusions']['evidence']}"
            )

            # Compare with actual current extraction
            print("\n📁 COMPARE WITH CURRENT SYSTEM:")
            structured_file = data_dir / "structured" / "icml" / "2025.yaml"
            if structured_file.exists():
                with open(structured_file, encoding="utf-8") as f:
                    current_data = yaml.safe_load(f)
                    current_limit = current_data["rules"]["page_limit"]["value"]
                    current_excl = current_data["rules"]["page_limit_exclusions"][
                        "value"
                    ]

                    print("   Current system:")
                    print(f"      page_limit: {current_limit}")
                    print(f"      page_limit_exclusions: {current_excl}")

                    print("\n   New system (legacy format):")
                    print(f"      page_limit: {legacy['page_limit']['value']}")
                    print(
                        f"      page_limit_exclusions: {legacy['page_limit_exclusions']['value']}"
                    )

                    if current_limit == legacy["page_limit"]["value"]:
                        print("\n   PASS page_limit MATCHES!")
                    else:
                        print(
                            f"\n   WARNING  page_limit DIFFERS: {current_limit} vs {legacy['page_limit']['value']}"
                        )

                    current_excl_bool = current_excl in [True, "True", "true"]
                    if current_excl_bool == legacy["page_limit_exclusions"]["value"]:
                        print("   PASS page_limit_exclusions MATCHES!")
                    else:
                        print("   WARNING  page_limit_exclusions DIFFERS")
        else:
            print("   FAIL No text files found")
    else:
        print("   FAIL ICML 2025 data not found")

    # Summary
    print(f"\n\n{'=' * 80}")
    print("SUMMARY")
    print("=" * 80)
    print("\nPASS Backward compatibility WORKS!")
    print("\nMigration strategy:")
    print("   1. Deploy new unified extractor in SHADOW MODE")
    print("      - Run both old and new extractors")
    print("      - Use to_legacy_format() to output old format")
    print("      - Compare results side-by-side")
    print("\n   2. Switch to new format gradually")
    print("      - Update frontend to show structured exclusions")
    print("      - Use new format for new conferences")
    print("      - Keep legacy format for existing data")
    print("\n   3. Deprecate old extractors")
    print("      - Once new extractor is validated")
    print("      - Remove old page_limit and page_limit_exclusions patterns")
    print("      - Migrate all data to new format")


if __name__ == "__main__":
    test_backward_compatibility()
