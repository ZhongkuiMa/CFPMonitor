"""Unified extraction schema design.

This module defines extraction schemas that support context preservation,
confidence scoring, and unified field concepts.
"""

from dataclasses import dataclass, field as dataclass_field
from enum import Enum


class ConfidenceLevel(str, Enum):
    """Confidence levels for extracted values."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class ExtractionResult:
    """Base class for extraction results.

    :ivar evidence: Matched text excerpt
    :ivar confidence: Extraction confidence level
    :ivar source: Extraction source (regex, ccfddl, wikicfp)
    """

    evidence: str = ""
    confidence: ConfidenceLevel = ConfidenceLevel.LOW
    source: str = "regex"


@dataclass
class PageExclusion:
    """Individual page exclusion.

    :ivar type: Exclusion type (references, appendices, acknowledgments)
    :ivar limit: Exclusion limit (unlimited, N pages)
    """

    type: str = "unknown"
    limit: str = "unknown"


@dataclass
class PageRequirements(ExtractionResult):
    """Unified page requirements.

    Merges page_limit and page_limit_exclusions into single field.

    :ivar main_limit: Main page limit (e.g., "8 pages", "6-10 pages")
    :ivar exclusions: List of exclusions
    :ivar total_max: Computed total if exclusions are bounded
    :ivar paper_types: Different types (long, short) with their limits
    """

    main_limit: str = "unknown"
    exclusions: list[PageExclusion] = dataclass_field(default_factory=list)
    total_max: str | None = None
    paper_types: dict[str, str] = dataclass_field(default_factory=dict)

    def to_legacy_format(self) -> dict[str, dict]:
        """Convert to legacy split format.

        :returns: Dictionary with page_limit and page_limit_exclusions keys
        """
        exclusions_evidence = ""
        if self.exclusions:
            parts = []
            for excl in self.exclusions:
                if excl.limit == "unlimited":
                    parts.append(excl.type)
                else:
                    parts.append(f"{excl.type} (up to {excl.limit})")

            if len(parts) == 1:
                exclusions_evidence = f"{parts[0]} do not count toward page limit"
            elif len(parts) == 2:
                exclusions_evidence = (
                    f"{parts[0]} and {parts[1]} do not count toward page limit"
                )
            else:
                exclusions_evidence = f"{', '.join(parts[:-1])}, and {parts[-1]} do not count toward page limit"

        return {
            "page_limit": {
                "value": self.main_limit,
                "evidence": self.evidence,
                "category": "submission_requirements",
                "priority": "critical",
            },
            "page_limit_exclusions": {
                "value": len(self.exclusions) > 0,
                "evidence": exclusions_evidence,
                "category": "submission_requirements",
                "priority": "high",
            },
        }


@dataclass
class ReviewProcess(ExtractionResult):
    """Review process classification.

    Replaces double_blind, single_blind, and open_review booleans.

    :ivar keywords_found: All relevant phrases matched
    :ivar classification: Review mode (double_blind, single_blind, open_review, mixed, unknown)
    :ivar nuances: Exceptions or conditional policies
    :ivar rebuttal_policy: Whether rebuttal is allowed (allowed, not_allowed, unknown)
    :ivar desk_rejection_policy: Whether desk rejection is used (yes, no, unknown)
    :ivar reciprocal_review_required: Whether reciprocal review is required
    """

    keywords_found: list[str] = dataclass_field(default_factory=list)
    classification: str = "unknown"
    nuances: list[str] = dataclass_field(default_factory=list)
    rebuttal_policy: str = "unknown"
    desk_rejection_policy: str = "unknown"
    reciprocal_review_required: bool | str = "unknown"

    def to_legacy_format(self) -> dict[str, dict]:
        """Convert to legacy 3-boolean format plus extended fields.

        :returns: Dictionary with double_blind, single_blind, open_review, and extended review fields
        """
        if self.classification == "double_blind":
            double_blind, single_blind, open_review = True, False, False
        elif self.classification == "single_blind":
            double_blind, single_blind, open_review = False, True, False
        elif self.classification == "open_review":
            double_blind, single_blind, open_review = False, False, True
        elif self.classification == "mixed":
            double_blind = any("double" in kw.lower() for kw in self.keywords_found)
            single_blind = any("single" in kw.lower() for kw in self.keywords_found)
            open_review = any(
                "open" in kw.lower() or "public" in kw.lower()
                for kw in self.keywords_found
            )
        else:
            double_blind, single_blind, open_review = "unknown", "unknown", "unknown"

        result = {
            "double_blind": {
                "value": double_blind,
                "evidence": self.evidence
                if self.classification == "double_blind"
                else "",
                "category": "review_process",
                "priority": "critical",
            },
            "single_blind": {
                "value": single_blind,
                "evidence": self.evidence
                if self.classification == "single_blind"
                else "",
                "category": "review_process",
                "priority": "high",
            },
            "open_review": {
                "value": open_review,
                "evidence": self.evidence
                if self.classification == "open_review"
                else "",
                "category": "review_process",
                "priority": "high",
            },
        }

        if self.rebuttal_policy != "unknown":
            result["rebuttal_allowed"] = {
                "value": self.rebuttal_policy == "allowed",
                "evidence": self.evidence,
                "category": "review_process",
                "priority": "medium",
            }

        if self.desk_rejection_policy != "unknown":
            result["desk_rejection"] = {
                "value": self.desk_rejection_policy == "yes",
                "evidence": self.evidence,
                "category": "review_process",
                "priority": "medium",
            }

        if self.reciprocal_review_required != "unknown":
            result["reciprocal_review"] = {
                "value": self.reciprocal_review_required,
                "evidence": self.evidence,
                "category": "review_process",
                "priority": "low",
            }

        return result


@dataclass
class PolicyField(ExtractionResult):
    """Generic policy field with semantic categories.

    Used for artifact_evaluation, llm_policy, concurrent_submission, arxiv_preprint.

    :ivar value: Policy value (mandatory, optional, allowed, required_disclosure, forbidden, etc.)
    :ivar keywords_found: Matched keywords
    """

    value: str = "unknown"
    keywords_found: list[str] = dataclass_field(default_factory=list)

    def to_legacy_format(self, field_name: str) -> dict[str, dict]:
        """Convert to legacy format.

        :param field_name: Field name (e.g., artifact_evaluation, llm_policy)
        :returns: Dictionary with field_name key
        """
        if field_name in ["artifact_evaluation", "llm_policy", "statements"]:
            category, priority = "ethics_reproducibility", "high"
        elif field_name in ["concurrent_submission", "arxiv_preprint"]:
            category, priority = "publication_policies", "high"
        else:
            category, priority = "unknown", "medium"

        return {
            field_name: {
                "value": self.value,
                "evidence": self.evidence,
                "category": category,
                "priority": priority,
            }
        }


@dataclass
class StatementsRequired(ExtractionResult):
    """Statement requirements.

    Shows which statements are required instead of single boolean.

    :ivar types: Required statement types (ethics_statement, broader_impact, reproducibility_checklist)
    :ivar keywords_found: Matched keywords
    """

    types: list[str] = dataclass_field(default_factory=list)
    keywords_found: list[str] = dataclass_field(default_factory=list)

    def to_legacy_format(self) -> dict[str, dict]:
        """Convert to legacy format.

        :returns: Dictionary with statements key
        """
        value = True if self.types else "unknown"

        if self.types:
            statement_list = ", ".join(self.types)
            evidence_text = f"Required statements: {statement_list}. {self.evidence}"
        else:
            evidence_text = (
                ""
                if self.evidence == "No specific statement requirements mentioned"
                else self.evidence
            )

        return {
            "statements": {
                "value": value,
                "evidence": evidence_text,
                "category": "ethics_reproducibility",
                "priority": "high",
            }
        }


@dataclass
class SubmissionRequirements(ExtractionResult):
    """Submission requirements for templates and supplementary materials.

    :ivar template_required: Whether template is required
    :ivar template_details: Details about template (LaTeX, Word, specific format)
    :ivar supplementary_allowed: Whether supplementary materials are allowed
    :ivar supplementary_limits: Limits on supplementary materials (size, pages, etc.)
    """

    template_required: bool | str = "unknown"
    template_details: str = ""
    supplementary_allowed: bool | str = "unknown"
    supplementary_limits: str = ""

    def to_legacy_format(self) -> dict[str, dict]:
        """Convert to legacy format.

        :returns: Dictionary with template_required and supplementary_material keys
        """
        result = {}

        if self.template_required != "unknown":
            result["template_required"] = {
                "value": self.template_required,
                "evidence": self.template_details
                if self.template_details
                else self.evidence,
                "category": "submission_requirements",
                "priority": "high",
            }

        if self.supplementary_allowed != "unknown":
            evidence_text = self.evidence
            if self.supplementary_limits:
                evidence_text = (
                    f"{self.supplementary_limits}. {self.evidence}"
                    if self.evidence
                    else self.supplementary_limits
                )

            result["supplementary_material"] = {
                "value": self.supplementary_allowed,
                "evidence": evidence_text,
                "category": "submission_requirements",
                "priority": "medium",
            }

        return result


@dataclass
class ConferenceLogistics(ExtractionResult):
    """Conference logistics information.

    :ivar presentation_formats: List of presentation formats (oral, poster, virtual)
    :ivar financial_aid_available: Whether financial aid is available
    :ivar workshops_present: Whether workshops are mentioned
    :ivar conference_format: Conference format (in-person, virtual, hybrid)
    """

    presentation_formats: list[str] = dataclass_field(default_factory=list)
    financial_aid_available: bool | str = "unknown"
    workshops_present: bool | str = "unknown"
    conference_format: str = "unknown"

    def to_legacy_format(self) -> dict[str, dict]:
        """Convert to legacy format.

        :returns: Dictionary with presentation_format, financial_aid, workshops, and conference_format keys
        """
        result = {}

        if self.presentation_formats:
            formats_str = ", ".join(self.presentation_formats)
            result["presentation_format"] = {
                "value": formats_str,
                "evidence": self.evidence,
                "category": "conference_info",
                "priority": "medium",
            }

        if self.financial_aid_available != "unknown":
            result["financial_aid"] = {
                "value": self.financial_aid_available,
                "evidence": self.evidence,
                "category": "conference_info",
                "priority": "low",
            }

        if self.workshops_present != "unknown":
            result["workshops"] = {
                "value": self.workshops_present,
                "evidence": self.evidence,
                "category": "conference_info",
                "priority": "low",
            }

        if self.conference_format != "unknown":
            result["conference_format"] = {
                "value": self.conference_format,
                "evidence": self.evidence,
                "category": "conference_info",
                "priority": "high",
            }

        return result


@dataclass
class TrackDetection(ExtractionResult):
    """Track and event detection results.

    :ivar has_workshop_proposals: Whether conference solicits workshop proposals
    :ivar has_tutorials: Whether conference has a tutorials track
    :ivar has_demos: Whether conference has a demo/system demonstrations track
    :ivar has_posters: Whether conference has a dedicated poster submission track
    :ivar has_industry_track: Whether conference has an industry/applications track
    :ivar has_position_papers: Whether conference accepts position/opinion papers
    :ivar has_student_research: Whether conference has a student research workshop/competition
    :ivar has_doctoral_consortium: Whether conference has a doctoral consortium/symposium
    :ivar has_findings: Whether conference has a Findings track (ACL-family venues)
    :ivar has_awards: Whether conference mentions best paper or other awards
    """

    has_workshop_proposals: bool | str = "unknown"
    has_tutorials: bool | str = "unknown"
    has_demos: bool | str = "unknown"
    has_posters: bool | str = "unknown"
    has_industry_track: bool | str = "unknown"
    has_position_papers: bool | str = "unknown"
    has_student_research: bool | str = "unknown"
    has_doctoral_consortium: bool | str = "unknown"
    has_findings: bool | str = "unknown"
    has_awards: bool | str = "unknown"

    def to_legacy_format(self) -> dict[str, dict]:
        """Convert to legacy format.

        :returns: Dictionary with has_* keys for detected tracks
        """
        result = {}
        fields = [
            "has_workshop_proposals",
            "has_tutorials",
            "has_demos",
            "has_posters",
            "has_industry_track",
            "has_position_papers",
            "has_student_research",
            "has_doctoral_consortium",
            "has_findings",
            "has_awards",
        ]
        for field_name in fields:
            value = getattr(self, field_name)
            if value != "unknown":
                result[field_name] = {
                    "value": value,
                    "evidence": self.evidence,
                    "category": "tracks_and_events",
                    "priority": "low",
                }
        return result
