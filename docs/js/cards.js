/** Conference card rendering. */

import { createRulesTags } from './rules.js';
import { escapeHtml, formatShortDate } from './utils.js';
import { CSS_CLASSES, ERROR_MESSAGES } from './constants.js';

// Date fields shown in the card footer, in chronological order
const FOOTER_DATES = [
    { key: 'abstract_deadline',     icon: '\uD83D\uDCDD', label: 'Abstract Deadline' },
    { key: 'submission_deadline',   icon: '\uD83D\uDCE4', label: 'Submission Deadline' },
    { key: 'rebuttal_deadline',     icon: '\uD83D\uDCAC', label: 'Rebuttal Deadline' },
    { key: 'notification_date',     icon: '\uD83D\uDCEC', label: 'Notification Date' },
    { key: 'camera_ready_deadline', icon: '\uD83D\uDCF8', label: 'Camera-Ready Deadline' },
    { key: 'conference_dates',      icon: '\uD83C\uDF89', label: 'Conference Dates' },
    { key: 'withdrawal_deadline',   icon: '\uD83D\uDEAB', label: 'Withdrawal Deadline' },
    { key: 'registration_deadline', icon: '\uD83C\uDFAB', label: 'Registration Deadline' },
];

function getRuleValue(rules, frontendName) {
    return rules[frontendName];
}

export function renderCard(conf) {
    const name = escapeHtml(conf.metadata?.short || conf.conference || 'Unknown');
    const fullName = escapeHtml(conf.metadata?.name || name);
    const area = escapeHtml(conf.metadata?.area || 'Other');
    const ccfRank = escapeHtml(conf.metadata?.rank?.ccf || '-');
    const coreRank = escapeHtml(conf.metadata?.rank?.core || '-');
    const thcplRank = escapeHtml(conf.metadata?.rank?.thcpl || '-');
    const year = conf.year || new Date().getFullYear();
    const confUrl = conf.homepage || '#';
    const rulesTags = createRulesTags(conf.rules || {}, conf);

    const ccfClass = ccfRank === 'A' ? CSS_CLASSES.RANK_A :
                     ccfRank === 'B' ? CSS_CLASSES.RANK_B :
                     ccfRank === 'C' ? CSS_CLASSES.RANK_C :
                     CSS_CLASSES.RANK_NONE;

    const footerDatesHTML = FOOTER_DATES
        .map(({ key, icon, label }) => {
            const value = getRuleValue(conf.rules || {}, key)?.value;
            if (!value || value === 'unknown' || value === 'Unknown') return '';
            return `<div class="footer-date"><strong>${icon} ${label}:</strong> ${formatShortDate(value)}</div>`;
        })
        .filter(Boolean)
        .join('');

    return `
        <div class="${CSS_CLASSES.CARD}">
            <div class="${CSS_CLASSES.CARD_HEADER}">
                <h3 class="card-title">${name} ${year}</h3>
                <a href="${confUrl}" target="_blank" rel="noopener noreferrer" class="card-subtitle-link">
                    ${fullName}<svg class="external-link-icon" width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M10 6.5v4a.5.5 0 01-.5.5h-8a.5.5 0 01-.5-.5v-8a.5.5 0 01.5-.5H6"/><path d="M7 1h4v4M11 1L5.5 6.5"/></svg>
                </a>
                <div class="card-badges-row">
                    <span class="area-badge">${area}</span>
                    ${ccfRank !== '-' ? `<span class="rank-badge ${ccfClass}" title="CCF Rank">CCF-${ccfRank}</span>` : ''}
                    ${coreRank !== '-' ? `<span class="rank-badge rank-core" title="CORE Rank">CORE-${coreRank}</span>` : ''}
                    ${thcplRank !== '-' ? `<span class="rank-badge rank-thcpl" title="THCPL Rank">THCPL-${thcplRank}</span>` : ''}
                </div>
            </div>
            <div class="${CSS_CLASSES.CARD_BODY}">
                <div class="rules-container">${rulesTags}</div>
            </div>
            ${footerDatesHTML ? `
            <div class="card-footer">
                <div class="footer-dates">${footerDatesHTML}</div>
            </div>` : ''}
        </div>
    `;
}

export function renderCards(conferences, container) {
    if (!container) return;
    if (conferences.length === 0) {
        container.innerHTML = `<div class="${CSS_CLASSES.NO_RESULTS}"><p>${ERROR_MESSAGES.NO_RESULTS}</p><p>Try adjusting your search or filters.</p></div>`;
        return;
    }
    container.innerHTML = conferences.map(renderCard).join('');
}

export function appendCards(conferences, container) {
    if (!container || conferences.length === 0) return;
    container.insertAdjacentHTML('beforeend', conferences.map(renderCard).join(''));
}

export function updateResultCount(count, element) {
    if (element) element.textContent = count;
}
