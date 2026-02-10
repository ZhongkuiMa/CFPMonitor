"""Test policy extractors with backward compatibility.

This tests the unified policy extractors:
- extract_policy_field (artifact_evaluation, llm_policy, concurrent_submission, arxiv_preprint)
- extract_statements_required (ethics, impact, reproducibility, etc.)

Run: python -m src.investigation.test_policy_extractors
"""

from src.extractor.unified_extractors import (
    extract_policy_field,
    extract_statements_required,
)


def test_artifact_evaluation():
    """Test artifact evaluation extractor.

    :returns: True if all tests pass, False otherwise
    """
    print("=" * 80)
    print("TEST: Artifact Evaluation Extractor")
    print("=" * 80)

    test_cases = [
        {
            "name": "Required artifacts",
            "text": """
            Artifact Evaluation
            Authors are required to submit artifacts for evaluation.
            All papers must include code and data to be considered for publication.
            """,
            "expected": "required",
        },
        {
            "name": "Optional artifacts",
            "text": """
            Authors may optionally submit artifacts for evaluation.
            Artifact submission is voluntary but encouraged.
            """,
            "expected": "optional",
        },
        {
            "name": "Encouraged artifacts",
            "text": """
            We strongly encourage authors to submit artifacts.
            Artifact evaluation is recommended to increase reproducibility.
            """,
            "expected": "encouraged",
        },
        {
            "name": "No mention",
            "text": """
            Papers should be submitted in PDF format.
            The review process is double-blind.
            """,
            "expected": "not_mentioned",
        },
    ]

    passed = 0
    total = len(test_cases)

    for i, test in enumerate(test_cases, 1):
        print(f"\n{i}. {test['name']}")
        print(f"   Text: {test['text'][:80]}...")

        result = extract_policy_field(test["text"], "artifact_evaluation")

        print(f"   Classification: {result.value}")
        print(f"   Confidence: {result.confidence.value}")
        print(f"   Evidence: {result.evidence[:100]}...")

        # Test backward compatibility
        legacy = result.to_legacy_format("artifact_evaluation")
        print(f"   Legacy value: {legacy['artifact_evaluation']['value']}")

        if result.value == test["expected"]:
            print("   PASS PASS")
            passed += 1
        else:
            print(f"   FAIL FAIL - Expected: {test['expected']}, Got: {result.value}")

    print(f"\n{'=' * 80}")
    print(f"Results: {passed}/{total} tests passed ({passed / total * 100:.1f}%)")
    return passed == total


def test_llm_policy():
    """Test LLM policy extractor.

    :returns: True if all tests pass, False otherwise
    """
    print("\n" + "=" * 80)
    print("TEST: LLM Policy Extractor")
    print("=" * 80)

    test_cases = [
        {
            "name": "LLM allowed",
            "text": """
            Use of AI Tools
            Authors may use large language models (LLMs) such as ChatGPT to assist
            with writing, but must disclose their use in the acknowledgments.
            """,
            "expected": "allowed_with_disclosure",
        },
        {
            "name": "LLM prohibited",
            "text": """
            The use of AI-generated text is prohibited.
            Papers found to contain ChatGPT or other LLM-generated content will be rejected.
            """,
            "expected": "prohibited",
        },
        {
            "name": "LLM discouraged",
            "text": """
            We discourage the use of large language models for writing papers.
            While not explicitly prohibited, reviewers will be looking for AI-generated content.
            """,
            "expected": "discouraged",
        },
        {
            "name": "No mention",
            "text": """
            Papers should follow the template provided.
            Citations should use the provided BibTeX style.
            """,
            "expected": "not_mentioned",
        },
    ]

    passed = 0
    total = len(test_cases)

    for i, test in enumerate(test_cases, 1):
        print(f"\n{i}. {test['name']}")
        print(f"   Text: {test['text'][:80]}...")

        result = extract_policy_field(test["text"], "llm_policy")

        print(f"   Classification: {result.value}")
        print(f"   Confidence: {result.confidence.value}")
        print(
            f"   Evidence: {result.evidence[:100]}..."
            if result.evidence
            else "   Evidence: (none)"
        )

        # Test backward compatibility
        legacy = result.to_legacy_format("llm_policy")
        print(f"   Legacy value: {legacy['llm_policy']['value']}")

        if result.value == test["expected"]:
            print("   PASS PASS")
            passed += 1
        else:
            print(f"   FAIL FAIL - Expected: {test['expected']}, Got: {result.value}")

    print(f"\n{'=' * 80}")
    print(f"Results: {passed}/{total} tests passed ({passed / total * 100:.1f}%)")
    return passed == total


