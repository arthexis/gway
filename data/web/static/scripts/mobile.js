// file: data/web/static/scripts/mobile.js

(function() {
    const NAV_SELECTOR = 'aside';
    const LAYOUT_SELECTOR = '.layout';
    const ROLL_CLASS = 'nav-rolled';
    const HANDLE_ID = 'nav-handle';
    let isOpen = false; // state: true=open, false=closed

    function isMobile() {
        return window.innerWidth <= 640;
    }

    function rollNav(out = true) {
        const layout = document.querySelector(LAYOUT_SELECTOR);
        const handle = document.getElementById(HANDLE_ID);
        if (!layout) return;
        if (out) {
            layout.classList.add(ROLL_CLASS);
            isOpen = false;
            if (handle) handle.style.display = 'flex';
        } else {
            layout.classList.remove(ROLL_CLASS);
            isOpen = true;
            if (handle) handle.style.display = 'none';
        }
    }

    function createHandle() {
        if (document.getElementById(HANDLE_ID)) return;
        const handle = document.createElement('div');
        handle.id = HANDLE_ID;
        // SVG: a left-side pill tab with arrow (can be styled as you wish)
        handle.innerHTML = `
            <svg width="50" height="44" viewBox="0 0 50 44" fill="none">
                <rect x="0" y="0" width="42" height="44" rx="22" fill="#26374a" opacity="0.97"/>
                <polygon points="37,22 17,12 17,32" fill="#fff"/>
            </svg>
        `;
        handle.setAttribute('aria-label', 'Open navigation');
        handle.style.position = 'fixed';
        handle.style.bottom = '2.1rem';
        handle.style.left = '0px';
        handle.style.zIndex = 3000;
        handle.style.width = '44px';
        handle.style.height = '44px';
        handle.style.display = 'flex';
        handle.style.justifyContent = 'center';
        handle.style.alignItems = 'center';
        handle.style.border = 'none';
        handle.style.background = 'none';
        handle.style.borderRadius = '0 24px 24px 0';
        handle.style.boxShadow = '2px 2px 16px #0005';
        handle.style.cursor = 'pointer';
        handle.style.opacity = '0.95';
        handle.onclick = function(e) {
            e.stopPropagation();
            rollNav(false);
        };
        document.body.appendChild(handle);
    }

    function removeHandle() {
        const handle = document.getElementById(HANDLE_ID);
        if (handle) handle.remove();
    }

    // --- Snap swipe left/right: open or closed, not in-between ---
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
        // No nav dragging; just record the delta for snap at end
    });

    document.addEventListener('touchend', function(e) {
        if (!isMobile() || touchStartX === null) return;
        // Left swipe (close) from open, right swipe (open) from handle area
        if (touchDeltaX < -70 && isOpen) {
            rollNav(true); // snap closed
        } else if (touchDeltaX > 70 && !isOpen && touchStartX < 60) {
            rollNav(false); // snap open
        }
        touchStartX = null;
        touchDeltaX = 0;
    });

    // Close on click outside nav when open
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
            rollNav(true); // snap closed
        }
    });

    function adapt() {
        if (isMobile()) {
            rollNav(true);
            createHandle();
        } else {
            rollNav(false);
            removeHandle();
        }
    }

    window.addEventListener('resize', adapt);
    document.addEventListener('DOMContentLoaded', adapt);
    setTimeout(adapt, 300);
})();

document.addEventListener('DOMContentLoaded', function() {
    if (window.innerWidth <= 650) {
        rollNav(false); // Start with nav open
        setTimeout(() => rollNav(true), 950); // Slide it away after a short moment
    }
});

