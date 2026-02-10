/** Application constants. */

export const BATCH_SIZE = 20;
export const SEARCH_DEBOUNCE_MS = 300;
export const STORAGE_KEY_SORT = 'cfpmonitor-sort';
export const DEFAULT_SORT = 'date';

export const RANK_VALUES = { 'A': 1, 'B': 2, 'C': 3, '-': 999 };
export const DEFAULT_RANK_VALUE = 999;

export const MONTH_ABBR = [
    'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
    'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'
];

export const MODAL_DISPLAY = { SHOW: 'block', HIDE: 'none' };

export const CSS_CLASSES = {
    CONFIRMED: 'confirmed',
    DENIED: 'denied',
    PARTIAL: 'partial',
    UNKNOWN: 'unknown',
    VALUE: 'value',
    RANK_A: 'rank-a',
    RANK_B: 'rank-b',
    RANK_C: 'rank-c',
    RANK_NONE: 'rank-none',
    CARD: 'conference-card',
    CARD_HEADER: 'card-header',
    CARD_BODY: 'card-body',
    RULE_TAG: 'rule-tag',
    EVIDENCE_BADGE: 'evidence-badge',
    NO_RESULTS: 'no-results'
};

export const ELEMENT_IDS = {
    CARDS_GRID: 'cardsGrid',
    SCROLL_SENTINEL: 'scrollSentinel',
    SEARCH_INPUT: 'searchInput',
    CLEAR_SEARCH: 'clearSearch',
    SORT_SELECT: 'sortSelect',
    CLEAR_FILTERS: 'clearFilters',
    RESULT_COUNT: 'resultCount',
    EVIDENCE_MODAL: 'evidenceModal',
    MODAL_TITLE: 'modalTitle',
    MODAL_BODY: 'modalBody'
};

export const ERROR_MESSAGES = {
    NO_DATA: 'No conference data available.',
    LOAD_FAILED: 'Failed to load conference data.',
    NO_RESULTS: 'No conferences found matching your filters.'
};
