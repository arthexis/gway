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
