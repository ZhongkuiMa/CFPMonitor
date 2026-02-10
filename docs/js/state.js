/** Application state management with observable pattern. */

import { getSortComparator } from './utils.js';
import { BATCH_SIZE, STORAGE_KEY_SORT, DEFAULT_SORT } from './constants.js';

export class AppState {
    constructor(initialData) {
        this.allData = [...initialData];
        this.filteredData = [...initialData];
        this.renderedCount = 0;
        this.currentSort = localStorage.getItem(STORAGE_KEY_SORT) || DEFAULT_SORT;
        this.activeFilters = {
            areas: [],
            ranks: [],
            search: '',
            years: [],
            months: [],
            countries: [],
            doubleBlind: false,
            rebuttal: false,
            arxiv: false
        };
        this.listeners = new Map();
    }

    subscribe(event, callback) {
        if (!this.listeners.has(event)) this.listeners.set(event, []);
        this.listeners.get(event).push(callback);
    }

    notify(event) {
        (this.listeners.get(event) || []).forEach(cb => cb(this));
    }

    updateSort(sortMethod) {
        this.currentSort = sortMethod;
        localStorage.setItem(STORAGE_KEY_SORT, sortMethod);
        this.applySort();
        this.notify('sort-changed');
    }

    applySort() {
        this.filteredData.sort(getSortComparator(this.currentSort));
    }

    updateSearch(query) {
        this.activeFilters.search = query;
        this.applyFilters();
        this.notify('filters-changed');
    }

    updateAreaFilters(areas) {
        this.activeFilters.areas = areas;
        this.applyFilters();
        this.notify('filters-changed');
    }

    updateRankFilters(ranks) {
        this.activeFilters.ranks = ranks;
        this.applyFilters();
        this.notify('filters-changed');
    }

    updateYearFilters(years) {
        this.activeFilters.years = years;
        this.applyFilters();
        this.notify('filters-changed');
    }

    updateMonthFilters(months) {
        this.activeFilters.months = months.map(m => parseInt(m));
        this.applyFilters();
        this.notify('filters-changed');
    }

    updateCountryFilters(countries) {
        this.activeFilters.countries = countries;
        this.applyFilters();
        this.notify('filters-changed');
    }

    updateDoubleBlindFilter(enabled) {
        this.activeFilters.doubleBlind = enabled;
        this.applyFilters();
        this.notify('filters-changed');
    }

    updateRebuttalFilter(enabled) {
        this.activeFilters.rebuttal = enabled;
        this.applyFilters();
        this.notify('filters-changed');
    }

    updateArxivFilter(enabled) {
        this.activeFilters.arxiv = enabled;
        this.applyFilters();
        this.notify('filters-changed');
    }

    clearFilters() {
        this.activeFilters = {
            areas: [],
            ranks: [],
            search: '',
            years: [],
            months: [],
            countries: [],
            doubleBlind: false,
            rebuttal: false,
            arxiv: false
        };
        this.applyFilters();
        this.notify('filters-changed');
    }

    applyFilters() {
        this.filteredData = this.allData.filter(conf => {
            if (this.activeFilters.search) {
                const q = this.activeFilters.search.toLowerCase();
                const name = (conf.conference || '').toLowerCase();
                const full = (conf.metadata?.name || '').toLowerCase();
                if (!name.includes(q) && !full.includes(q)) return false;
            }
            if (this.activeFilters.areas.length > 0) {
                if (!this.activeFilters.areas.includes(conf.metadata?.area || 'Other')) return false;
            }
            if (this.activeFilters.ranks.length > 0) {
                if (!this.activeFilters.ranks.includes(conf.metadata?.rank?.ccf || '-')) return false;
            }
            // Year filter
            if (this.activeFilters.years.length > 0) {
                if (!this.activeFilters.years.includes(String(conf.year))) return false;
            }
            // Month filter
            if (this.activeFilters.months.length > 0) {
                const confMonth = conf.metadata?.conf_date;
                if (!this.activeFilters.months.includes(confMonth)) return false;
            }
            // Country filter (hierarchical: selecting "China" also matches "Hong Kong, China" etc.)
            if (this.activeFilters.countries.length > 0) {
                const confCountry = conf.metadata?.location?.country;
                if (!this.activeFilters.countries.some(selected =>
                    confCountry === selected ||
                    confCountry?.endsWith(', ' + selected)
                )) return false;
            }
            // Double-blind filter
            if (this.activeFilters.doubleBlind) {
                if (conf.rules?.double_blind?.value !== true) return false;
            }
            // Rebuttal filter
            if (this.activeFilters.rebuttal) {
                if (conf.rules?.rebuttal_allowed?.value !== true) return false;
            }
            // arXiv filter
            if (this.activeFilters.arxiv) {
                if (conf.rules?.arxiv_preprint?.value !== true) return false;
            }
            return true;
        });
        this.applySort();
    }

    getNextBatch() {
        const batch = this.filteredData.slice(this.renderedCount, this.renderedCount + BATCH_SIZE);
        this.renderedCount += batch.length;
        return batch;
    }

    hasMore() {
        return this.renderedCount < this.filteredData.length;
    }

    resetRendered() {
        this.renderedCount = 0;
    }

    getFilterCount() {
        return this.filteredData.length;
    }
}
