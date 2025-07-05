// charger_status.js
document.addEventListener("DOMContentLoaded", function() {

    const copyBtn = document.getElementById('copy-ws-url-btn');
    if (copyBtn) {
        copyBtn.addEventListener('click', function() {
            const wsUrl = document.getElementById('ocpp-ws-url');
            if (wsUrl) {
                navigator.clipboard.writeText(wsUrl.value);
                copyBtn.innerText = "Copied!";
                setTimeout(() => copyBtn.innerText = "Copy", 1200);
            }
        });
    }
});