def test_statements_required():
    """Test statements required extractor.

    :returns: True if all tests pass, False otherwise
    """
    print("\n" + "=" * 80)
    print("TEST: Statements Required Extractor")
    print("=" * 80)

    test_cases = [
        {
            "name": "Ethics statement required",
            "text": """
            Required Statements
            All papers must include an ethics statement discussing potential
            societal impacts of the research.
            """,
            "expected_types": ["ethics_statement"],
        },
        {
            "name": "Multiple statements",
            "text": """
            Papers must include:
            - Ethics statement
            - Broader impact section
            - Reproducibility checklist

            These are mandatory for all submissions.
            """,
            "expected_types": [
                "ethics_statement",
                "broader_impact",
                "reproducibility_checklist",
            ],
        },
        {
            "name": "Impact statement",
            "text": """
            Authors should discuss the broader impacts of their work.
            A dedicated impact statement section is required.
            """,
            "expected_types": ["broader_impact"],
        },
        {
            "name": "No statements",
            "text": """
            Papers should be submitted in PDF format.
            Maximum length is 8 pages.
            """,
            "expected_types": [],
        },
    ]

    passed = 0
    total = len(test_cases)

    for i, test in enumerate(test_cases, 1):
        print(f"\n{i}. {test['name']}")
        print(f"   Text: {test['text'][:80]}...")

        result = extract_statements_required(test["text"])

        print(f"   Types found: {result.types}")
        print(f"   Confidence: {result.confidence.value}")
        print(
            f"   Evidence: {result.evidence[:100]}..."
            if result.evidence
            else "   Evidence: (none)"
        )

        # Test backward compatibility
        legacy = result.to_legacy_format()
        print(f"   Legacy value: {legacy['statements']['value']}")

        # Check if expected types are found (order doesn't matter)
        found_all = all(t in result.types for t in test["expected_types"])
        no_extra = all(t in test["expected_types"] for t in result.types)

        if found_all and no_extra:
            print("   PASS PASS")
            passed += 1
        else:
            print(
                f"   FAIL FAIL - Expected: {test['expected_types']}, Got: {result.types}"
            )

    print(f"\n{'=' * 80}")
    print(f"Results: {passed}/{total} tests passed ({passed / total * 100:.1f}%)")
    return passed == total


def test_concurrent_submission():
    """Test concurrent submission policy extractor.

    :returns: True if all tests pass, False otherwise
    """
    print("\n" + "=" * 80)
    print("TEST: Concurrent Submission Policy Extractor")
    print("=" * 80)

    test_cases = [
        {
            "name": "Not allowed",
            "text": """
            Concurrent Submissions
            Papers under review at other venues will be rejected without review.
            Simultaneous submission to multiple conferences is not permitted.
            """,
            "expected": "not_allowed",
        },
        {
            "name": "Allowed",
            "text": """
            Authors may submit their work to other venues concurrently.
            Parallel submissions are permitted.
            """,
            "expected": "allowed",
        },
        {
            "name": "No mention",
            "text": """
            Papers should be original work.
            Previously published papers will not be considered.
            """,
            "expected": "not_mentioned",
        },
    ]

    passed = 0
    total = len(test_cases)

    for i, test in enumerate(test_cases, 1):
        print(f"\n{i}. {test['name']}")
        print(f"   Text: {test['text'][:80]}...")

        result = extract_policy_field(test["text"], "concurrent_submission")

        print(f"   Classification: {result.value}")
        print(f"   Confidence: {result.confidence.value}")

        # Test backward compatibility
        legacy = result.to_legacy_format("concurrent_submission")
        print(f"   Legacy value: {legacy['concurrent_submission']['value']}")

        if result.value == test["expected"]:
            print("   PASS PASS")
            passed += 1
        else:
            print(f"   FAIL FAIL - Expected: {test['expected']}, Got: {result.value}")

    print(f"\n{'=' * 80}")
    print(f"Results: {passed}/{total} tests passed ({passed / total * 100:.1f}%)")
    return passed == total


def main():
    """Run all policy extractor tests.

    :returns: True if all tests pass, False otherwise
    """
    print("=" * 80)
    print("POLICY EXTRACTORS TEST SUITE")
    print("=" * 80)
    print("\nTesting unified policy extractors with backward compatibility...\n")

    results = {
        "artifact_evaluation": test_artifact_evaluation(),
        "llm_policy": test_llm_policy(),
        "statements_required": test_statements_required(),
        "concurrent_submission": test_concurrent_submission(),
    }

    # Overall summary
    print("\n" + "=" * 80)
    print("OVERALL TEST SUMMARY")
    print("=" * 80)

    passed_count = sum(1 for v in results.values() if v)
    total_count = len(results)

    for name, passed in results.items():
        status = "PASS PASS" if passed else "FAIL FAIL"
        print(f"  {status} - {name}")

    print(f"\n{'=' * 80}")
    print(
        f"Overall: {passed_count}/{total_count} test suites passed ({passed_count / total_count * 100:.1f}%)"
    )

    if passed_count == total_count:
        print("\n All policy extractors working correctly!")
        print("PASS Backward compatibility verified")
        print("\nNext steps:")
        print("  1. Test on real conference data")
        print("  2. Integrate into main extraction pipeline")
        print("  3. Run full dataset validation")
    else:
        print(
            f"\nWARNING  {total_count - passed_count} test suite(s) failed - review implementation"
        )

    return passed_count == total_count


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
