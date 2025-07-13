/**
 * GWAY Minimal Render Client (render.js)
 *
 * Finds all elements with gw-render (also supports x-gw-render or data-gw-render).
 * If gw-refresh is present,
 * auto-refreshes them using the named render endpoint, passing their params.
 * - gw-render: name of render function (without 'render_' prefix)
 * - gw-refresh: interval in seconds (optional)
 * - gw-params: comma-separated data attributes to POST (optional; defaults to all except gw-*)
 * - gw-target: 'content' (default, replace innerHTML), or 'replace' (replace the whole element)
 * - gw-click: any value starting with "re" to manually re-render the block on left click (optional, case-insensitive)
 * - gw-left-click: same as gw-click (optional)
 * - gw-right-click: any value starting with "re" to re-render on right click (optional, case-insensitive)
 * - gw-double-click: any value starting with "re" to re-render on double click (optional, case-insensitive)
 * - gw-on-load: load block once on page load (optional)
 *
 * No external dependencies.
 */

(function() {
  let timers = {};
  const prefixes = ['gw-', 'x-gw-', 'data-gw-'];

  function getAttr(el, name) {
    for (let pre of prefixes) {
      let val = el.getAttribute(pre + name);
      if (val !== null) return val;
    }
    return null;
  }

  // Extract params from data attributes as specified by gw-params or all non-gw- data attrs
  function extractParams(el) {
    let paramsAttr = getAttr(el, 'params');
    let params = {};
    if (paramsAttr) {
      paramsAttr.split(',').map(s => s.trim()).forEach(key => {
        let dataKey = 'data-' + key.replace(/[A-Z]/g, m => '-' + m.toLowerCase());
        let val = el.getAttribute(dataKey);
        if (val !== null) params[key.replace(/-([a-z])/g, g => g[1].toUpperCase())] = val;
      });
    } else {
      // Use all data- attributes except gw-* variants
      for (let { name, value } of Array.from(el.attributes)) {
        if (name.startsWith('data-') && !name.startsWith('data-gw-')) {
          let key = name.slice(5).replace(/-([a-z])/g, g => g[1].toUpperCase());
          params[key] = value;
        }
      }
    }
    return params;
  }

  // Render a block using its gw-render attribute
  function renderBlock(el) {
    let func = getAttr(el, 'render');
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
      let target = getAttr(el, 'target') || 'content';
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

  // Set up auto-refresh for all gw-render blocks
  function setupAll() {
    // Clear existing timers
    Object.values(timers).forEach(clearInterval);
    timers = {};
    // For each gw-render element
    document.querySelectorAll('[gw-render],[x-gw-render],[data-gw-render]').forEach(el => {
      let refresh = parseFloat(getAttr(el, 'refresh'));
      if (!isNaN(refresh) && refresh > 0) {
        let id = el.id || Math.random().toString(36).slice(2);
        timers[id] = setInterval(() => renderBlock(el), refresh * 1000);
        // Render once immediately
        renderBlock(el);
        el.dataset.gwLoaded = "1";
      }
        let onLoad = getAttr(el, 'on-load');
        if (onLoad !== null && !el.dataset.gwLoaded) {
          renderBlock(el);
          el.dataset.gwLoaded = "1";
        }
      let leftClick = getAttr(el, 'click') || getAttr(el, 'left-click');
      if (leftClick && /^re/i.test(leftClick) && !el.dataset.gwLeftClickSetup) {
        el.addEventListener('click', evt => {
          evt.preventDefault();
          renderBlock(el);
        });
        el.dataset.gwLeftClickSetup = '1';
      }

      let rightClick = getAttr(el, 'right-click');
      if (rightClick && /^re/i.test(rightClick) && !el.dataset.gwRightClickSetup) {
        el.addEventListener('contextmenu', evt => {
          evt.preventDefault();
          renderBlock(el);
        });
        el.dataset.gwRightClickSetup = '1';
      }

      let dblClick = getAttr(el, 'double-click');
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
  if (document.readyState !== 'loading') {
    setupAll();
  }
  // If you want to support adding elements after the fact, you may re-call setupAll as needed.
  window.gwRenderSetup = setupAll;
})();
