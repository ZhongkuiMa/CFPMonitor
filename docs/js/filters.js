/** Filter management and event handling. */

import { ELEMENT_IDS, SEARCH_DEBOUNCE_MS } from './constants.js';

function getCheckedValues(name) {
    return Array.from(document.querySelectorAll(`input[name="${name}"]:checked`))
        .map(cb => cb.value);
}

/**
 * Set up all filter event listeners.
 * @param {Object} callbacks - { onAreaChange, onRankChange, onSearchChange, onClearFilters }
 */
export function setupAllFilters(callbacks) {
    // Area checkboxes
    document.querySelectorAll('input[name="area"]').forEach(cb => {
        cb.addEventListener('change', () => callbacks.onAreaChange(getCheckedValues('area')));
    });

    // Rank checkboxes
    document.querySelectorAll('input[name="rank"]').forEach(cb => {
        cb.addEventListener('change', () => callbacks.onRankChange(getCheckedValues('rank')));
    });

    // Search input with debounce
    const searchInput = document.getElementById(ELEMENT_IDS.SEARCH_INPUT);
    const clearSearch = document.getElementById(ELEMENT_IDS.CLEAR_SEARCH);
    if (searchInput && clearSearch) {
        let searchTimeout;
        searchInput.addEventListener('input', (e) => {
            clearTimeout(searchTimeout);
            clearSearch.style.display = e.target.value ? 'block' : 'none';
            searchTimeout = setTimeout(() => callbacks.onSearchChange(e.target.value), SEARCH_DEBOUNCE_MS);
        });
        clearSearch.addEventListener('click', () => {
            searchInput.value = '';
            clearSearch.style.display = 'none';
            callbacks.onSearchChange('');
        });
    }

    // Year single-select dropdown
    const yearSelect = document.getElementById('yearSelect');
    if (yearSelect) {
        yearSelect.addEventListener('change', (e) => {
            const value = e.target.value;
            callbacks.onYearChange(value ? [value] : []);
        });
    }

    // Month single-select dropdown
    const monthSelect = document.getElementById('monthSelect');
    if (monthSelect) {
        monthSelect.addEventListener('change', (e) => {
            const value = e.target.value;
            callbacks.onMonthChange(value ? [parseInt(value)] : []);
        });
    }

    // Country single-select dropdown
    const countrySelect = document.getElementById('countrySelect');
    if (countrySelect) {
        countrySelect.addEventListener('change', (e) => {
            const value = e.target.value;
            callbacks.onCountryChange(value ? [value] : []);
        });
    }

    // Boolean filter checkboxes
    const doubleBlindCb = document.getElementById('doubleBlindFilter');
    const rebuttalCb = document.getElementById('rebuttalFilter');
    const arxivCb = document.getElementById('arxivFilter');

    if (doubleBlindCb) {
        doubleBlindCb.addEventListener('change', (e) => callbacks.onDoubleBlindChange(e.target.checked));
    }
    if (rebuttalCb) {
        rebuttalCb.addEventListener('change', (e) => callbacks.onRebuttalChange(e.target.checked));
    }
    if (arxivCb) {
        arxivCb.addEventListener('change', (e) => callbacks.onArxivChange(e.target.checked));
    }

    // Clear all filters
    const clearBtn = document.getElementById(ELEMENT_IDS.CLEAR_FILTERS);
    if (clearBtn) {
        clearBtn.addEventListener('click', () => {
            document.querySelectorAll('.filter-bar input[type="checkbox"]').forEach(cb => { cb.checked = false; });
            const yearSelect = document.getElementById('yearSelect');
            const monthSelect = document.getElementById('monthSelect');
            const countrySelect = document.getElementById('countrySelect');
            if (yearSelect) yearSelect.selectedIndex = 0;
            if (monthSelect) monthSelect.selectedIndex = 0;
            if (countrySelect) countrySelect.selectedIndex = 0;
            callbacks.onClearFilters();
        });
    }
}
