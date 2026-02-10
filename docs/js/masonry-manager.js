/** Masonry layout manager. Masonry.js loaded via CDN as window.Masonry. */

export class MasonryManager {
    constructor(containerSelector, itemSelector) {
        this.containerSelector = containerSelector;
        this.itemSelector = itemSelector;
        this.masonry = null;
    }

    init() {
        const container = document.querySelector(this.containerSelector);
        if (!container || typeof window.Masonry === 'undefined') return;

        this.masonry = new window.Masonry(container, {
            itemSelector: this.itemSelector,
            columnWidth: this._getColumnWidth(),
            gutter: 16,
            fitWidth: true,
            transitionDuration: 0,
            initLayout: false,
        });

        let resizeTimer;
        window.addEventListener('resize', () => {
            clearTimeout(resizeTimer);
            resizeTimer = setTimeout(() => {
                if (this.masonry) {
                    this.masonry.options.columnWidth = this._getColumnWidth();
                    this.layout();
                }
            }, 150);
        });
    }

    _getColumnWidth() {
        const width = window.innerWidth;
        const padding = 32;  // Total horizontal padding
        const gap = 16;      // Gap between cards

        // Calculate optimal column width based on viewport
        if (width < 640) {
            // Mobile: single column, full width
            return width - padding;
        } else if (width < 900) {
            // Small tablet: 1-2 columns with adaptive width
            return Math.max(260, Math.floor((width - padding - gap) / 2));
        } else if (width < 1200) {
            // Tablet: 2-3 columns with adaptive width
            return Math.max(280, Math.floor((width - padding - gap * 2) / 3));
        } else {
            // Desktop: 3-4 columns calculated based on available space
            const columns = Math.floor((width - padding) / 340);
            return Math.floor((width - padding - gap * (columns - 1)) / columns);
        }
    }

    layout() {
        if (this.masonry) {
            this.masonry.reloadItems();
            this.masonry.layout();
        }
    }

    isInitialized() {
        return this.masonry !== null;
    }
}
