// file: data/web/static/scripts/mobile.js

(function() {
    const NAV_SELECTOR = 'aside';
    const LAYOUT_SELECTOR = '.layout';
    const ROLL_CLASS = 'nav-rolled';
    const HANDLE_ID = 'nav-handle';
    const SPLITTER_ID = 'nav-splitter';
    let isOpen = true;
    let isMobileMode = false;

    // Helper: Are we in mobile mode?
    function isMobile() {
        return window.innerWidth <= 650;
    }

    // Main nav open/close logic
    function rollNav(out = true) {
        const layout = document.querySelector(LAYOUT_SELECTOR);
        if (!layout) return;
        if (out) {
            layout.classList.add(ROLL_CLASS);
            isOpen = false;
            if (isMobile()) createMobileHandle();
            else createDesktopHandle();
        } else {
            layout.classList.remove(ROLL_CLASS);
            isOpen = true;
            removeAllHandles();
        }
    }

    // --- Handles ---
    function createMobileHandle() {
        if (document.getElementById(HANDLE_ID)) return;
        const handle = document.createElement('div');
        handle.id = HANDLE_ID;
        tab.innerHTML = `
            <svg width="44" height="54" viewBox="0 0 44 54" fill="none">
                <rect x="0" y="0" width="38" height="54" rx="15"
                    fill="var(--bg-alt, #26374a)" fill-opacity="0.98"/>
                <polygon points="14,15 28,27 14,39"
                    fill="var(--accent, #F98C00)"/>
            </svg>
        `;
        handle.setAttribute('aria-label', 'Open navigation');
        handle.style.position = 'fixed';
        handle.style.bottom = '2.1rem';
        handle.style.left = '0px';
        handle.style.zIndex = 3000;
        handle.style.width = '54px';
        handle.style.height = '64px';
        handle.style.display = 'flex';
        handle.style.justifyContent = 'center';
        handle.style.alignItems = 'center';
        handle.style.border = 'none';
        handle.style.background = 'none';
        handle.style.borderRadius = '0 18px 18px 0';
        handle.style.boxShadow = '2px 2px 18px #0004';
        handle.style.cursor = 'pointer';
        handle.style.opacity = '0.98';
        handle.onclick = function(e) {
            e.stopPropagation();
            rollNav(false);
        };
        document.body.appendChild(handle);
    }

    function createDesktopHandle() {
        // Splitter appears on the right edge of aside
        if (document.getElementById(SPLITTER_ID)) return;
        const aside = document.querySelector(NAV_SELECTOR);
        if (!aside) return;
        const splitter = document.createElement('div');
        splitter.id = SPLITTER_ID;
        splitter.title = "Collapse navigation";
        splitter.style.position = 'absolute';
        splitter.style.top = '0';
        splitter.style.right = '-11px';
        splitter.style.width = '18px';
        splitter.style.height = '100%';
        splitter.style.display = 'flex';
        splitter.style.alignItems = 'center';
        splitter.style.justifyContent = 'center';
        splitter.style.cursor = 'ew-resize';
        splitter.style.zIndex = 101;
        splitter.style.background = 'transparent';

        // Big gray vertical pill with a left arrow
        splitter.innerHTML = `
            <div style="
                width: 16px;
                height: 64px;
                background: var(--bg-alt, #26374a);
                opacity: 0.98;
                border-radius: 0 14px 14px 0;
                box-shadow: 2px 2px 8px #0003;
                display: flex; align-items: center; justify-content: center;">
                <svg width="16" height="44" viewBox="0 0 16 44">
                    <polygon points="13,22 5,12 5,32"
                        fill="var(--accent, #F98C00)"/>
                </svg>
            </div>
        `;

        splitter.onclick = function(e) {
            e.stopPropagation();
            rollNav(true);
        };
        // Place on aside
        aside.style.position = 'relative';
        aside.appendChild(splitter);
    }

    function createDesktopRestoreTab() {
        if (document.getElementById(HANDLE_ID)) return;
        const main = document.querySelector('main');
        if (!main) return;
        const tab = document.createElement('div');
        tab.id = HANDLE_ID;
        tab.title = "Restore navigation";
        tab.style.position = 'fixed';
        tab.style.top = '2.4rem';
        tab.style.left = '0px';
        tab.style.zIndex = 2001;
        tab.style.width = '42px';
        tab.style.height = '64px';
        tab.style.display = 'flex';
        tab.style.justifyContent = 'center';
        tab.style.alignItems = 'center';
        tab.style.border = 'none';
        tab.style.background = 'none';
        tab.style.borderRadius = '0 16px 16px 0';
        tab.style.boxShadow = '2px 2px 18px #0003';
        tab.style.cursor = 'pointer';
        tab.style.opacity = '0.97';
        tab.innerHTML = `
            <svg width="44" height="54" viewBox="0 0 44 54" fill="none">
                <rect x="0" y="0" width="38" height="54" rx="15"
                    fill="var(--bg-alt, #26374a)" fill-opacity="0.98"/>
                <polygon points="14,15 28,27 14,39"
                    fill="var(--accent, #F98C00)"/>
            </svg>
        `;
        tab.onclick = function(e) {
            e.stopPropagation();
            rollNav(false);
        };
        document.body.appendChild(tab);
    }

    function removeAllHandles() {
        ['#' + HANDLE_ID, '#' + SPLITTER_ID].forEach(sel => {
            const el = document.querySelector(sel);
            if (el) el.remove();
        });
    }

    // --- Desktop hover-to-show splitter logic ---
    function setupSplitterHover() {
        const aside = document.querySelector(NAV_SELECTOR);
        if (!aside) return;
        aside.addEventListener('mouseenter', function() {
            if (!isMobile() && isOpen) createDesktopHandle();
        });
        aside.addEventListener('mouseleave', function() {
            if (!isMobile() && isOpen) {
                const splitter = document.getElementById(SPLITTER_ID);
                if (splitter) splitter.remove();
            }
        });
    }

    // --- Touch support for mobile ---
    let touchStartX = null;
    let touchDeltaX = 0;
    document.addEventListener('touchstart', function(e) {
        if (!isMobile()) return;
        if (!e.touches[0]) return;
        touchStartX = e.touches[0].clientX;
        touchDeltaX = 0;
    });
    document.addEventListener('touchmove', function(e) {
        if (!isMobile()) return;
        if (touchStartX === null) return;
        let currentX = e.touches[0].clientX;
        touchDeltaX = currentX - touchStartX;
    });
    document.addEventListener('touchend', function(e) {
        if (!isMobile() || touchStartX === null) return;
        if (touchDeltaX < -70 && isOpen) {
            rollNav(true);
        } else if (touchDeltaX > 70 && !isOpen && touchStartX < 60) {
            rollNav(false);
        }
        touchStartX = null;
        touchDeltaX = 0;
    });

    // --- Click outside nav to close on mobile ---
    document.addEventListener('click', function(e) {
        if (!isMobile()) return;
        const nav = document.querySelector(NAV_SELECTOR);
        if (!nav) return;
        const handle = document.getElementById(HANDLE_ID);
        if (
            isOpen &&
            !nav.contains(e.target) &&
            !(handle && handle.contains(e.target))
        ) {
            rollNav(true);
        }
    });

    // --- Handle resizing / mode switching ---
    function adapt() {
        isMobileMode = isMobile();
        if (isMobileMode) {
            // Always start with nav closed in mobile
            rollNav(true);
        } else {
            // On desktop, nav is open, splitter appears on hover
            rollNav(false);
            setupSplitterHover();
        }
    }

    // --- Listen for resize / DOMContentLoaded / short delay for SSR ---
    window.addEventListener('resize', adapt);
    document.addEventListener('DOMContentLoaded', adapt);
    setTimeout(adapt, 300);

    // --- Desktop collapsed nav: show restore tab on nav rolled ---
    const observer = new MutationObserver(function(mutations) {
        const layout = document.querySelector(LAYOUT_SELECTOR);
        if (!layout) return;
        if (!isMobile() && layout.classList.contains(ROLL_CLASS)) {
            createDesktopRestoreTab();
        } else {
            const restore = document.getElementById(HANDLE_ID);
            if (restore) restore.remove();
        }
    });
    document.addEventListener('DOMContentLoaded', function() {
        const layout = document.querySelector(LAYOUT_SELECTOR);
        if (layout) {
            observer.observe(layout, { attributes: true, attributeFilter: ['class'] });
        }
    });
})();

