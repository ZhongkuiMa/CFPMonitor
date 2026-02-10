/** Rule definitions and rendering logic. */

import { formatShortDate } from './utils.js';
import { RULE_DEFINITIONS as GENERATED_SCHEMA, getDateFields } from './generated_schema.js';

// ---- Display helper factories ----

function boolDisplay(yesText, noText) {
    return {
        icon: v => v === true ? '\u2713' : v === false ? '\u2717' : '?',
        statusText: v => v === true ? yesText : v === false ? noText : 'Unknown',
        cssClass: v => v === true ? 'confirmed' : v === false ? 'denied' : 'unknown',
    };
}

function boolDisplayInverted(yesText, noText) {
    return {
        icon: v => v === true ? '\u2713' : v === false ? '\u2717' : '?',
        statusText: v => v === true ? yesText : v === false ? noText : 'Unknown',
        cssClass: v => v === true ? 'denied' : v === false ? 'confirmed' : 'unknown',
    };
}

function enumDisplay(map) {
    return {
        icon: v => (map[v] || [])[0] || '?',
        statusText: v => (map[v] || [])[1] || 'Unknown',
        cssClass: v => (map[v] || [])[2] || 'unknown',
    };
}

function valueDisplay(icon, opts = {}) {
    const base = {
        icon: v => v && v !== 'unknown' ? icon : '?',
        statusText: v => v !== 'unknown' ? (opts.suffix ? `${v} ${opts.suffix}` : String(v)) : 'Unknown',
        cssClass: v => v !== 'unknown' ? 'value' : 'unknown',
    };
    if (opts.labelWithValue) {
        base.getLabelWithValue = v => v !== 'unknown' ? String(v) : opts.fallbackLabel;
    }
    if (opts.formatter) base.formatter = opts.formatter;
    return base;
}

function listDisplay(icon) {
    return {
        icon: v => Array.isArray(v) && v.length > 0 ? icon : '?',
        statusText: v => Array.isArray(v) && v.length > 0 ? v.join(', ') : 'Unknown',
        cssClass: v => Array.isArray(v) && v.length > 0 ? 'value' : 'unknown',
    };
}

const MANDATORY_OPTIONAL_NONE = {
    mandatory: ['\u2713', 'Required', 'confirmed'],
    optional:  ['\u25CB', 'Optional', 'partial'],
    none:      ['\u2717', 'Not Required', 'denied'],
};

const MANDATORY_OPTIONAL_NONE_DISALLOWED = {
    mandatory: ['\u2713', 'Required', 'confirmed'],
    optional:  ['\u25CB', 'Optional', 'partial'],
    none:      ['\u2717', 'Not Allowed', 'denied'],
};


// ---- Custom display logic ----

