// file: data/static/games/massive_snake/massive_snake.js

document.addEventListener('DOMContentLoaded', function () {
    if (window.msnakeReadyToAscend) {
        const msg = document.getElementById('ascend-msg');
        if (msg) {
            msg.textContent = 'Ready to ascend!';
        }
    }
});
