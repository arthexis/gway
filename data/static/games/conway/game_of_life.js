// data/conway/static/scripts/game_of_life.js

document.addEventListener("DOMContentLoaded", function () {
    const board = document.getElementById('gameboard');
    if (!board) return;

    let drawing = false;
    let toggled = new Set();

    function toggleCell(td) {
        if (!td) return;
        const x = +td.getAttribute('data-x');
        const y = +td.getAttribute('data-y');
        const key = `${x},${y}`;
        if (toggled.has(key)) return;
        toggled.add(key);
        td.classList.toggle('cell-1');
        td.classList.toggle('cell-0');
    }

    board.addEventListener('mousedown', function (e) {
        const cell = e.target.closest('.cell');
        if (cell) {
            drawing = true;
            toggled = new Set();
            toggleCell(cell);
            e.preventDefault();
        }
    });

    board.addEventListener('mouseover', function (e) {
        if (!drawing) return;
        const cell = e.target.closest('.cell');
        if (cell) toggleCell(cell);
    });

    document.addEventListener('mouseup', function () {
        if (!drawing) return;
        drawing = false;
        const rows = Array.from(document.querySelectorAll('.game-board tr')).map(
            tr => Array.from(tr.querySelectorAll('.cell')).map(td => td.classList.contains('cell-1') ? 1 : 0)
        );
        const flat = rows.map(r => r.join(',')).join(';');
        document.getElementById('boarddata').value = flat;
        document.getElementById('lifeform').submit();
    });
});
