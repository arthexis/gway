// file: data/static/search_games.js

// Random button JS: fill field and submit
function mtgFillField(field, val) {
    document.querySelector('[name="'+field+'"]').value = val;
    document.querySelector('.mtg-search-form').submit();
}
function mtgPickRandom(field) {
    var suggestions = window.mtgSuggestions || {};
    var vals = suggestions[field];
    if (!vals || !vals.length) return;
    var idx = Math.floor(Math.random() * vals.length);
    mtgFillField(field, vals[idx]);
}

function mtgUpdateLife(delta) {
    var el = document.querySelector('.mtg-life-value');
    if (!el) return;
    var val = parseInt(el.textContent, 10);
    if (isNaN(val)) val = 20;
    val += delta;
    if (val < 0) val = 0;
    el.textContent = val;
    document.cookie = 'mtg_life=' + val + ';path=/';
}
