/** CFPMonitor - Main application entry point. */

import { AppState } from './js/state.js';
import { renderCards, appendCards, updateResultCount } from './js/cards.js';
import { setupAllFilters } from './js/filters.js';
import { getUniqueCountries } from './js/utils.js';
import { ELEMENT_IDS, MODAL_DISPLAY } from './js/constants.js';
import { MasonryManager } from './js/masonry-manager.js';
import { ErrorHandler } from './js/error-handler.js';

let appState;
let masonryManager;
let errorHandler;

function relayout() {
    requestAnimationFrame(() => {
        if (masonryManager?.isInitialized()) masonryManager.layout();
    });
}

function initFilterToggle() {
    const toggleBtn = document.getElementById('filterToggle');
    const filterBar = document.getElementById('filterBar');

    if (!toggleBtn || !filterBar) return;

    toggleBtn.addEventListener('click', () => {
        const isActive = filterBar.classList.toggle('active');
        toggleBtn.classList.toggle('active', isActive);
        toggleBtn.setAttribute('aria-expanded', isActive);
    });
}

function renderFirstBatch() {
    const grid = document.getElementById(ELEMENT_IDS.CARDS_GRID);
    renderCards(appState.getNextBatch(), grid);
    relayout();
    updateResultCount(appState.getFilterCount(), document.getElementById(ELEMENT_IDS.RESULT_COUNT));
}

