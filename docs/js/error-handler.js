/** Simple error handling and loading states */

export class ErrorHandler {
    /**
     * Show loading state
     */
    showLoading() {
        const container = document.getElementById('cardsGrid');
        if (container) {
            container.innerHTML = `
                <div class="loading-state">
                    <div class="loading-spinner"></div>
                    <p>Loading conferences...</p>
                </div>
            `;
        }
    }

    /**
     * Show error state
     */
    showError(message = 'Failed to load conference data') {
        const container = document.getElementById('cardsGrid');
        if (container) {
            container.innerHTML = `
                <div class="error-state">
                    <div class="error-icon">⚠️</div>
                    <h3>Something went wrong</h3>
                    <p>${message}</p>
                    <button onclick="location.reload()" class="retry-btn">Reload</button>
                </div>
            `;
        }
    }

    /**
     * Initialize conference data
     */
    initializeData() {
        try {
            if (!window.conferenceData || !Array.isArray(window.conferenceData)) {
                console.error('Invalid conference data');
                return [];
            }
            console.log(`✓ Loaded ${window.conferenceData.length} conferences`);
            return window.conferenceData;
        } catch (error) {
            console.error('Error loading data:', error);
            this.showError('Failed to load data. Please refresh the page.');
            return [];
        }
    }

    /**
     * Handle errors
     */
    handleError(error, context = 'App') {
        console.error(`${context} error:`, error);
        this.showError(error.message || 'An error occurred');
    }
}
