/**
 * GWAY Minimal Render Client (render.js)
 *
 * Finds all elements with gw-render (also supports x-gw-render or data-gw-render)
 * or gw-api (also supports x-gw-api or data-gw-api)
 * or gw-view (also supports x-gw-view or data-gw-view).
 * If gw-refresh is present,
 * auto-refreshes them using the named render, api or view endpoint, passing their params.
 * - gw-render: name of render function (without 'render_' prefix)
 * - gw-api: name of api function (without 'api_' prefix)
 * - gw-view: name of view function (without 'view_' prefix)
 * - gw-refresh: interval in seconds (optional)
 * - gw-params: comma-separated data attributes to POST (optional; defaults to all except gw-*)
 * - gw-form: form id to read values from (optional; defaults to child form if present)
 * - gw-target: 'content' (default, replace innerHTML), or 'replace' (replace the whole element)
 * - gw-click: any value starting with "re" to manually re-render the block on left click (optional, case-insensitive)
 * - gw-left-click: same as gw-click (optional)
 * - gw-right-click: any value starting with "re" to re-render on right click (optional, case-insensitive)
 * - gw-double-click: any value starting with "re" to re-render on double click (optional, case-insensitive)
 * - gw-on-load: load block once on page load (optional)
 *
 * When gw-api is used and the element contains [sigils], the API result is used
 * to replace them. A hidden template clone of the original element ensures the
 * placeholders persist across refreshes.
 *
 * No external dependencies.
 */

(function() {
  let timers = {};
  const prefixes = ['gw-', 'x-gw-', 'data-gw-'];
  const templates = new WeakMap();

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

  function getTemplate(el) {
    if (!templates.has(el)) {
      templates.set(el, el.cloneNode(true));
    }
    return templates.get(el);
  }

  function getForm(el) {
    let formId = getAttr(el, 'form');
    let form = null;
    if (formId) {
      form = document.getElementById(formId);
    } else if (el.tagName.toLowerCase() === 'form') {
      form = el;
    } else {
      form = el.querySelector('form');
    }
    return form;
  }

  function replaceSigilsInString(str, data) {
    return str.replace(/\[([^\[\]]+)\]/g, (m, key) => {
      key = key.split('|')[0].trim();
      return Object.prototype.hasOwnProperty.call(data, key) ? data[key] : m;
    });
  }

  function replaceSigils(node, data) {
    if (node.nodeType === Node.TEXT_NODE) {
      node.textContent = replaceSigilsInString(node.textContent, data);
    } else if (node.nodeType === Node.ELEMENT_NODE) {
      Array.from(node.attributes).forEach(attr => {
        let val = replaceSigilsInString(attr.value, data);
        if (val !== attr.value) node.setAttribute(attr.name, val);
      });
      Array.from(node.childNodes).forEach(child => replaceSigils(child, data));
    }
  }

  // Render a block using its gw-render attribute
  function renderBlock(el) {
    let func = getAttr(el, 'render');
    if (!func) return;
    let params = extractParams(el);
    let form = getForm(el);
    if (form) {
      new FormData(form).forEach((v, k) => { params[k] = v; });
    }
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

  function apiBlock(el) {
    let func = getAttr(el, 'api');
    if (!func) return;
    let params = extractParams(el);
    let form = getForm(el);
    if (form) {
      new FormData(form).forEach((v, k) => { params[k] = v; });
    }
    let urlBase = location.pathname.replace(/\/$/, '');
    let url = '/api' + urlBase + '/' + func;

    fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(params),
      cache: "no-store"
    })
    .then(res => res.json())
    .then(data => {
      let template = getTemplate(el).cloneNode(true);
      replaceSigils(template, data);
      Array.from(el.attributes).forEach(a => el.removeAttribute(a.name));
      Array.from(template.attributes).forEach(a => el.setAttribute(a.name, a.value));
      el.innerHTML = template.innerHTML;
    })
    .catch(err => {
      console.error("GWAY api block update failed:", func, err);
    });
  }

  function viewBlock(el) {
    let func = getAttr(el, 'view');
    if (!func) return;
    let params = extractParams(el);
    let form = getForm(el);
    if (form) {
      new FormData(form).forEach((v, k) => { params[k] = v; });
    }
    let path = location.pathname.replace(/\/$/, '');
    let base = path.substring(0, path.lastIndexOf('/'));
    if (!base) base = path; // fallback
    let url = '/render' + base + '/' + func;

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
    })
    .catch(err => {
      console.error("GWAY view block update failed:", func, err);
    });
  }

  function setupElement(el) {
    let refreshFunc = renderBlock;
    if (getAttr(el, 'api')) {
      refreshFunc = apiBlock;
      getTemplate(el);
    } else if (getAttr(el, 'view')) {
      refreshFunc = viewBlock;
    }
    let refresh = parseFloat(getAttr(el, 'refresh'));
    if (!isNaN(refresh) && refresh > 0) {
      let id = el.id || Math.random().toString(36).slice(2);
      timers[id] = setInterval(() => refreshFunc(el), refresh * 1000);
      refreshFunc(el);
      el.dataset.gwLoaded = "1";
    }
    let onLoad = getAttr(el, 'on-load');
    if (onLoad !== null && !el.dataset.gwLoaded) {
      refreshFunc(el);
      el.dataset.gwLoaded = "1";
    }
    let leftClick = getAttr(el, 'click') || getAttr(el, 'left-click');
    if (leftClick && /^re/i.test(leftClick) && !el.dataset.gwLeftClickSetup) {
      el.addEventListener('click', evt => {
        evt.preventDefault();
        refreshFunc(el);
      });
      el.dataset.gwLeftClickSetup = '1';
    }
    let rightClick = getAttr(el, 'right-click');
    if (rightClick && /^re/i.test(rightClick) && !el.dataset.gwRightClickSetup) {
      el.addEventListener('contextmenu', evt => {
        evt.preventDefault();
        refreshFunc(el);
      });
      el.dataset.gwRightClickSetup = '1';
    }
    let dblClick = getAttr(el, 'double-click');
    if (dblClick && /^re/i.test(dblClick) && !el.dataset.gwDoubleClickSetup) {
      el.addEventListener('dblclick', evt => {
        evt.preventDefault();
        refreshFunc(el);
      });
      el.dataset.gwDoubleClickSetup = '1';
    }
  }

  // Set up auto-refresh for all gw-render, gw-api or gw-view blocks
  function setupAll() {
    Object.values(timers).forEach(clearInterval);
    timers = {};
    document.querySelectorAll('[gw-render],[x-gw-render],[data-gw-render],[gw-api],[x-gw-api],[data-gw-api],[gw-view],[x-gw-view],[data-gw-view]').forEach(el => {
      setupElement(el);
    });
  }

  document.addEventListener('DOMContentLoaded', setupAll);
  if (document.readyState !== 'loading') {
    setupAll();
  }
  // If you want to support adding elements after the fact, you may re-call setupAll as needed.
  window.gwRenderSetup = setupAll;
})();
