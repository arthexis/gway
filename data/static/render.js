/**
 * GWAY Minimal Render Client (render.js)
 *
 * Finds all elements with data-gw-render. If data-gw-refresh is present, 
 * auto-refreshes them using the named render endpoint, passing their params.
 * - data-gw-render: name of render function (without 'render_' prefix)
 * - data-gw-refresh: interval in seconds (optional)
 * - data-gw-params: comma-separated data attributes to POST (optional; defaults to all except data-gw-*)
 * - data-gw-target: 'content' (default, replace innerHTML), or 'replace' (replace the whole element)
 * - data-gw-click: any value starting with "re" to manually re-render the block on left click (optional, case-insensitive)
 * - data-gw-left-click: same as data-gw-click (optional)
 * - data-gw-right-click: any value starting with "re" to re-render on right click (optional, case-insensitive)
 * - data-gw-double-click: any value starting with "re" to re-render on double click (optional, case-insensitive)
 * - data-gw-on-load: load block once on page load (optional)
 *
 * No external dependencies.
 */

(function() {
  let timers = {};

  // Extract params from data attributes as specified by data-gw-params or all non-gw- data attrs
  function extractParams(el) {
    let paramsAttr = el.getAttribute('data-gw-params');
    let params = {};
    if (paramsAttr) {
      paramsAttr.split(',').map(s => s.trim()).forEach(key => {
        let dataKey = 'data-' + key.replace(/[A-Z]/g, m => '-' + m.toLowerCase());
        let val = el.getAttribute(dataKey);
        if (val !== null) params[key.replace(/-([a-z])/g, g => g[1].toUpperCase())] = val;
      });
    } else {
      // Use all data- attributes except data-gw-*
      for (let { name, value } of Array.from(el.attributes)) {
        if (name.startsWith('data-') && !name.startsWith('data-gw-')) {
          let key = name.slice(5).replace(/-([a-z])/g, g => g[1].toUpperCase());
          params[key] = value;
        }
      }
    }
    return params;
  }

  // Render a block using its data-gw-render attribute
  function renderBlock(el) {
    let func = el.getAttribute('data-gw-render');
    if (!func) return;
    let params = extractParams(el);
    let urlBase = location.pathname.replace(/\/$/, '');
    let url = '/render' + urlBase + '/' + func;

    fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(params),
      cache: "no-store"
    })
    .then(res => res.text())
    .then(html => {
      let target = el.getAttribute('data-gw-target') || 'content';
      if (target === 'replace') {
        let temp = document.createElement('div');
        temp.innerHTML = html;
        let newEl = temp.firstElementChild;
        if (newEl) el.replaceWith(newEl);
        else el.innerHTML = html;
      } else {
        el.innerHTML = html;
      }
      // No script execution for now.
    })
    .catch(err => {
      console.error("GWAY render block update failed:", func, err);
    });
  }

  // Set up auto-refresh for all data-gw-render blocks
  function setupAll() {
    // Clear existing timers
    Object.values(timers).forEach(clearInterval);
    timers = {};
    // For each data-gw-render element
    document.querySelectorAll('[data-gw-render]').forEach(el => {
      let refresh = parseFloat(el.getAttribute('data-gw-refresh'));
      if (!isNaN(refresh) && refresh > 0) {
        let id = el.id || Math.random().toString(36).slice(2);
        timers[id] = setInterval(() => renderBlock(el), refresh * 1000);
        // Render once immediately
        renderBlock(el);
        el.dataset.gwLoaded = "1";
      }
        let onLoad = el.getAttribute("data-gw-on-load");
        if (onLoad !== null && !el.dataset.gwLoaded) {
          renderBlock(el);
          el.dataset.gwLoaded = "1";
        }
      let leftClick = el.getAttribute('data-gw-click') || el.getAttribute('data-gw-left-click');
      if (leftClick && /^re/i.test(leftClick) && !el.dataset.gwLeftClickSetup) {
        el.addEventListener('click', evt => {
          evt.preventDefault();
          renderBlock(el);
        });
        el.dataset.gwLeftClickSetup = '1';
      }

      let rightClick = el.getAttribute('data-gw-right-click');
      if (rightClick && /^re/i.test(rightClick) && !el.dataset.gwRightClickSetup) {
        el.addEventListener('contextmenu', evt => {
          evt.preventDefault();
          renderBlock(el);
        });
        el.dataset.gwRightClickSetup = '1';
      }

      let dblClick = el.getAttribute('data-gw-double-click');
      if (dblClick && /^re/i.test(dblClick) && !el.dataset.gwDoubleClickSetup) {
        el.addEventListener('dblclick', evt => {
          evt.preventDefault();
          renderBlock(el);
        });
        el.dataset.gwDoubleClickSetup = '1';
      }
    });
  }

  document.addEventListener('DOMContentLoaded', setupAll);
  // If you want to support adding elements after the fact, you may re-call setupAll as needed.
  window.gwRenderSetup = setupAll;
})();
