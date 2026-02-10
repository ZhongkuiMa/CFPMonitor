#!/usr/bin/env python3
"""Generate JavaScript rule definitions from fields.yaml."""

from pathlib import Path

import yaml

SEMANTIC_LABELS = {
    "submission_system": "Submission System",
    "lay_summary_required": "Lay Summary",
    "open_review": "Open Review",
    "single_blind": "Single-Blind Review",
    "double_blind": "Double-Blind Review",
    "reciprocal_review": "Reciprocal Review",
    "rebuttal_allowed": "Rebuttal Allowed",
    "desk_rejection": "Desk Rejection",
    "page_limit": "Page Limit",
    "page_limit_exclusions": "Page Limit Exclusions",
    "template_required": "Template Required",
    "supplementary_material_allowed": "Supplementary Material",
    "artifact_evaluation": "Artifact Evaluation",
    "llm_policy": "LLM Policy",
    "concurrent_submission": "Concurrent Submission",
    "arxiv_preprint": "arXiv Preprint",
    "conference_format": "Conference Format",
    "presentation_formats": "Presentation Formats",
    "financial_aid_available": "Financial Aid",
    "workshops": "Workshops",
    "has_workshop_proposals": "Workshop Proposals",
    "has_tutorials": "Tutorials",
    "has_demos": "Demos",
    "has_posters": "Poster Track",
    "has_industry_track": "Industry Track",
    "has_position_papers": "Position Papers",
    "has_student_research": "Student Research",
    "has_doctoral_consortium": "Doctoral Consortium",
    "has_findings": "Findings Track",
    "has_awards": "Awards",
}

CATEGORY_ICONS = {
    "deadlines": "\U0001f4c5",
    "review_process": "\U0001f465",
    "submission_requirements": "\U0001f4c4",
    "publication_policies": "\U0001f4cb",
    "ethics_reproducibility": "\u2696\ufe0f",
    "conference_logistics": "\U0001f3db\ufe0f",
    "publication_details": "\U0001f4f0",
    "tracks_and_events": "\U0001f3af",
}

FIELD_ICONS = {
    "double_blind": "\U0001f441\ufe0f",
    "arxiv": "\U0001f4da",
    "preprint": "\U0001f4da",
    "code": "\U0001f4bb",
    "artifact": "\U0001f4bb",
    "ethics": "\u2696\ufe0f",
    "llm": "\U0001f916",
    "rebuttal": "\U0001f4ac",
    "venue": "\U0001f3db\ufe0f",
}

TYPE_ICONS = {
    "date": "\U0001f4c5",
    "boolean": "\u2713",
}


def get_icon_for_field(field_name: str, category: str, field_type: str) -> str:
    """Determine icon for field.

    :param field_name: Field name
    :param category: Field category
    :param field_type: Field type
    :return: Icon string
    """
    for key, icon in FIELD_ICONS.items():
        if key in field_name.lower():
            return icon

    if field_type in TYPE_ICONS:
        return TYPE_ICONS[field_type]

    return CATEGORY_ICONS.get(category, "\u2753")


def generate_rule_definitions() -> str:
    """Generate RULE_DEFINITIONS JavaScript from fields.yaml.

    :return: JavaScript code
    """
    fields_path = Path("src/extractor/fields.yaml")
    with open(fields_path) as f:
        fields = yaml.safe_load(f)

    lines = [
        "// AUTO-GENERATED from src/extractor/fields.yaml",
        "// DO NOT EDIT MANUALLY",
        "",
        "export const RULE_DEFINITIONS = {",
    ]

    for field_name, field_data in fields.items():
        category = field_data.get("category", "unknown")
        field_type = field_data.get("type", "string")
        priority = field_data.get("priority", "medium")
        description = (
            field_data.get("description", "")
            .replace("\\", "\\\\")
            .replace("'", "\\'")
            .replace("\n", "\\n")
        )
        icon = get_icon_for_field(field_name, category, field_type)
        label = SEMANTIC_LABELS.get(field_name) or field_name.replace("_", " ").title()

        lines.extend(
            [
                f"    {field_name}: {{",
                f"        label: '{label}',",
                f"        fullName: '{description}',",
                f"        type: '{field_type}',",
                f"        category: '{category}',",
                f"        priority: '{priority}',",
                f"        icon: '{icon}',",
                f"        backendName: '{field_name}',",
                "    },",
            ]
        )

    lines.extend(
        [
            "};",
            "",
            "export function getDateFields(ruleDefs = RULE_DEFINITIONS) {",
            "    return new Set(",
            "        Object.entries(ruleDefs)",
            "            .filter(([_, def]) => def.type === 'date')",
            "            .map(([name, _]) => name)",
            "    );",
            "}",
            "",
        ]
    )

    return "\n".join(lines)


def main() -> None:
    """Generate and save schema file."""
    output = generate_rule_definitions()
    output_path = Path("docs/js/generated_schema.js")
    output_path.write_text(output)

    with open("src/extractor/fields.yaml") as f:
        fields = yaml.safe_load(f)

    date_fields = sum(1 for v in fields.values() if v.get("type") == "date")
    print(f"Generated {output_path}")
    print(f"  {len(fields)} fields ({date_fields} date fields)")


if __name__ == "__main__":
    main()
