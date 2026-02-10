"""Unified extractors for conference CFP data.

This module provides unified extraction functions for:
1. Page requirements (merges page_limit + page_limit_exclusions)
2. Review process (keyword-based instead of 3 booleans)
3. Policy fields (artifact evaluation, LLM policy, concurrent submission)
4. Statement requirements (shows which statements are required)
"""

import re

from .unified_schema import (
    PageRequirements,
    PageExclusion,
    ReviewProcess,
    PolicyField,
    StatementsRequired,
    SubmissionRequirements,
    ConferenceLogistics,
    TrackDetection,
    ConfidenceLevel,
)


NUMBER_WORDS = {
    "one": "1",
    "two": "2",
    "three": "3",
    "four": "4",
    "five": "5",
    "six": "6",
    "seven": "7",
    "eight": "8",
    "nine": "9",
    "ten": "10",
    "eleven": "11",
    "twelve": "12",
}

PAGE_PATTERNS = [
    r"(\d+)\s+pages?\s+for\s+(?:the\s+)?main\s+(?:content|paper|text)?,?\s+plus\s+unlimited\s+(?:pages?\s+(?:for\s+)?)?references?(?:\s+and\s+(?:unlimited\s+)?appendices)?",
    r"(\d+)\s+pages?\s+for\s+(?:main|content)(?:\s+(?:paper|text))?,?\s+plus\s+unlimited\s+references",
    r"(\d+)\s+pages?\s+(?:plus|\+)\s+unlimited\s+(?:pages?\s+(?:for\s+)?)?references?",
    r"(\d+)\s+pages?\s+(?:excluding|not\s+including)\s+references?(?:\s+and\s+appendices)?",
    r"(\d+)\s+pages?(?:,|\s+(?:and|where|with))?\s+references?\s+(?:do\s+)?not\s+count",
    r"(\d+)\s+pages?\s+plus\s+(?:up\s+to\s+)?(\d+)\s+pages?\s+(?:for\s+|of\s+)?(?:references?|appendices)",
    r"(\d+)\s+pages?\s+\((?:references?\s+)?(?:excluded|not\s+included|excluding\s+references?)\)",
    r"maximum\s+(?:of\s+)?(\d+)\s+pages?",
    r"limited\s+to\s+(?:a\s+maximum\s+(?:of\s+)?)?(\d+)\s+pages?",
    r"(?:up\s+to|at\s+most)\s+(\d+)\s+pages?",
    r"(\d+)[- ]page\s+(?:limit|maximum)",
    r"page\s+limit\s+(?:is\s+)?(\d+)\s+pages?",
    r"papers?\s+(?:must|should)\s+be\s+(\d+)\s+pages?",
    r"(?:must\s+|should\s+)?not\s+exceed\s+(\d+)\s+pages?",
    r"no\s+(?:longer|more)\s+than\s+(\d+)\s+pages?",
    r"submissions?\s+(?:are\s+)?limited\s+to\s+(\d+)\s+pages?",
    r"manuscripts?\s+(?:of\s+)?up\s+to\s+(\d+)\s+pages?",
    r"between\s+(\d+)\s+and\s+(\d+)\s+pages?",
    r"(\d+)\s*(?:-|to)\s*(\d+)\s+pages?",
    r"(?i)Long\s+Papers?\s+\((\d+)\s+pages?\)\s+and\s+Short\s+Papers?\s+\((\d+)\s+pages?\)",
    r"(?i)(?:long|full|research|regular)\s+papers?\s*[:(]\s*(\d+)\s+pages?\s*[)]?",
    r"(?i)(?:short|extended\s+abstract)\s+papers?\s*[:(]\s*(\d+)\s+pages?\s*[)]?",
    r"(?i)limited\s+to\s+(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)\s+(?:content\s+)?pages?",
    r"(?i)(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)\s+(?:content\s+)?pages?\s+for\s+(?:the\s+)?main",
    r"(?i)(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)\s+pages?\s+(?:of\s+)?content",
    r"(?i)(?:main\s+text\s+)?must\s+be\s+between\s+(\d+)\s+and\s+(\d+)\s+pages?",
    r"(?i)limited\s+to\s+(\d+)\s+content\s+pages?",
    r"(?i)beyond\s+the\s+first\s+(\d+)\s+pages?",
    r"(?i)(?:the\s+)?first\s+(\d+)\s+pages?(?:\s+(?:should|must|will))",
]

