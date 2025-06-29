// file: data/static/render.js

/**
 * When the hash in the URL changes, fetch updated HTML fragments for one or more elements
 * from the API, and replace those elements by their IDs on the current page.
 */
function updateFromHash() {
  let hash = location.hash.slice(1);
  if (!hash) return;

  // Construct API endpoint (e.g., /hash/ocpp/csms/meter-kwh)
  let path = location.pathname.replace(/\/$/, '');
  let apiUrl = '/hash' + path + '/' + hash;

  fetch(apiUrl)
    .then(res => {
      if (!res.ok) throw new Error('API error');
      return res.json();
    })
    .then(data => {
      // For each returned key (element ID), replace the corresponding element's HTML
      for (let id in data) {
        if (data.hasOwnProperty(id)) {
          let oldEl = document.getElementById(id);
          if (oldEl) {
            // Safely parse HTML fragment to DOM element
            let temp = document.createElement('div');
            temp.innerHTML = data[id];
            let newEl = temp.firstElementChild;
            if (newEl) {
              oldEl.replaceWith(newEl);
            }
          }
        }
      }
    })
    .catch(err => {
      console.error('Error updating content for hash:', hash, err);
    });
}
