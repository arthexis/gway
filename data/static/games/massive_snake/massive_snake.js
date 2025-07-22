// file: data/static/games/massive_snake/massive_snake.js

document.addEventListener('DOMContentLoaded', function () {
    if (window.msnakeReadyToAscend) {
        const title = document.getElementById('msnake-title');
        const msg = document.getElementById('ascend-msg');
        if (msg) {
            msg.textContent = 'Ready to ascend! ';
            if (title) {
                const span = document.createElement('span');
                span.textContent = title.textContent;
                span.className = 'snake-title ascended';
                msg.appendChild(span);
            }
        }
    }
});
