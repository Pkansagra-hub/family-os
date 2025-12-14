/**
 * Theme Management Service
 *
 * Handles light/dark theme switching with:
 * - CSS custom properties for theming
 * - localStorage persistence
 * - System theme preference detection
 * - Smooth transitions
 *
 * Usage:
 *   import { ThemeManager } from './theme.js';
 *   const themeManager = new ThemeManager();
 *   themeManager.toggleTheme();
 */

export class ThemeManager {
    constructor() {
        this.STORAGE_KEY = 'concierge-theme';
        this.THEMES = {
            LIGHT: 'light',
            DARK: 'dark'
        };

        // Initialize theme on creation
        this.init();
    }

    /**
     * Initialize theme system
     * Detects system preference or loads from localStorage
     */
    init() {
        const savedTheme = this.getSavedTheme();
        const systemTheme = this.getSystemTheme();

        // Priority: saved preference > system preference > default (light)
        const initialTheme = savedTheme || systemTheme || this.THEMES.LIGHT;

        this.applyTheme(initialTheme, false); // No transition on init

        // Listen for system theme changes
        this.watchSystemTheme();
    }

    /**
     * Get saved theme from localStorage
     * @returns {string|null} Theme name or null
     */
    getSavedTheme() {
        try {
            return localStorage.getItem(this.STORAGE_KEY);
        } catch (error) {
            console.warn('Could not access localStorage:', error);
            return null;
        }
    }

    /**
     * Get system theme preference
     * @returns {string} 'dark' or 'light'
     */
    getSystemTheme() {
        if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
            return this.THEMES.DARK;
        }
        return this.THEMES.LIGHT;
    }

    /**
     * Watch for system theme changes
     */
    watchSystemTheme() {
        if (!window.matchMedia) return;

        const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');

        // Use modern API if available, fallback to deprecated one
        const handler = (e) => {
            // Only auto-switch if user hasn't set a preference
            if (!this.getSavedTheme()) {
                const newTheme = e.matches ? this.THEMES.DARK : this.THEMES.LIGHT;
                this.applyTheme(newTheme, true);
            }
        };

        if (mediaQuery.addEventListener) {
            mediaQuery.addEventListener('change', handler);
        } else if (mediaQuery.addListener) {
            // Fallback for older browsers
            mediaQuery.addListener(handler);
        }
    }

    /**
     * Get current active theme
     * @returns {string} Current theme name
     */
    getCurrentTheme() {
        return document.documentElement.getAttribute('data-theme') || this.THEMES.LIGHT;
    }

    /**
     * Apply theme to document
     * @param {string} theme - Theme name ('light' or 'dark')
     * @param {boolean} withTransition - Enable smooth transition
     */
    applyTheme(theme, withTransition = true) {
        const root = document.documentElement;

        // Add transition class if needed
        if (withTransition) {
            root.classList.add('theme-transition');

            // Remove transition class after animation completes
            setTimeout(() => {
                root.classList.remove('theme-transition');
            }, 300);
        }

        // Apply theme attribute
        root.setAttribute('data-theme', theme);

        // Update meta theme-color for mobile browsers
        this.updateMetaThemeColor(theme);

        // Dispatch custom event for components to react
        window.dispatchEvent(new CustomEvent('themechange', {
            detail: { theme }
        }));
    }

    /**
     * Update meta theme-color tag
     * @param {string} theme - Theme name
     */
    updateMetaThemeColor(theme) {
        let metaThemeColor = document.querySelector('meta[name="theme-color"]');

        if (!metaThemeColor) {
            metaThemeColor = document.createElement('meta');
            metaThemeColor.name = 'theme-color';
            document.head.appendChild(metaThemeColor);
        }

        // Set color based on theme
        const color = theme === this.THEMES.DARK ? '#1a1a1a' : '#667eea';
        metaThemeColor.setAttribute('content', color);
    }

    /**
     * Save theme preference to localStorage
     * @param {string} theme - Theme name
     */
    saveTheme(theme) {
        try {
            localStorage.setItem(this.STORAGE_KEY, theme);
        } catch (error) {
            console.warn('Could not save theme to localStorage:', error);
        }
    }

    /**
     * Toggle between light and dark themes
     */
    toggleTheme() {
        const currentTheme = this.getCurrentTheme();
        const newTheme = currentTheme === this.THEMES.DARK
            ? this.THEMES.LIGHT
            : this.THEMES.DARK;

        this.applyTheme(newTheme, true);
        this.saveTheme(newTheme);

        return newTheme;
    }

    /**
     * Set specific theme
     * @param {string} theme - Theme name ('light' or 'dark')
     */
    setTheme(theme) {
        if (theme !== this.THEMES.LIGHT && theme !== this.THEMES.DARK) {
            console.warn(`Invalid theme: ${theme}`);
            return;
        }

        this.applyTheme(theme, true);
        this.saveTheme(theme);
    }

    /**
     * Check if dark mode is active
     * @returns {boolean} True if dark mode
     */
    isDarkMode() {
        return this.getCurrentTheme() === this.THEMES.DARK;
    }

    /**
     * Clear saved theme preference
     */
    clearPreference() {
        try {
            localStorage.removeItem(this.STORAGE_KEY);
        } catch (error) {
            console.warn('Could not clear theme preference:', error);
        }
    }
}

// Export singleton instance for convenience
export const themeManager = new ThemeManager();

// Make available globally for debugging
if (typeof window !== 'undefined') {
    window.themeManager = themeManager;
}