const CUSTOM_DISPLAY_LOGIC = {
    // Boolean fields
    double_blind:                { label: 'Double-Blind Review', fullName: 'Double-Blind Review Process', ...boolDisplay('Required', 'Not Required') },
    rebuttal_allowed:            { label: 'Author Rebuttal', fullName: 'Author Rebuttal Period', ...boolDisplay('Allowed', 'Not Allowed') },
    concurrent_submission:       boolDisplay('Allowed', 'Not Allowed'),
    reciprocal_review:           boolDisplay('Required', 'Not Required'),
    lay_summary_required:        boolDisplay('Required', 'Not Required'),
    arxiv_preprint:              { label: 'arXiv Preprints', fullName: 'arXiv Preprint Posting Policy', ...boolDisplay('Allowed', 'Not Allowed') },
    single_blind:                { label: 'Single-Blind', ...boolDisplay('Single-Blind', 'Not Single-Blind') },
    open_review:                 boolDisplay('Public Reviews', 'Private Reviews'),
    template_required:           { label: 'Template Required', fullName: 'Official Template Requirement', ...boolDisplay('Required', 'Not Required') },
    supplementary_material_allowed: { label: 'Supplementary Material', fullName: 'Supplementary Material Submission', ...boolDisplay('Allowed', 'Not Allowed') },
    workshops:                   { label: 'Workshops Available', fullName: 'Workshops and Satellite Events', ...boolDisplay('Available', 'Not available') },
    financial_aid_available:     { label: 'Financial Aid Available', fullName: 'Travel Grants and Financial Support', ...boolDisplay('Available', 'Not available') },
    has_workshop_proposals:      { label: 'Workshop Proposals', fullName: 'Call for Workshop Proposals', ...boolDisplay('Available', 'Not mentioned') },
    has_tutorials:               { label: 'Tutorials', fullName: 'Tutorials Track', ...boolDisplay('Available', 'Not mentioned') },
    has_demos:                   { label: 'Demos', fullName: 'Demo/System Demonstrations Track', ...boolDisplay('Available', 'Not mentioned') },
    has_posters:                 { label: 'Poster Track', fullName: 'Dedicated Poster Submission Track', ...boolDisplay('Available', 'Not mentioned') },
    has_industry_track:          { label: 'Industry Track', fullName: 'Industry/Applications Track', ...boolDisplay('Available', 'Not mentioned') },
    has_position_papers:         { label: 'Position Papers', fullName: 'Position/Opinion Papers Track', ...boolDisplay('Available', 'Not mentioned') },
    has_student_research:        { label: 'Student Research', fullName: 'Student Research Workshop/Competition', ...boolDisplay('Available', 'Not mentioned') },
    has_doctoral_consortium:     { label: 'Doctoral Consortium', fullName: 'Doctoral Consortium/Symposium', ...boolDisplay('Available', 'Not mentioned') },
    has_findings:                { label: 'Findings Track', fullName: 'Findings Track (ACL-family)', ...boolDisplay('Available', 'Not mentioned') },
    has_awards:                  { label: 'Awards', fullName: 'Best Paper and Other Awards', ...boolDisplay('Available', 'Not mentioned') },

    // Inverted boolean (true = bad)
    desk_rejection: {
        label: 'Desk Rejection', fullName: 'Desk Rejection Policy',
        icon: v => v === true ? '\u26A0\uFE0F' : v === false ? '\u2713' : '?',
        statusText: v => v === true ? 'Possible' : v === false ? 'Not possible' : 'Unknown',
        cssClass: v => v === true ? 'denied' : v === false ? 'confirmed' : 'unknown',
    },
    page_limit_exclusions: {
        label: 'Page Limit Exclusions', fullName: 'Whether References/Appendices Are Excluded From Page Limit',
        ...boolDisplayInverted('Included in limit', 'Excluded from limit'),
    },

    // Enum fields
    artifact_evaluation: { label: 'Artifact Submission', fullName: 'Code/Artifact Submission Policy', ...enumDisplay(MANDATORY_OPTIONAL_NONE_DISALLOWED) },
    statements:    { label: 'Ethics', ...enumDisplay(MANDATORY_OPTIONAL_NONE) },
    llm_policy: {
        label: 'LLM Policy', fullName: 'LLM Usage Policy',
        ...enumDisplay({
            allowed:             ['\u2713', 'Allowed', 'confirmed'],
            required_disclosure: ['\u2713', 'Must Disclose', 'partial'],
            forbidden:           ['\u2717', 'Forbidden', 'denied'],
        }),
    },
    code_submission: {
        label: 'Code Submission Policy', fullName: 'Code/Implementation Submission Requirements',
        ...enumDisplay({
            required:      ['\u2713', 'Required', 'confirmed'],
            optional:      ['\u25CB', 'Optional', 'partial'],
            not_mentioned: ['\u2717', 'Not Mentioned', 'denied'],
        }),
    },
    conference_format: {
        label: 'Conference Format', fullName: 'Conference Delivery Format',
        ...enumDisplay({
            'in-person': ['\uD83C\uDFDB\uFE0F', 'In-Person', 'value'],
            'hybrid':    ['\uD83C\uDF10', 'Hybrid', 'value'],
            'virtual':   ['\uD83D\uDCBB', 'Virtual', 'value'],
        }),
    },

    // Value/string fields
    page_limit:                  valueDisplay('\uD83D\uDCC4', { labelWithValue: true, fallbackLabel: 'Page Limit' }),
    publication_venue:           { label: 'Publication Venue', fullName: 'Where Proceedings Will Be Published', ...valueDisplay('\uD83D\uDCDA', { labelWithValue: true, fallbackLabel: 'Publication Venue' }) },
    submission_system:           valueDisplay('\uD83D\uDCBB', { labelWithValue: true, fallbackLabel: 'System' }),
    conference_location:         {
        label: 'Conference Location',
        fullName: 'Physical Location of Conference',
        icon: (value) => value && value !== 'Unknown' ? '\uD83C\uDFDB\uFE0F' : '?',
        statusText: (value) => value !== 'Unknown' ? value : 'Unknown',
        cssClass: (value) => value !== 'Unknown' ? 'value' : 'unknown',
        getLabelWithValue: (value) => value !== 'Unknown' ? value : 'Conference Location',
        getDisplayValue: (conf) => conf.metadata?.location?.display || 'Unknown'
    },

    // List fields
    presentation_formats:        { label: 'Presentation Formats', fullName: 'Available Presentation Types', ...listDisplay('\uD83C\uDFA4') },

    // Date fields
    submission_deadline:    { label: 'Submission', ...valueDisplay('\uD83D\uDCC5', { formatter: formatShortDate }) },
    abstract_deadline:      { label: 'Abstract', ...valueDisplay('\uD83D\uDCDD', { formatter: formatShortDate }) },
    notification_date:      { label: 'Notification', ...valueDisplay('\uD83D\uDCEC', { formatter: formatShortDate }) },
    camera_ready_deadline:  { label: 'Camera-Ready', ...valueDisplay('\uD83D\uDCF8', { formatter: formatShortDate }) },
    conference_dates:       { label: 'Conference', ...valueDisplay('\uD83C\uDF89', { formatter: formatShortDate }) },
    rebuttal_deadline:      { label: 'Rebuttal Deadline', fullName: 'Author Rebuttal Submission Deadline', ...valueDisplay('\uD83D\uDCAC', { formatter: formatShortDate }) },
    withdrawal_deadline:    { label: 'Withdrawal Deadline', fullName: 'Last Date to Withdraw Submission', ...valueDisplay('\uD83D\uDEAB', { formatter: formatShortDate }) },
    registration_deadline:  { label: 'Registration Deadline', fullName: 'Author Registration Deadline', ...valueDisplay('\uD83C\uDFAB', { formatter: formatShortDate }) },
};


