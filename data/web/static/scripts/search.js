// file: data/web/static/scripts/search.js

function autoExpand(el) {
    el.style.height = '2.4em'; // base height for 1 line
    if (el.value.trim() !== "") {
        el.style.height = "auto";
        el.style.height = (el.scrollHeight) + "px";
    }
}

function attachSearchBoxHandlers(el) {
    if (!el || el._searchboxAttached) return;
    el._searchboxAttached = true; // Avoid double-binding
    // Auto-expand if pre-filled
    if (el.value.trim() !== "") autoExpand(el);
    el.addEventListener('input', function() { autoExpand(el); });
    // Submit on Enter, newline on Shift+Enter
    el.addEventListener('keydown', function(e) {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            // Find parent form and submit
            var form = el.form;
            if (form) form.submit();
        }
        // Shift+Enter = allow newline (do nothing special)
    });
}

// Attach to any matching box now and in the future (in case of SPA/dynamic nav)
function bindAllSearchBoxes() {
    // By ID (legacy)
    var el = document.getElementById('help-search');
    if (el) attachSearchBoxHandlers(el);
    // By class (future-proof for multiple search boxes)
    var els = document.querySelectorAll('textarea.help-search, textarea[data-searchbox]');
    els.forEach(attachSearchBoxHandlers);
}

// Run once on initial page load
window.addEventListener("DOMContentLoaded", bindAllSearchBoxes);

// If using htmx or other partial-reload framework, you may want to run bindAllSearchBoxes()
// again after navigation or replacement. Example for htmx:
// document.body.addEventListener("htmx:afterSwap", bindAllSearchBoxes);