EXCLUSION_PATTERNS = {
    "references": [
        r"unlimited\s+(?:pages?\s+(?:for\s+)?)?(?:references?|bibliograph(?:y|ies))",
        r"(?:plus|with)\s+unlimited\s+(?:pages?\s+(?:for\s+)?)?(?:references?|bibliograph(?:y|ies))",
        r"(?:(?:the|a)\s+)?(?:list\s+of\s+)?(?:references?|bibliograph(?:y|ies))\s+(?:do(?:es)?\s+)?not\s+count(?:\s+toward(?:s)?(?:\s+(?:the|this))?(?:\s+page)?\s+limit)?",
        r"(?:the\s+)?(?:list\s+of\s+)?(?:references?|bibliograph(?:y|ies))\s+(?:is|are)\s+not\s+included\s+in\s+(?:the\s+)?(?:\d+[- ])?page\s+(?:limit|count)",
        r"exclud(?:ing|ed?)\s+(?:the\s+)?(?:list\s+of\s+)?(?:references?|bibliograph(?:y|ies))",
        r"not\s+includ(?:ing|e|ed)\s+(?:the\s+)?(?:list\s+of\s+)?(?:references?|bibliograph(?:y|ies))",
        r"not\s+counting\s+(?:the\s+)?(?:list\s+of\s+)?(?:references?|bibliograph(?:y|ies))",
        r"(?:page\s+)?limit\s+(?:does\s+)?not\s+include\s+(?:the\s+)?references?",
        r"no\s+(?:page\s+)?limit\s+(?:on|for)\s+(?:the\s+)?references?",
        r"references?\s+(?:are\s+)?(?:listed\s+)?separate(?:ly)?",
        r"(?:in\s+)?addition\s+to\s+(?:the\s+)?(?:\d+[- ])?page\s+limit.*?references?",
        r"plus\s+(?:up\s+to\s+)?(\d+)\s+pages?\s+(?:for\s+|of\s+)?references?",
    ],
    "appendices": [
        r"appendices?\s+(?:do\s+)?not\s+count(?:\s+toward)?",
        r"unlimited\s+(?:pages?\s+(?:for\s+)?)?(?:appendices|appendix)",
        r"exclud(?:ing|ed)\s+(?:the\s+)?(?:appendices|appendix)",
        r"not\s+includ(?:ing|ed)\s+(?:the\s+)?(?:appendices|appendix)",
        r"not\s+counting\s+(?:the\s+)?(?:appendices|appendix)",
        r"(?:appendices|appendix)\s+(?:is\s+|are\s+)?(?:beyond|outside)\s+(?:the\s+)?page\s+limit",
        r"plus\s+(?:up\s+to\s+)?(\d+)\s+pages?\s+(?:for\s+|of\s+)?(?:appendices|appendix)",
    ],
    "acknowledgments": [
        r"acknowledgments?\s+(?:do(?:es)?\s+)?not\s+count",
    ],
    "ethics_statement": [
        r"ethics\s+(?:statement|section)\s+(?:does\s+)?not\s+count",
    ],
    "impact_statement": [
        r"(?:broader\s+)?impact\s+statement\s+(?:does\s+)?not\s+count",
    ],
}

REVIEW_KEYWORDS = {
    "double_blind": [
        r"double[- ]blind",
        r"anonymized?\s+(?:submission|review|manuscript|paper)",
        r"(?:submissions?|papers?)\s+(?:must|should|will)\s+be\s+anonymous(?:ized)?",
        r"(?:submitted|submit)\s+(?:papers?|manuscripts?)\s+(?:must|should)\s+be\s+anonymous",
        r"remove\s+(?:all\s+)?author\s+(?:names?|identif(?:ying|ication)|information)",
        r"both\s+(?:reviewers?\s+and\s+authors?|authors?\s+and\s+reviewers?)\s+(?:are\s+)?anonymous",
        r"authors?\s+(?:and\s+)?reviewers?\s+(?:are\s+)?(?:both\s+)?anonymous",
        r"blind\s+(?:to|submission).*author",
        r"author\s+identit(?:y|ies)\s+(?:must\s+)?(?:be\s+)?(?:hidden|concealed)",
    ],
    "single_blind": [
        r"single[- ]blind",
        r"reviewers?\s+(?:are|remain|will\s+be)\s+anonymous",
        r"authors?\s+(?:are\s+)?(?:known|visible).*reviewers?\s+(?:are\s+)?anonymous",
        r"reviewer\s+anonymity\s+(?:is\s+)?maintained",
        r"reviews?\s+(?:are\s+)?anonymous.*authors?\s+(?:are\s+)?(?:known|visible)",
    ],
    "open_review": [
        r"open\s+(?:peer\s+)?review(?:\s+process)?",
        r"reviews?\s+(?:will\s+be|are)\s+(?:made\s+)?public(?:ly)?(?:\s+available)?",
        r"transparent\s+review(?:\s+process)?",
        r"public\s+(?:review|discussion)",
        r"reviews?\s+(?:and\s+)?(?:author\s+)?responses?\s+(?:will\s+be\s+)?(?:made\s+)?public",
        r"non[- ]anonymous\s+review",
    ],
}

REBUTTAL_PATTERNS = {
    "allowed": [
        r"author(?:s)?\s+(?:may|can|will\s+have)\s+(?:the\s+)?(?:opportunity\s+)?(?:to\s+)?(?:submit\s+)?rebuttals?",
        r"rebuttals?\s+(?:are\s+)?(?:allowed|permitted|encouraged)",
        r"(?:will\s+have|have)\s+(?:the\s+)?(?:opportunity|chance)\s+to\s+respond\s+to\s+reviews?",
        r"author\s+response\s+(?:period|phase)",
        r"response\s+to\s+reviewers?",
    ],
    "not_allowed": [
        r"no\s+rebuttals?",
        r"rebuttals?\s+(?:are\s+)?not\s+(?:allowed|permitted)",
        r"(?:will\s+)?not\s+(?:be\s+)?(?:able|allowed)\s+to\s+submit\s+rebuttals?",
    ],
}

