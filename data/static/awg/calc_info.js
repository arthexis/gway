// file: data/static/awg/calc_info.js
window.addEventListener('DOMContentLoaded', function () {
    var toggle = document.getElementById('info-toggle');
    var box = document.getElementById('calc-info');
    var close = document.getElementById('info-close');
    if (!toggle || !box || !close) return;
    toggle.addEventListener('click', function () {
        box.classList.add('open');
        toggle.classList.add('hidden');
        close.classList.remove('hidden');
    });
    close.addEventListener('click', function () {
        box.classList.remove('open');
        toggle.classList.remove('hidden');
        close.classList.add('hidden');
    });
});

