// file: data/web/static/scripts/mobile.js

(function() {
    const NAV_SELECTOR = 'aside';
    const LAYOUT_SELECTOR = '.layout';
    const MAIN_SELECTOR = 'main';
    const ROLL_CLASS = 'nav-rolled';
    const HANDLE_ID = 'nav-handle';
    const SPLITTER_ID = 'nav-splitter';
    const ARROW_WIDTH = 54; // px

    function isNavRight() {
        const layout = document.querySelector(LAYOUT_SELECTOR);
        return layout && layout.classList.contains('nav-right');
    }
    let isOpen = true;
    let initialized = false;

    function isMobile() {
        return window.innerWidth <= 650;
    }

    function rollNav(out = true) {
        const layout = document.querySelector(LAYOUT_SELECTOR);
        const main = document.querySelector(MAIN_SELECTOR);
        if (!layout) return;
        const navRight = isNavRight();
        if (out) {
            layout.classList.add(ROLL_CLASS);
            isOpen = false;
            showHandle();
            if (isMobile() && main) {
                if (navRight) {
                    main.style.marginRight = ARROW_WIDTH + 'px';
                } else {
                    main.style.marginLeft = ARROW_WIDTH + 'px';
                }
            }
        } else {
            layout.classList.remove(ROLL_CLASS);
            isOpen = true;
            hideHandle();
            if (main) {
                main.style.marginLeft = '';
                main.style.marginRight = '';
            }
        }
    }

    function showHandle() {
        const existing = document.getElementById(HANDLE_ID);
        if (existing) {
            existing.style.display = 'flex';
            return;
        }
        const navRight = isNavRight();
        const handle = document.createElement('div');
        handle.id = HANDLE_ID;
        const arrow = navRight
            ? '<polygon points="38,18 22,32 38,46" fill="var(--accent, #F98C00)"/>'
            : '<polygon points="22,18 38,32 22,46" fill="var(--accent, #F98C00)"/>';
        handle.innerHTML = `
            <svg width="60" height="64" viewBox="0 0 60 64" fill="none">
                <rect x="0" y="0" width="56" height="64" rx="18" fill="var(--bg-alt, #26374a)" fill-opacity="0.98"/>
                ${arrow}
            </svg>
        `;
        handle.setAttribute('aria-label', 'Open navigation');
        handle.style.position = 'fixed';
        handle.style.bottom = '2.1rem';
        handle.style.left = navRight ? '' : '0px';
        handle.style.right = navRight ? '0px' : '';
        handle.style.zIndex = 3000;
        handle.style.width = ARROW_WIDTH + 'px';
        handle.style.height = '64px';
        handle.style.display = 'flex';
        handle.style.justifyContent = 'center';
        handle.style.alignItems = 'center';
        handle.style.border = 'none';
        handle.style.background = 'none';
        handle.style.borderRadius = navRight ? '18px 0 0 18px' : '0 18px 18px 0';
        handle.style.boxShadow = navRight ? '-2px 2px 18px #0004' : '2px 2px 18px #0004';
        handle.style.cursor = 'pointer';
        handle.style.opacity = '0.98';
        handle.onclick = function(e) {
            e.stopPropagation();
            rollNav(false);
        };
        document.body.appendChild(handle);
    }

    function hideHandle() {
        const handle = document.getElementById(HANDLE_ID);
        if (handle) handle.style.display = 'none';
    }

    function removeHandle() {
        const handle = document.getElementById(HANDLE_ID);
        if (handle) handle.remove();
    }

    function showSplitter() {
        if (document.getElementById(SPLITTER_ID) || isMobile()) return;
        const aside = document.querySelector(NAV_SELECTOR);
        if (!aside) return;
        const navRight = isNavRight();
        const splitter = document.createElement('div');
        splitter.id = SPLITTER_ID;
        splitter.title = "Collapse navigation";
        splitter.style.position = 'absolute';
        splitter.style.top = '0';
        splitter.style.right = navRight ? '' : '-11px';
        splitter.style.left = navRight ? '-11px' : '';
        splitter.style.width = '18px';
        splitter.style.height = '100%';
        splitter.style.display = 'flex';
        splitter.style.alignItems = 'center';
        splitter.style.justifyContent = 'center';
        splitter.style.cursor = 'ew-resize';
        splitter.style.zIndex = 101;
        splitter.style.background = 'transparent';
        const arrow = navRight
            ? '<polygon points="3,22 11,12 11,32" fill="var(--accent, #F98C00)"/>'
            : '<polygon points="13,22 5,12 5,32" fill="var(--accent, #F98C00)"/>';
        const radius = navRight ? '14px 0 0 14px' : '0 14px 14px 0';
        const shadow = navRight ? '-2px 2px 8px #0003' : '2px 2px 8px #0003';
        splitter.innerHTML = `
            <div style="
                width: 16px;
                height: 64px;
                background: var(--bg-alt, #26374a);
                opacity: 0.98;
                border-radius: ${radius};
                box-shadow: ${shadow};
                display: flex; align-items: center; justify-content: center;">
                <svg width="16" height="44" viewBox="0 0 16 44">
                    ${arrow}
                </svg>
            </div>
        `;
        splitter.onclick = function(e) {
            e.stopPropagation();
            rollNav(true);
        };
        aside.style.position = 'relative';
        aside.appendChild(splitter);
    }

    function removeSplitter() {
        const splitter = document.getElementById(SPLITTER_ID);
        if (splitter) splitter.remove();
    }

    // Only on desktop: show/hide splitter on nav hover
    function setupSplitterHover() {
        const aside = document.querySelector(NAV_SELECTOR);
        if (!aside) return;
        aside.addEventListener('mouseenter', function() {
            if (!isMobile() && isOpen) showSplitter();
        });
        aside.addEventListener('mouseleave', function() {
            if (!isMobile() && isOpen) removeSplitter();
        });
    }

    // Only on mobile: click outside nav closes it
    document.addEventListener('click', function(e) {
        if (!isMobile()) return;
        const nav = document.querySelector(NAV_SELECTOR);
        const handle = document.getElementById(HANDLE_ID);
        if (
            isOpen &&
            nav &&
            !nav.contains(e.target) &&
            !(handle && handle.contains(e.target))
        ) {
            rollNav(true);
        }
    });

    // Prevent footer from overlapping nav in mobile mode
    function fixFooterOverlap() {
        const nav = document.querySelector(NAV_SELECTOR);
        const footer = document.querySelector('footer');
        if (!nav || !footer) return;
        if (isMobile()) {
            nav.style.height = `100%`;
            nav.style.overflowY = 'auto';
        } else {
            nav.style.height = '';
            nav.style.overflowY = '';
        }
    }

    // Keep nav/main gap as wide as the arrow when nav open in mobile
    function fixMainMargin() {
        const main = document.querySelector(MAIN_SELECTOR);
        if (!main) return;
        const navRight = isNavRight();
        if (isMobile() && isOpen) {
            if (navRight) {
                main.style.marginRight = ARROW_WIDTH + 'px';
                main.style.marginLeft = '';
            } else {
                main.style.marginLeft = ARROW_WIDTH + 'px';
                main.style.marginRight = '';
            }
        } else {
            main.style.marginLeft = '';
            main.style.marginRight = '';
        }
    }

    // Set correct nav/main state on load and resize
    function adapt() {
        removeHandle();
        removeSplitter();
        fixFooterOverlap();
        const layout = document.querySelector(LAYOUT_SELECTOR);
        if (!layout) return;

        const sameOrigin = document.referrer &&
            new URL(document.referrer, location.href).origin === location.origin;

        if (isMobile()) {
            if (!initialized) {
                if (sameOrigin) {
                    rollNav(true);
                } else {
                    rollNav(false);
                    setTimeout(() => rollNav(true), 400);
                }
                initialized = true;
            }
            showHandle();
            fixFooterOverlap();
            fixMainMargin();
        } else {
            rollNav(false); // desktop: start open
            hideHandle();
            setupSplitterHover();
            fixFooterOverlap();
            fixMainMargin();
        }
    }

    window.addEventListener('resize', function() {
        adapt();
    });
    document.addEventListener('DOMContentLoaded', function() {
        adapt();
    });
    setTimeout(adapt, 300);
})();