DESK_REJECTION_PATTERNS = {
    "yes": [
        r"desk\s+reject(?:ion)?",
        r"papers?\s+may\s+be\s+desk\s+rejected",
        r"(?:may|will)\s+be\s+rejected\s+without\s+(?:full\s+)?review",
        r"administrative\s+reject(?:ion)?",
    ],
    "no": [
        r"no\s+desk\s+reject(?:ion)?",
        r"all\s+papers?\s+(?:will\s+)?(?:be\s+)?(?:fully\s+)?reviewed",
    ],
}

RECIPROCAL_REVIEW_PATTERNS = {
    True: [
        r"reciprocal\s+review(?:ing)?",
        r"(?:must|required\s+to)\s+review\s+other\s+(?:papers?|submissions?)",
        r"authors?\s+(?:are\s+)?(?:expected|required)\s+to\s+(?:serve\s+as\s+)?reviewers?",
    ],
    False: [
        r"no\s+reciprocal\s+review",
        r"(?:not\s+)?required\s+to\s+review",
    ],
}

POLICY_PATTERNS = {
    "artifact_evaluation": {
        "mandatory": [
            r"artifacts?\s+(?:submission\s+)?(?:is\s+)?(?:required|mandatory)",
            r"(?:are\s+)?required\s+to\s+submit\s+artifacts?",
            r"code\s+submission\s+(?:is\s+)?required",
            r"must\s+(?:submit|provide|include)\s+(?:code|artifacts?|data)",
            r"all\s+papers?\s+must\s+include\s+(?:code|artifacts?)",
        ],
        "optional": [
            r"(?:may\s+)?optionally\s+submit\s+artifacts?",
            r"artifacts?\s+(?:are\s+)?optional",
            r"artifact\s+submission\s+is\s+(?:voluntary|optional)",
            r"submit\s+code\s+for\s+artifact",
            r"(?:strongly\s+)?(?:encouraged|recommended)\s+(?:to\s+)?(?:submit|provide)\s+(?:code|artifacts?)",
            r"artifact\s+evaluation\s+is\s+(?:encouraged|recommended)",
            r"(?:we\s+)?encourage\s+(?:authors?\s+)?to\s+submit\s+artifacts?",
            r"(?:encouraged|recommended)\s+to\s+submit.*?(?:data|source\s+code|supplementary\s+material)",
            r"(?:encouraged|recommended)\s+to\s+(?:provide|upload).*?(?:data|code)",
        ],
        "not_mentioned": [],
    },
    "llm_policy": {
        "required_disclosure": [
            r"(?:may|can)\s+use\s+(?:large\s+language\s+models?|LLMs?|AI|ChatGPT)(?:.*?)must\s+disclose",
            r"(?:use|usage)\s+of\s+(?:large\s+language\s+models?|LLMs?|AI)\s+(?:is\s+)?allowed(?:.*?)disclose",
            r"disclose\s+(?:any\s+)?(?:use|usage)\s+of\s+(?:LLMs?|AI|ChatGPT|large\s+language\s+models?)",
        ],
        "forbidden": [
            r"(?:use\s+of\s+)?(?:AI-generated|LLM-generated)\s+(?:text|content)\s+(?:is\s+)?prohibited",
            r"(?:LLMs?|AI|ChatGPT)(?:.*?)(?:is\s+)?(?:prohibited|not\s+allowed|forbidden)",
            r"(?:do\s+not|cannot)\s+use\s+(?:LLMs?|AI|ChatGPT)",
            r"papers?\s+found\s+to\s+contain\s+(?:ChatGPT|LLM|AI)",
            r"discourage\s+(?:the\s+)?use\s+of\s+(?:large\s+language\s+models?|LLMs?|AI)",
            r"(?:LLMs?|AI)\s+(?:usage\s+)?(?:is\s+)?discouraged",
            r"(?:should|recommend)\s+not\s+use\s+(?:LLMs?|AI)",
        ],
        "allowed": [
            r"(?:may|can)\s+use\s+(?:large\s+language\s+models?|LLMs?|AI|ChatGPT)",
            r"(?:LLMs?|AI)\s+(?:usage\s+)?(?:is\s+)?(?:allowed|permitted)",
        ],
        "not_mentioned": [],
    },
    "concurrent_submission": {
        "not_allowed": [
            r"concurrent\s+submissions?\s+(?:are\s+)?(?:not\s+)?(?:allowed|permitted|prohibited)",
            r"papers?\s+under\s+review\s+at\s+other\s+venues\s+will\s+be\s+rejected",
            r"simultaneous\s+submission(?:s)?\s+(?:to\s+)?(?:multiple\s+)?(?:conferences?\s+)?(?:is\s+)?not\s+permitted",
            r"(?:do\s+not|cannot)\s+submit\s+(?:concurrently|simultaneously)",
        ],
        "allowed": [
            r"(?:may|can)\s+submit(?:.*?)concurrently",
            r"concurrent\s+submissions?\s+(?:are\s+)?(?:allowed|permitted)",
            r"parallel\s+submissions?\s+(?:are\s+)?permitted",
            r"authors?\s+may\s+submit(?:.*?)(?:to\s+)?other\s+venues",
        ],
        "not_mentioned": [],
    },
    "arxiv_preprint": {
        "allowed": [
            r"arXiv\s+(?:preprints?\s+)?(?:are\s+)?allowed",
            r"(?:may|can)\s+(?:post|upload)\s+(?:to\s+)?arXiv",
        ],
        "not_allowed": [
            r"arXiv\s+(?:preprints?\s+)?(?:are\s+)?(?:not\s+)?(?:allowed|permitted|prohibited)",
            r"(?:do\s+not|cannot)\s+(?:post|upload)\s+(?:to\s+)?arXiv",
        ],
        "not_mentioned": [],
    },
}