document.addEventListener('DOMContentLoaded', () => {
    try {
        // Initialize error handler
        errorHandler = new ErrorHandler();

        // Show loading state
        errorHandler.showLoading();

        // Initialize data with error handling
        const conferenceData = errorHandler.initializeData();

        if (conferenceData.length === 0) {
            errorHandler.showError('No conference data available. Please try again later.');
            return;
        }

        // Initialize app state
        appState = new AppState(conferenceData);
        masonryManager = new MasonryManager('#cardsGrid', '.conference-card');
        masonryManager.init();

        // Initialize filter toggle for mobile
        initFilterToggle();

        const sortSelect = document.getElementById(ELEMENT_IDS.SORT_SELECT);
        if (sortSelect) sortSelect.value = appState.currentSort;

        // Populate country dropdown dynamically
        const countrySelect = document.getElementById('countrySelect');
        if (countrySelect) {
            const countries = getUniqueCountries(conferenceData);
            countries.forEach(country => {
                const option = document.createElement('option');
                option.value = country;
                option.textContent = country;
                countrySelect.appendChild(option);
            });
        }

        // Try to restore saved filter state (simple localStorage)
        const savedFilters = localStorage.getItem('cfpmonitor_filters');
        if (savedFilters) {
            try {
                const filters = JSON.parse(savedFilters);
                // Restore UI checkboxes
                if (filters.areas) {
                    filters.areas.forEach(area => {
                        const checkbox = document.querySelector(`input[name="area"][value="${area}"]`);
                        if (checkbox) checkbox.checked = true;
                    });
                }
                if (filters.ranks) {
                    filters.ranks.forEach(rank => {
                        const checkbox = document.querySelector(`input[name="rank"][value="${rank}"]`);
                        if (checkbox) checkbox.checked = true;
                    });
                }
                if (filters.search) {
                    const searchInput = document.getElementById(ELEMENT_IDS.SEARCH_INPUT);
                    if (searchInput) searchInput.value = filters.search;
                }
                // Restore year filter
                if (filters.years && filters.years.length > 0) {
                    const yearSelect = document.getElementById('yearSelect');
                    if (yearSelect) yearSelect.value = filters.years[0];
                }
                // Restore month filter
                if (filters.months && filters.months.length > 0) {
                    const monthSelect = document.getElementById('monthSelect');
                    if (monthSelect) monthSelect.value = filters.months[0];
                }
                // Restore country filter
                if (filters.countries && filters.countries.length > 0) {
                    const countrySelect = document.getElementById('countrySelect');
                    if (countrySelect) countrySelect.value = filters.countries[0];
                }
                // Apply filters to state
                Object.assign(appState.activeFilters, filters);
            } catch (e) {
                console.warn('Failed to restore filters:', e);
            }
        }

        appState.applySort();
        appState.applyFilters();

    // State change listeners
    appState.subscribe('filters-changed', () => {
        appState.resetRendered();
        renderFirstBatch();
        // Save filter state to localStorage (simple)
        try {
            localStorage.setItem('cfpmonitor_filters', JSON.stringify(appState.activeFilters));
        } catch (e) {
            console.warn('Failed to save filters:', e);
        }
    });
    appState.subscribe('sort-changed', () => {
        appState.resetRendered();
        renderFirstBatch();
    });

    // UI listeners
    if (sortSelect) {
        sortSelect.addEventListener('change', (e) => appState.updateSort(e.target.value));
    }

    setupAllFilters({
        onAreaChange: (areas) => appState.updateAreaFilters(areas),
        onRankChange: (ranks) => appState.updateRankFilters(ranks),
        onSearchChange: (query) => appState.updateSearch(query),
        onYearChange: (years) => appState.updateYearFilters(years),
        onMonthChange: (months) => appState.updateMonthFilters(months),
        onCountryChange: (countries) => appState.updateCountryFilters(countries),
        onDoubleBlindChange: (enabled) => appState.updateDoubleBlindFilter(enabled),
        onRebuttalChange: (enabled) => appState.updateRebuttalFilter(enabled),
        onArxivChange: (enabled) => appState.updateArxivFilter(enabled),
        onClearFilters: () => {
            appState.clearFilters();
            const searchInput = document.getElementById(ELEMENT_IDS.SEARCH_INPUT);
            if (searchInput) {
                searchInput.value = '';
                const clearBtn = document.getElementById(ELEMENT_IDS.CLEAR_SEARCH);
                if (clearBtn) clearBtn.style.display = 'none';
            }
        }
    });

    // Infinite scroll
    const sentinel = document.getElementById(ELEMENT_IDS.SCROLL_SENTINEL);
    if (sentinel) {
        new IntersectionObserver(entries => {
            if (entries[0].isIntersecting && appState.hasMore()) {
                appendCards(appState.getNextBatch(), document.getElementById(ELEMENT_IDS.CARDS_GRID));
                relayout();
            }
        }, { rootMargin: '200px' }).observe(sentinel);
    }

    // Expose masonry re-layout for inline handlers (rule tag expand)
    window.relayoutMasonry = relayout;

    // Reposition popovers that would overflow viewport edges
    document.addEventListener('mouseenter', (e) => {
        const tag = e.target.closest('.rule-tag');
        if (!tag) return;
        const popover = tag.querySelector('.rule-tag-popover');
        if (!popover) return;

        // Reset to default centered position
        popover.style.left = '50%';
        popover.style.transform = 'translateX(-50%) scale(1)';

        const rect = popover.getBoundingClientRect();
        const margin = 8;

        if (rect.left < margin) {
            // Overflows left edge
            const tagRect = tag.getBoundingClientRect();
            const shift = margin - rect.left;
            popover.style.left = `calc(50% + ${shift}px)`;
        } else if (rect.right > window.innerWidth - margin) {
            // Overflows right edge
            const shift = rect.right - (window.innerWidth - margin);
            popover.style.left = `calc(50% - ${shift}px)`;
        }
    }, true);

        renderFirstBatch();

    } catch (error) {
        console.error('Application initialization error:', error);
        if (errorHandler) {
            errorHandler.handleError(error, 'Initialization');
        } else {
            document.getElementById('cardsGrid').innerHTML = `
                <div class="error-state">
                    <h3>Failed to load application</h3>
                    <p>${error.message}</p>
                    <button onclick="location.reload()">Reload</button>
                </div>
            `;
        }
    }
});

// Modal
window.openModal = function(ruleName, conf) {
    const modal = document.getElementById(ELEMENT_IDS.EVIDENCE_MODAL);
    const title = document.getElementById(ELEMENT_IDS.MODAL_TITLE);
    const body = document.getElementById(ELEMENT_IDS.MODAL_BODY);
    if (!modal || !title || !body) return;

    const rule = conf.rules?.[ruleName] || {};
    title.textContent = `Evidence: ${ruleName.replace(/_/g, ' ').toUpperCase()}`;

    const evidence = rule.evidence || '';
    body.innerHTML = evidence
        ? `<div class="evidence-item"><p class="evidence-text">${evidence}</p></div>`
        : '<p class="no-evidence">No evidence available for this rule.</p>';

    modal.style.display = MODAL_DISPLAY.SHOW;
};

window.closeModal = function() {
    const modal = document.getElementById(ELEMENT_IDS.EVIDENCE_MODAL);
    if (modal) modal.style.display = MODAL_DISPLAY.HIDE;
};

window.addEventListener('click', (e) => {
    if (e.target === document.getElementById(ELEMENT_IDS.EVIDENCE_MODAL)) window.closeModal();
});

window.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') window.closeModal();
});
