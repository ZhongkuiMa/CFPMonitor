/** Utility functions. */

import { RANK_VALUES, DEFAULT_RANK_VALUE, MONTH_ABBR } from './constants.js';

/**
 * Format date to short display format (e.g., "Jan 27, 2025").
 * Handles date ranges, "Month DD, YYYY", and ISO formats.
 */
export function formatShortDate(dateStr) {
    if (!dateStr || dateStr === 'unknown') return 'Unknown';

    const currentYear = new Date().getFullYear();
    const currentMonth = new Date().getMonth();

    function inferYear(monthStr) {
        const idx = MONTH_ABBR.findIndex(m => m.toLowerCase() === monthStr.toLowerCase());
        return idx < currentMonth ? currentYear + 1 : currentYear;
    }

    // Date range: "July 13-19" or "July 13-19, 2025"
    const rangeMatch = dateStr.match(/([A-Za-z]+)\s+(\d+)[-\u2013](\d+)(?:,?\s+(\d{4}))?/);
    if (rangeMatch) {
        const month = rangeMatch[1].substring(0, 3);
        const year = rangeMatch[4] || inferYear(month);
        return `${month} ${rangeMatch[2]}-${rangeMatch[3]}, ${year}`;
    }

    // Single date: "Month DD, YYYY" or "Month DD"
    const singleMatch = dateStr.match(/([A-Za-z]+)\s+(\d+)(?:,?\s+(\d{4}))?/);
    if (singleMatch) {
        const month = singleMatch[1].substring(0, 3);
        const year = singleMatch[3] || inferYear(month);
        return `${month} ${singleMatch[2]}, ${year}`;
    }

    // ISO: "YYYY-MM-DD"
    const isoMatch = dateStr.match(/(\d{4})-(\d{2})-(\d{2})/);
    if (isoMatch) {
        const date = new Date(dateStr);
        return `${MONTH_ABBR[date.getMonth()]} ${date.getDate()}, ${date.getFullYear()}`;
    }

    return dateStr;
}

/** Escape HTML special characters to prevent XSS. */
export function escapeHtml(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

/** Get numeric rank value for sorting (lower is better). */
function getRankValue(conference) {
    const rank = conference.metadata?.rank?.ccf || '-';
    return RANK_VALUES[rank] || DEFAULT_RANK_VALUE;
}

/** Get sort comparator function by name. */
export function getSortComparator(sortBy) {
    switch (sortBy) {
        case 'name-asc':
            return (a, b) => (a.conference || '').toLowerCase().localeCompare((b.conference || '').toLowerCase());
        case 'name-desc':
            return (a, b) => (b.conference || '').toLowerCase().localeCompare((a.conference || '').toLowerCase());
        case 'rank':
            return (a, b) => getRankValue(a) - getRankValue(b);
        case 'completeness':
            return (a, b) => (b.completeness_percent || 0) - (a.completeness_percent || 0);
        case 'updated':
            return (a, b) => (b.updated_at || '').localeCompare(a.updated_at || '');
        case 'date':
        default:
            return (a, b) => (a.metadata?.conf_date || 0) - (b.metadata?.conf_date || 0);
    }
}

/**
 * Extract unique countries from conference data for filter dropdown.
 * @param {Array} conferences - Array of conference objects
 * @returns {Array} Sorted array of country names
 */
export function getUniqueCountries(conferences) {
    const countries = new Set();

    conferences.forEach(conf => {
        const country = conf.metadata?.location?.country;
        if (country && country !== 'Unknown') {
            countries.add(country);
        }
    });

    return Array.from(countries).sort((a, b) => a.localeCompare(b));
}