STATEMENT_PATTERNS = {
    "ethics_statement": [
        r"ethics\s+statement\s+(?:is\s+)?(?:required|mandatory)",
        r"must\s+include\s+(?:an?\s+)?ethics\s+statement",
        r"ethics\s+section\s+(?:is\s+)?required",
        r"-\s+ethics\s+statement",
        r"(?:all\s+)?papers?\s+must\s+include\s+(?:an?\s+)?ethics\s+statement",
    ],
    "broader_impact": [
        r"broader\s+impacts?\s+(?:statement|section)\s+(?:is\s+)?required",
        r"impact\s+statement\s+(?:is\s+)?required",
        r"must\s+include\s+(?:an?\s+)?(?:broader\s+)?impacts?\s+(?:statement|section)",
        r"-\s+broader\s+impact",
        r"discuss\s+(?:the\s+)?broader\s+impacts?(?:.*?)required",
        r"dedicated\s+impact\s+statement(?:.*?)required",
        r"societal\s+impact",
    ],
    "reproducibility_checklist": [
        r"reproducibility\s+checklist\s+(?:is\s+)?(?:required|mandatory)",
        r"must\s+complete\s+(?:the\s+)?reproducibility\s+checklist",
        r"checklist\s+(?:is\s+)?(?:required|mandatory)",
        r"-\s+reproducibility\s+checklist",
        r"(?:required|must)\s+(?:to\s+)?complete\s+(?:a\s+)?(?:paper\s+)?checklist",
        r"(?:authors?\s+(?:are\s+)?)?required\s+to\s+complete\s+(?:a\s+)?(?:paper\s+)?checklist",
        r"checklist\s+forms\s+part\s+of\s+(?:the\s+)?(?:paper\s+)?submission",
        r"paper\s+checklist",
        r"NeurIPS\s+(?:paper\s+)?checklist",
    ],
    "limitations_section": [
        r"limitations\s+section\s+(?:is\s+)?required",
        r"must\s+include\s+(?:a\s+)?limitations\s+(?:section|discussion)",
    ],
    "funding_disclosure": [
        r"funding\s+disclosure\s+(?:is\s+)?required",
        r"must\s+disclose\s+funding",
        r"conflict\s+of\s+interest\s+(?:statement\s+)?(?:is\s+)?required",
    ],
}

TEMPLATE_PATTERNS = {
    "required": [
        r"(?:must|required\s+to)\s+use\s+(?:the\s+)?(?:provided\s+)?(?:LaTeX|Word|conference)\s+template",
        r"template\s+(?:is\s+)?(?:required|mandatory)",
        r"(?:papers?|submissions?)\s+must\s+(?:be\s+)?(?:formatted\s+)?using\s+(?:the\s+)?template",
        r"(?:LaTeX|Word)\s+template\s+(?:is\s+)?(?:required|mandatory)",
    ],
    "optional": [
        r"template\s+(?:is\s+)?(?:available|provided|optional)",
        r"(?:may|can)\s+use\s+(?:the\s+)?template",
    ],
}

SUPPLEMENTARY_PATTERNS = {
    "allowed": [
        r"supplementary\s+(?:materials?|files?)\s+(?:are\s+)?(?:allowed|permitted|encouraged)",
        r"(?:may|can)\s+(?:include|submit|provide)\s+supplementary\s+(?:materials?|files?)",
        r"appendices?\s+(?:are\s+)?(?:allowed|permitted)",
        r"additional\s+materials?\s+(?:may|can)\s+be\s+(?:submitted|included)",
    ],
    "not_allowed": [
        r"no\s+supplementary\s+(?:materials?|files?)",
        r"supplementary\s+(?:materials?|files?)\s+(?:are\s+)?not\s+(?:allowed|permitted)",
    ],
}

PRESENTATION_FORMAT_PATTERNS = [
    r"(?:oral|poster|demo|virtual|in-person|hybrid)\s+presentations?",
    r"presented\s+as\s+(?:oral|poster|demo)",
    r"(?:will\s+be\s+)?presented\s+(?:orally|as\s+posters?|virtually)",
]

CONFERENCE_FORMAT_PATTERNS = {
    "in-person": [
        r"in[- ]person\s+(?:conference|event|meeting)",
        r"physical\s+conference",
        r"on[- ]site\s+(?:conference|event)",
    ],
    "virtual": [
        r"virtual\s+(?:conference|event|meeting)",
        r"online\s+(?:conference|event|meeting)",
        r"remote\s+(?:conference|participation)",
    ],
    "hybrid": [
        r"hybrid\s+(?:conference|event|meeting)",
        r"(?:virtual|online)\s+and\s+(?:in[- ]person|physical)",
        r"(?:in[- ]person|physical)\s+and\s+(?:virtual|online)",
    ],
}

