/**
 * TX2 Fansite - Language Controller
 * Manages session-level language persistence and browser language detection.
 * Default: English (EN); Auto-switch: Polish (PL) if browser language reports Polish.
 */
(function () {
    'use strict';

    function initLanguage() {
        const langEn = document.getElementById('lang-toggle-en');
        const langPl = document.getElementById('lang-toggle-pl');

        if (!langEn || !langPl) {
            return;
        }

        let savedLang = null;
        try {
            savedLang = sessionStorage.getItem('preferred_lang');
        } catch (e) {
            // Storage access restricted or disabled
        }

        if (savedLang === 'pl') {
            langPl.checked = true;
            document.documentElement.lang = 'pl';
        } else if (savedLang === 'en') {
            langEn.checked = true;
            document.documentElement.lang = 'en';
        } else {
            // First visit in current session: detect browser language preference
            const browserLang = (navigator.languages && navigator.languages[0]) || navigator.language || '';
            if (browserLang.toLowerCase().startsWith('pl')) {
                langPl.checked = true;
                document.documentElement.lang = 'pl';
            } else {
                langEn.checked = true;
                document.documentElement.lang = 'en';
            }
        }

        // Listen for user changes to maintain selection across subpages
        langEn.addEventListener('change', function () {
            if (langEn.checked) {
                try {
                    sessionStorage.setItem('preferred_lang', 'en');
                } catch (e) {}
                document.documentElement.lang = 'en';
            }
        });

        langPl.addEventListener('change', function () {
            if (langPl.checked) {
                try {
                    sessionStorage.setItem('preferred_lang', 'pl');
                } catch (e) {}
                document.documentElement.lang = 'pl';
            }
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initLanguage);
    } else {
        initLanguage();
    }
})();