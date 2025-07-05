// charger_status.js
document.addEventListener("DOMContentLoaded", function() {
    function handleDetails(e) {
        const btn = e.target.closest(".details-btn");
        if (!btn) return;
        const id = btn.getAttribute("data-target");
        const panel = document.getElementById(id);
        if (panel) panel.classList.toggle("hidden");
    }

    document.addEventListener("click", handleDetails);

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