FINANCIAL_AID_PATTERNS = [
    r"(?:financial\s+)?(?:aid|assistance|support)\s+(?:is\s+)?available",
    r"(?:travel\s+)?grants?\s+(?:are\s+)?available",
    r"(?:student\s+)?scholarships?\s+(?:are\s+)?available",
    r"funding\s+(?:is\s+)?available",
]

WORKSHOP_PATTERNS = [
    r"workshops?(?:\s+and\s+tutorials?)?",
    r"co[- ]located\s+workshops?",
    r"affiliated\s+workshops?",
]

TRACK_DETECTION_PATTERNS = {
    "has_workshop_proposals": [
        r"call\s+for\s+workshop\s+proposals?",
        r"workshop\s+proposals?\s+(?:are\s+)?(?:invited|solicited|welcome)",
        r"submit\s+(?:a\s+)?workshop\s+proposal",
        r"proposing\s+(?:a\s+)?workshop",
    ],
    "has_tutorials": [
        r"call\s+for\s+tutorials?",
        r"tutorial\s+(?:track|proposals?|submissions?|program)",
        r"tutorials?\s+(?:are\s+)?(?:invited|solicited|welcome)",
        r"(?:include|offer|feature)s?\s+tutorials?",
    ],
    "has_demos": [
        r"call\s+for\s+demos?",
        r"(?:system\s+)?demonstrations?\s+(?:track|papers?|submissions?)",
        r"demo\s+(?:track|papers?|submissions?|program)",
        r"system\s+demonstrations?",
    ],
    "has_posters": [
        r"call\s+for\s+posters?",
        r"poster\s+(?:track|session|submissions?|program)",
        r"(?:submit|present)\s+(?:a\s+)?poster",
    ],
    "has_industry_track": [
        r"industry\s+(?:track|papers?|program|session)",
        r"(?:applied|applications?)\s+(?:track|papers?|program)",
        r"call\s+for\s+industry",
    ],
    "has_position_papers": [
        r"position\s+papers?",
        r"opinion\s+papers?",
        r"perspective\s+papers?",
        r"call\s+for\s+position",
    ],
    "has_student_research": [
        r"student\s+research\s+(?:workshop|competition|forum|track)",
        r"SRW\b",
        r"student\s+abstract",
        r"(?:undergraduate|graduate)\s+(?:student\s+)?research\s+(?:track|forum)",
    ],
    "has_doctoral_consortium": [
        r"doctoral\s+(?:consortium|symposium|forum)",
        r"DC\s+(?:track|program|submissions?)",
        r"call\s+for\s+doctoral\s+consortium",
    ],
    "has_findings": [
        r"\bfindings\b\s+(?:track|papers?|of\s+(?:ACL|EMNLP|NAACL|EACL))",
        r"findings\s+(?:submissions?|program)",
        r"(?:accepted|published)\s+(?:in|to)\s+findings",
    ],
    "has_awards": [
        r"best\s+paper\s+award",
        r"outstanding\s+paper\s+award",
        r"distinguished\s+paper\s+award",
        r"test[- ]of[- ]time\s+award",
        r"best\s+(?:student\s+)?paper",
    ],
}


