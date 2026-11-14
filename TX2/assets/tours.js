/**
 * TX2 Fansite - Tours Controller
 * Marks past tour dates, highlights the next upcoming show per language,
 * and centers the viewport on the upcoming show.
 */
(function () {
    'use strict';

    function getLocalTodayISO() {
        const now = new Date();
        const year = String(now.getFullYear());
        const month = String(now.getMonth() + 1).padStart(2, '0');
        const day = String(now.getDate()).padStart(2, '0');
        return year + '-' + month + '-' + day;
    }

    function updateTourItems(todayISO) {
        const containers = [
            { selector: '.content-en', badgeText: 'NEXT' },
            { selector: '.content-pl', badgeText: 'NAJBLIZSZY' }
        ];

        containers.forEach(function (cfg) {
            const container = document.querySelector(cfg.selector);
            if (!container) {
                return;
            }

            const items = container.querySelectorAll('.tour-item[data-date]');
            let nextEl = null;

            items.forEach(function (el) {
                const compareDate = el.dataset.endDate || el.dataset.date;
                if (compareDate < todayISO) {
                    el.classList.add('tour-past');
                    el.classList.remove('tour-next');
                    const existingBadges = el.querySelectorAll('.tour-next-badge');
                    existingBadges.forEach(function (badge) {
                        badge.remove();
                    });
                } else {
                    el.classList.remove('tour-past');
                    if (!nextEl) {
                        nextEl = el;
                    }
                }
            });

            if (nextEl) {
                nextEl.classList.add('tour-next');
                if (!nextEl.querySelector('.tour-next-badge')) {
                    const badge = document.createElement('span');
                    badge.className = 'tour-next-badge';
                    badge.textContent = cfg.badgeText;
                    nextEl.prepend(badge);
                }
            }
        });
    }

    function centerNextShow() {
        const langPl = document.getElementById('lang-toggle-pl');
        const isPl = Boolean(langPl && langPl.checked);
        const containerSelector = isPl ? '.content-pl' : '.content-en';
        const container = document.querySelector(containerSelector);
        if (!container) {
            return;
        }

        const nextEl = container.querySelector('.tour-next');
        if (!nextEl) {
            return;
        }

        const rect = nextEl.getBoundingClientRect();
        const top = Math.max(
            0,
            window.scrollY + rect.top - (window.innerHeight / 2) + (rect.height / 2)
        );
        const prefersReduced = window.matchMedia &&
            window.matchMedia('(prefers-reduced-motion: reduce)').matches;

        window.scrollTo({
            top: top,
            behavior: prefersReduced ? 'auto' : 'smooth'
        });
    }

    function initTours() {
        const todayISO = getLocalTodayISO();
        updateTourItems(todayISO);

        const hash = window.location.hash;
        if (hash === '' || hash === '#upcoming') {
            setTimeout(function () {
                requestAnimationFrame(centerNextShow);
            }, 30);
        }

        const langEn = document.getElementById('lang-toggle-en');
        const langPl = document.getElementById('lang-toggle-pl');

        if (langEn) {
            langEn.addEventListener('change', function () {
                requestAnimationFrame(centerNextShow);
            });
        }

        if (langPl) {
            langPl.addEventListener('change', function () {
                requestAnimationFrame(centerNextShow);
            });
        }

        document.addEventListener('click', function (event) {
            const link = event.target.closest('a[href]');
            if (!link) {
                return;
            }

            const href = link.getAttribute('href') || '';
            if (href === '#upcoming' || /(?:^|\/)tours\.html#upcoming$/.test(href)) {
                event.preventDefault();
                requestAnimationFrame(centerNextShow);
            }
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initTours);
    } else {
        initTours();
    }
})();
