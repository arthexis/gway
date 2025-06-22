// data/conway/static/scripts/game_of_life.js

document.addEventListener("DOMContentLoaded", function () {
    // Allow clicking cells to toggle state, send to backend
    document.querySelectorAll('.cell').forEach(cell => {
        cell.onclick = function() {
            const x = +this.getAttribute('data-x');
            const y = +this.getAttribute('data-y');
            const rows = Array.from(document.querySelectorAll('.game-board tr')).map(
                tr => Array.from(tr.querySelectorAll('.cell')).map(td => td.classList.contains('cell-1') ? 1 : 0)
            );
            rows[x][y] = rows[x][y] ? 0 : 1;
            const flat = rows.map(r => r.join(',')).join(';');
            document.getElementById('boarddata').value = flat;
            document.getElementById('lifeform').submit();
        };
    });
});