def extract_page_requirements_unified(text: str) -> PageRequirements:
    """Extract page requirements.

    :param text: Conference CFP text
    :returns: PageRequirements object
    """
    page_info = {
        "main_limit": "unknown",
        "exclusions": [],
        "paper_types": {},
        "evidence": "",
        "confidence": ConfidenceLevel.LOW,
    }

    all_matches = []

    for i, pattern in enumerate(PAGE_PATTERNS):
        for match in re.finditer(pattern, text, re.IGNORECASE):
            matched_text = match.group(0)
            matched_lower = matched_text.lower()

            start = max(0, match.start() - 100)
            end = min(len(text), match.end() + 100)
            context = text[start:end].lower()

            priority = 0
            if i < 7:
                priority += 100
            if any(
                kw in context
                for kw in [
                    "main paper",
                    "regular paper",
                    "full paper",
                    "research paper",
                    "submission",
                ]
            ):
                priority += 50
            if not any(
                kw in context
                for kw in [
                    "poster",
                    "demo",
                    "workshop",
                    "abstract submission",
                    "extended abstract",
                ]
            ):
                priority += 25

            numbers = re.findall(r"\d+", matched_text)
            if not numbers:
                for word, digit in NUMBER_WORDS.items():
                    if re.search(rf"\b{word}\b", matched_lower):
                        numbers = [digit]
                        matched_text = re.sub(
                            rf"\b{word}\b", digit, matched_text, flags=re.IGNORECASE
                        )
                        matched_lower = matched_text.lower()
                        break

            if not numbers:
                continue

            page_num = int(numbers[0])
            if page_num >= 6:
                priority += 20

            all_matches.append(
                {
                    "match": match,
                    "text": matched_text,
                    "pattern_index": i,
                    "numbers": numbers,
                    "context": context,
                    "priority": priority,
                }
            )

    all_matches.sort(key=lambda x: x["priority"], reverse=True)

    if all_matches:
        best = all_matches[0]
        match = best["match"]
        matched_text = best["text"]
        matched_lower = matched_text.lower()
        i = best["pattern_index"]
        numbers = best["numbers"]

        confidence = ConfidenceLevel.HIGH if i < 7 else ConfidenceLevel.MEDIUM

        if "long papers" in matched_lower and "short papers" in matched_lower:
            if len(numbers) >= 2:
                page_info["paper_types"]["long"] = f"{numbers[0]} pages"
                page_info["paper_types"]["short"] = f"{numbers[1]} pages"
                page_info["main_limit"] = (
                    f"{numbers[0]} pages (long), {numbers[1]} pages (short)"
                )
                page_info["evidence"] = matched_text
                page_info["confidence"] = confidence

        elif len(numbers) == 2:
            is_range = bool(
                re.search(rf"between\s+{numbers[0]}\s+and\s+{numbers[1]}", matched_text)
                or re.search(rf"{numbers[0]}\s+to\s+{numbers[1]}", matched_text)
                or re.search(rf"{numbers[0]}\s*-\s*{numbers[1]}", matched_text)
            )

            if is_range:
                page_info["main_limit"] = f"{numbers[0]}-{numbers[1]} pages"
            else:
                page_info["main_limit"] = f"{numbers[0]} pages"
            page_info["evidence"] = matched_text
            page_info["confidence"] = confidence

        else:
            page_info["main_limit"] = f"{numbers[0]} pages"
            page_info["evidence"] = matched_text
            page_info["confidence"] = confidence

        exclusions_found = set()

        if re.search(
            r"unlimited\s+(?:pages?\s+(?:for\s+)?)?references?", matched_lower
        ):
            exclusions_found.add("references")
            page_info["exclusions"].append(
                PageExclusion(type="references", limit="unlimited")
            )
        elif re.search(
            r"exclud(?:ing|ed)\s+references?|not\s+counting\s+references?|references?\s+(?:do\s+)?not\s+count|references?\s+(?:excluded|not\s+included)",
            matched_lower,
        ):
            exclusions_found.add("references")
            page_info["exclusions"].append(
                PageExclusion(type="references", limit="unlimited")
            )

        if re.search(r"unlimited\s+(?:pages?\s+(?:for\s+)?)?appendices", matched_lower):
            if "appendices" not in exclusions_found:
                page_info["exclusions"].append(
                    PageExclusion(type="appendices", limit="unlimited")
                )
                exclusions_found.add("appendices")
        elif re.search(
            r"exclud(?:ing|ed)\s+(?:appendices|appendix)|not\s+counting\s+(?:appendices|appendix)|appendices?\s+(?:do\s+)?not\s+count",
            matched_lower,
        ):
            if "appendices" not in exclusions_found:
                page_info["exclusions"].append(
                    PageExclusion(type="appendices", limit="unlimited")
                )
                exclusions_found.add("appendices")

        bounded_match = re.search(
            r"plus\s+(?:up\s+to\s+)?(\d+)\s+pages?\s+(?:for\s+|of\s+)?(references?|appendices)",
            matched_lower,
        )
        if bounded_match:
            limit_pages = bounded_match.group(1)
            excl_type = (
                "references" if "reference" in bounded_match.group(2) else "appendices"
            )
            if excl_type not in exclusions_found:
                page_info["exclusions"].append(
                    PageExclusion(type=excl_type, limit=f"{limit_pages} pages")
                )

    if page_info["main_limit"] != "unknown" and not page_info["exclusions"]:
        combined_patterns = [
            r"(?:not\s+counting|exclud(?:ing|ed)|not\s+includ(?:ing|ed))\s+(?:the\s+)?(?:references?|bibliograph(?:y|ies))\s+and\s+(?:the\s+)?(?:appendices|appendix)",
            r"(?:not\s+counting|exclud(?:ing|ed)|not\s+includ(?:ing|ed))\s+(?:the\s+)?(?:appendices|appendix)\s+and\s+(?:the\s+)?(?:references?|bibliograph(?:y|ies))",
        ]

        for pattern in combined_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                page_info["exclusions"].append(
                    PageExclusion(type="references", limit="unlimited")
                )
                page_info["exclusions"].append(
                    PageExclusion(type="appendices", limit="unlimited")
                )
                if page_info["confidence"] == ConfidenceLevel.MEDIUM:
                    page_info["confidence"] = ConfidenceLevel.HIGH
                break

        if not page_info["exclusions"]:
            for excl_type, patterns in EXCLUSION_PATTERNS.items():
                for pattern in patterns:
                    match = re.search(pattern, text, re.IGNORECASE)
                    if match and not any(
                        e.type == excl_type for e in page_info["exclusions"]
                    ):
                        bounded_match = re.search(
                            r"plus\s+(?:up\s+to\s+)?(\d+)\s+pages?",
                            match.group(0),
                            re.IGNORECASE,
                        )
                        limit = (
                            f"{bounded_match.group(1)} pages"
                            if bounded_match
                            else "unlimited"
                        )
                        page_info["exclusions"].append(
                            PageExclusion(type=excl_type, limit=limit)
                        )
                        if page_info["confidence"] == ConfidenceLevel.MEDIUM:
                            page_info["confidence"] = ConfidenceLevel.HIGH
                        break

    return PageRequirements(
        main_limit=page_info["main_limit"],
        exclusions=page_info["exclusions"],
        paper_types=page_info["paper_types"],
        evidence=page_info["evidence"],
        confidence=page_info["confidence"],
    )