// ---- Merged definitions ----

export const RULE_DEFINITIONS = Object.fromEntries(
    Object.entries(GENERATED_SCHEMA).map(([name, base]) => [
        name,
        { ...base, ...(CUSTOM_DISPLAY_LOGIC[name] || {}) }
    ])
);

export const DATE_RULES = getDateFields(RULE_DEFINITIONS);


// ---- Tag importance (1-10, higher = more important to authors) ----

const TAG_IMPORTANCE = {
    'page_limit': 10, 'submission_deadline': 10,
    'double_blind': 9, 'template_required': 9, 'page_limit_exclusions': 9,
    'rebuttal_allowed': 8, 'concurrent_submission': 8, 'arxiv_preprint': 8, 'desk_rejection': 8,
    'llm_policy': 7, 'supplementary_material_allowed': 7,
    'notification_date': 6, 'camera_ready_deadline': 6, 'publication_venue': 6,
    'submission_system': 6, 'conference_location': 6, 'presentation_formats': 6, 'abstract_deadline': 6,
    'reciprocal_review': 5, 'open_review': 5, 'conference_dates': 5,
    'statements': 4, 'artifact_evaluation': 4, 'conference_format': 4, 'rebuttal_deadline': 4,
    'single_blind': 2,
    'workshops': 1, 'financial_aid_available': 1, 'withdrawal_deadline': 1, 'registration_deadline': 1,
    'has_workshop_proposals': 1, 'has_tutorials': 1, 'has_demos': 1, 'has_posters': 1,
    'has_industry_track': 1, 'has_position_papers': 1, 'has_student_research': 1,
    'has_doctoral_consortium': 1, 'has_findings': 1, 'has_awards': 1,
};


// ---- Sorting ----

function isUnknownValue(value) {
    return value === undefined || value === null || value === 'unknown' || value === 'not_mentioned' || value === '';
}

function getAvailabilityScore(value, type) {
    if (isUnknownValue(value)) return 0;
    if (type === 'boolean') return value === false ? 1 : 3;
    if (type === 'enum') {
        if (value === 'none' || value === 'forbidden') return 1;
        if (value === 'optional' || value === 'required_disclosure') return 2;
        if (value === 'mandatory' || value === 'allowed') return 3;
    }
    return 3;
}

