/**
 * GWAY Minimal Render Client (render.js)
 *
 * Finds all elements with data-gw-render. If data-gw-refresh is present, 
 * auto-refreshes them using the named render endpoint, passing their params.
 * - data-gw-render: name of render function (without 'render_' prefix)
 * - data-gw-refresh: interval in seconds (optional)
 * - data-gw-params: comma-separated data attributes to POST (optional; defaults to all except data-gw-*)
 * - data-gw-target: 'content' (default, replace innerHTML), or 'replace' (replace the whole element)
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
      }
    });
  }

  document.addEventListener('DOMContentLoaded', setupAll);
  // If you want to support adding elements after the fact, you may re-call setupAll as needed.
  window.gwRenderSetup = setupAll;
})();