def extract_review_process_keywords(text: str) -> ReviewProcess:
    """Extract review process including rebuttal and desk rejection policies.

    :param text: Conference CFP text
    :returns: ReviewProcess object
    """
    keywords_found = []
    classification_scores = {"double_blind": 0, "single_blind": 0, "open_review": 0}
    evidence_snippets = []
    nuances = []

    for mode, patterns in REVIEW_KEYWORDS.items():
        for pattern in patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                matched_text = match.group(0)
                keywords_found.append(matched_text)

                weight = 1.0
                if re.search(
                    r"(double|single)[- ]blind\s+(review|process)",
                    matched_text,
                    re.IGNORECASE,
                ):
                    weight = 2.0
                elif re.search(
                    r"open\s+(?:peer\s+)?review", matched_text, re.IGNORECASE
                ):
                    weight = 2.0
                elif (
                    "OpenReview" in matched_text or "openreview" in matched_text.lower()
                ):
                    weight = 0.3

                classification_scores[mode] += weight

                start = max(0, match.start() - 50)
                end = min(len(text), match.end() + 50)
                evidence_snippets.append(text[start:end].strip())

    if not keywords_found:
        classification = "unknown"
        evidence = ""
        confidence = ConfidenceLevel.LOW
    else:
        classification = max(classification_scores, key=classification_scores.get)
        evidence = "; ".join(evidence_snippets[:2])

        max_score = classification_scores[classification]
        second_max = sorted(classification_scores.values(), reverse=True)[1]

        if max_score >= 3:
            confidence = ConfidenceLevel.HIGH
        elif max_score == 2 and second_max == 0:
            confidence = ConfidenceLevel.MEDIUM
        else:
            confidence = ConfidenceLevel.LOW

        if (
            classification_scores["double_blind"] > 0
            and classification_scores["single_blind"] > 0
        ):
            nuances.append("Mixed policy detected - may vary by track or phase")

        if "workshop" in text.lower() and classification != "unknown":
            workshop_context = re.search(r"workshop[^.]{0,100}", text, re.IGNORECASE)
            if workshop_context:
                nuances.append(
                    f"Workshop policy may differ: {workshop_context.group(0)}"
                )

    rebuttal_policy = "unknown"
    for policy, patterns in REBUTTAL_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, text, re.IGNORECASE):
                rebuttal_policy = policy
                break
        if rebuttal_policy != "unknown":
            break

    desk_rejection_policy = "unknown"
    for policy, patterns in DESK_REJECTION_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, text, re.IGNORECASE):
                desk_rejection_policy = policy
                break
        if desk_rejection_policy != "unknown":
            break

    reciprocal_review_required = "unknown"
    for policy, patterns in RECIPROCAL_REVIEW_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, text, re.IGNORECASE):
                reciprocal_review_required = policy
                break
        if reciprocal_review_required != "unknown":
            break

    return ReviewProcess(
        keywords_found=list(set(keywords_found))[:10],
        classification=classification,
        nuances=nuances,
        evidence=evidence,
        confidence=confidence,
        rebuttal_policy=rebuttal_policy,
        desk_rejection_policy=desk_rejection_policy,
        reciprocal_review_required=reciprocal_review_required,
    )


def extract_policy_field(text: str, policy_type: str) -> PolicyField:
    """Extract policy field.

    :param text: Conference CFP text
    :param policy_type: Policy type (artifact_evaluation, llm_policy, etc.)
    :returns: PolicyField object
    """
    if policy_type not in POLICY_PATTERNS:
        return PolicyField(value="unknown", confidence=ConfidenceLevel.LOW)

    patterns = POLICY_PATTERNS[policy_type]
    value_scores = {value: 0 for value in patterns.keys()}
    keywords_found = []
    evidence_snippets = []

    for value, value_patterns in patterns.items():
        for pattern in value_patterns:
            matches = list(re.finditer(pattern, text, re.IGNORECASE | re.DOTALL))
            if matches:
                value_scores[value] += len(matches)
                keywords_found.extend([m.group(0) for m in matches])

                for match in matches[:2]:
                    start = max(0, match.start() - 30)
                    end = min(len(text), match.end() + 30)
                    evidence_snippets.append(text[start:end].strip())

    if max(value_scores.values()) == 0:
        value = "not_mentioned" if "not_mentioned" in patterns else "unknown"
        confidence = ConfidenceLevel.LOW
        evidence = ""
    else:
        if (
            policy_type == "llm_policy"
            and value_scores.get("required_disclosure", 0) > 0
        ):
            value = "required_disclosure"
            max_score = value_scores[value]
        else:
            value = max(value_scores, key=value_scores.get)
            max_score = value_scores[value]

        evidence = "; ".join(evidence_snippets[:2])
        confidence = ConfidenceLevel.HIGH if max_score >= 3 else ConfidenceLevel.MEDIUM

    return PolicyField(
        value=value,
        keywords_found=list(set(keywords_found))[:5],
        evidence=evidence,
        confidence=confidence,
    )