function sortByImportanceAndAvailability(ruleNames, rules) {
    return ruleNames.sort((a, b) => {
        const ruleA = rules[a] || { value: 'unknown' };
        const ruleB = rules[b] || { value: 'unknown' };
        const defA = RULE_DEFINITIONS[a];
        const defB = RULE_DEFINITIONS[b];

        const availDiff = getAvailabilityScore(ruleB.value, defB?.type) - getAvailabilityScore(ruleA.value, defA?.type);
        if (availDiff !== 0) return availDiff;

        const priDiff = (TAG_IMPORTANCE[b] || 0) - (TAG_IMPORTANCE[a] || 0);
        if (priDiff !== 0) return priDiff;

        const catDiff = (defA?.category || 'z').localeCompare(defB?.category || 'z');
        if (catDiff !== 0) return catDiff;

        return a.localeCompare(b);
    });
}


// ---- Rendering ----

function normalizeRuleNames(rules) {
    return rules;
}

export function createRuleTag(ruleName, rule, definition, conf = null) {
    const value = rule.value;

    // Use custom display value if getDisplayValue is defined
    const displayValue = (definition.getDisplayValue && conf)
        ? definition.getDisplayValue(conf)
        : value;

    const icon = typeof definition.icon === 'function' ? definition.icon(displayValue) : definition.icon;
    const label = definition.getLabelWithValue
        ? definition.getLabelWithValue(displayValue)
        : (definition.formatter && displayValue !== 'unknown' ? definition.formatter(displayValue) : definition.label);
    const statusText = typeof definition.statusText === 'function' ? definition.statusText(displayValue) : definition.statusText;
    const cssClass = typeof definition.cssClass === 'function' ? definition.cssClass(displayValue) : definition.cssClass;
    const evidence = rule.evidence || '';
    const evidenceHTML = evidence
        ? `<div class="evidence-item"><p class="evidence-text">${evidence}</p></div>`
        : '<p class="no-evidence">No evidence available</p>';

    return `
        <span class="rule-tag rule-tag--${cssClass}" data-rule="${ruleName}">
            <span class="rule-tag__icon">${icon}</span>
            <span class="rule-tag__label">${label}</span>
            <div class="rule-tag-popover">
                <div class="rule-tag-popover__header">${definition.fullName}</div>
                <div class="rule-tag-popover__status">${statusText}</div>
                <div class="rule-tag-popover__evidence">${evidenceHTML}</div>
            </div>
        </span>
    `;
}

export function createRulesTags(rules, conf = null) {
    const normalized = normalizeRuleNames(rules);
    const allRules = Object.keys(normalized).filter(r => !DATE_RULES.has(r));
    const sorted = sortByImportanceAndAvailability(allRules, normalized);

    // Always put conference_location first if it exists and has a value
    const locationIndex = sorted.indexOf('conference_location');
    if (locationIndex > 0) {
        const locationRule = normalized['conference_location'];
        if (locationRule && locationRule.value && locationRule.value !== 'unknown') {
            sorted.splice(locationIndex, 1);
            sorted.unshift('conference_location');
        }
    }

    const makeTag = (name) => {
        const rule = normalized[name] || { value: 'unknown', evidence: '' };
        const def = RULE_DEFINITIONS[name];
        return def ? createRuleTag(name, rule, def, conf) : '';
    };

    const known = sorted.filter(r => !isUnknownValue((normalized[r] || {}).value));
    const unknown = sorted.filter(r => isUnknownValue((normalized[r] || {}).value));

    const knownHTML = known.map(makeTag).filter(Boolean).join('');
    const visibleUnknown = unknown.slice(0, 3);
    const hiddenUnknown = unknown.slice(3);

    const visibleHTML = visibleUnknown.map(makeTag).filter(Boolean).join('');
    let hiddenHTML = '';
    if (hiddenUnknown.length > 0) {
        const tags = hiddenUnknown.map(makeTag).filter(Boolean).join('');
        hiddenHTML = `<span class="rule-tags-hidden" style="display:none">${tags}</span>`
            + `<span class="rule-tag rule-tag--more" onclick="this.previousElementSibling.style.display='contents';this.style.display='none';if(window.relayoutMasonry)window.relayoutMasonry()">\u2026 ${hiddenUnknown.length} more</span>`;
    }
    return knownHTML + visibleHTML + hiddenHTML;
}
