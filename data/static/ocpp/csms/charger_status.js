// charger_status.js
document.addEventListener("DOMContentLoaded", function() {
    document.querySelectorAll(".details-btn").forEach(function(btn) {
        btn.addEventListener("click", function() {
            const id = btn.getAttribute("data-target");
            const panel = document.getElementById(id);
            if (panel) panel.classList.toggle("hidden");
        });
    });

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