def extract_statements_required(text: str) -> StatementsRequired:
    """Extract required statements.

    :param text: Conference CFP text
    :returns: StatementsRequired object
    """
    types_required = []
    keywords_found = []
    evidence_snippets = []

    for statement_type, patterns in STATEMENT_PATTERNS.items():
        for pattern in patterns:
            matches = list(re.finditer(pattern, text, re.IGNORECASE))
            if matches:
                if statement_type not in types_required:
                    types_required.append(statement_type)

                keywords_found.extend([m.group(0) for m in matches[:2]])

                for match in matches[:1]:
                    start = max(0, match.start() - 30)
                    end = min(len(text), match.end() + 30)
                    evidence_snippets.append(text[start:end].strip())

    if not types_required:
        confidence = ConfidenceLevel.LOW
        evidence = ""
    elif len(types_required) >= 2:
        confidence = ConfidenceLevel.HIGH
        evidence = "; ".join(evidence_snippets[:3])
    else:
        confidence = ConfidenceLevel.MEDIUM
        evidence = evidence_snippets[0] if evidence_snippets else ""

    return StatementsRequired(
        types=types_required,
        keywords_found=list(set(keywords_found))[:10],
        evidence=evidence,
        confidence=confidence,
    )


def extract_submission_requirements(text: str) -> SubmissionRequirements:
    """Extract template and supplementary material requirements.

    :param text: Conference CFP text
    :returns: SubmissionRequirements object
    """
    template_required = "unknown"
    template_details = ""
    supplementary_allowed = "unknown"
    supplementary_limits = ""
    evidence_snippets = []

    for req_type, patterns in TEMPLATE_PATTERNS.items():
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                template_required = req_type == "required"
                template_details = match.group(0)
                start = max(0, match.start() - 30)
                end = min(len(text), match.end() + 30)
                evidence_snippets.append(text[start:end].strip())
                break
        if template_required != "unknown":
            break

    for allow_type, patterns in SUPPLEMENTARY_PATTERNS.items():
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                supplementary_allowed = allow_type == "allowed"
                start = max(0, match.start() - 30)
                end = min(len(text), match.end() + 100)
                context = text[start:end]
                evidence_snippets.append(context.strip())

                limit_match = re.search(
                    r"(\d+)\s*(?:MB|GB|pages?)", context, re.IGNORECASE
                )
                if limit_match:
                    supplementary_limits = limit_match.group(0)
                break
        if supplementary_allowed != "unknown":
            break

    evidence = "; ".join(evidence_snippets[:2])
    confidence = ConfidenceLevel.MEDIUM if evidence_snippets else ConfidenceLevel.LOW

    return SubmissionRequirements(
        template_required=template_required,
        template_details=template_details,
        supplementary_allowed=supplementary_allowed,
        supplementary_limits=supplementary_limits,
        evidence=evidence,
        confidence=confidence,
    )


def extract_conference_logistics(text: str) -> ConferenceLogistics:
    """Extract conference logistics information.

    :param text: Conference CFP text
    :returns: ConferenceLogistics object
    """
    presentation_formats = []
    financial_aid_available = "unknown"
    workshops_present = "unknown"
    conference_format = "unknown"
    evidence_snippets = []

    for pattern in PRESENTATION_FORMAT_PATTERNS:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            matched_text = match.group(0).lower()
            if "oral" in matched_text and "oral" not in presentation_formats:
                presentation_formats.append("oral")
            if "poster" in matched_text and "poster" not in presentation_formats:
                presentation_formats.append("poster")
            if "demo" in matched_text and "demo" not in presentation_formats:
                presentation_formats.append("demo")
            if "virtual" in matched_text and "virtual" not in presentation_formats:
                presentation_formats.append("virtual")

    for pattern in FINANCIAL_AID_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            financial_aid_available = True
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                start = max(0, match.start() - 20)
                end = min(len(text), match.end() + 50)
                evidence_snippets.append(text[start:end].strip())
            break

    for pattern in WORKSHOP_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            workshops_present = True
            break

    for format_type, patterns in CONFERENCE_FORMAT_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, text, re.IGNORECASE):
                conference_format = format_type
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    start = max(0, match.start() - 20)
                    end = min(len(text), match.end() + 50)
                    evidence_snippets.append(text[start:end].strip())
                break
        if conference_format != "unknown":
            break

    evidence = "; ".join(evidence_snippets[:2])
    confidence = ConfidenceLevel.MEDIUM if evidence_snippets else ConfidenceLevel.LOW

    return ConferenceLogistics(
        presentation_formats=presentation_formats,
        financial_aid_available=financial_aid_available,
        workshops_present=workshops_present,
        conference_format=conference_format,
        evidence=evidence,
        confidence=confidence,
    )


def extract_track_detection(text: str) -> TrackDetection:
    """Detect which tracks and events a conference offers.

    :param text: Conference CFP text
    :returns: TrackDetection object
    """
    results = {}
    evidence_snippets = []

    for field_name, patterns in TRACK_DETECTION_PATTERNS.items():
        found = False
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                found = True
                start = max(0, match.start() - 20)
                end = min(len(text), match.end() + 50)
                evidence_snippets.append(text[start:end].strip())
                break
        results[field_name] = found if found else "unknown"

    evidence = "; ".join(evidence_snippets[:3])
    detected_count = sum(1 for v in results.values() if v is True)
    confidence = (
        ConfidenceLevel.HIGH
        if detected_count >= 3
        else ConfidenceLevel.MEDIUM
        if detected_count >= 1
        else ConfidenceLevel.LOW
    )

    return TrackDetection(
        evidence=evidence,
        confidence=confidence,
        **results,
    )
