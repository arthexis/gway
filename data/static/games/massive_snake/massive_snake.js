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
        const roll = document.querySelector('.roll-button');
        const asc = document.querySelector('.snake-ascend button');
        if (asc) asc.disabled = true;
        if (roll) roll.disabled = true;
        setTimeout(() => {
            if (msg) msg.remove();
            if (asc) asc.disabled = false;
            if (roll) roll.disabled = false;
        }, 2000);
    } else if (window.msnakeDisableRoll) {
        const roll = document.querySelector('.roll-button');
        if (roll) {
            roll.disabled = true;
            setTimeout(() => { roll.disabled = false; }, 2000);
        }
    }
});
