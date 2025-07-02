// file: static/net_monitors.js

document.addEventListener('DOMContentLoaded', function () {
    // Find the dashboard
    const dashboard = document.querySelector('.gway-net-dashboard');
    if (!dashboard) return;

    // Find all monitor blocks (each monitor = 1 block)
    const blocks = Array.from(dashboard.querySelectorAll('.monitor-block'));
    if (blocks.length === 0) return;

    // Create tab bar
    const tabBar = document.createElement('div');
    tabBar.className = 'monitor-tabs';

    // For each monitor, create a tab button
    blocks.forEach((block, i) => {
        // Tab label: use the <h2> content if present, fallback to "Monitor N"
        let label = block.querySelector('h2')?.textContent?.replace(/Monitor:\s*/, '')?.trim() || `Monitor ${i+1}`;
        const tab = document.createElement('button');
        tab.className = 'monitor-tab';
        tab.textContent = label;
        tab.setAttribute('data-tab-index', i);

        tab.addEventListener('click', function() {
            // Hide all blocks, deactivate all tabs
            blocks.forEach((b, j) => b.classList.toggle('active', i === j));
            Array.from(tabBar.children).forEach((t, j) => t.classList.toggle('active', i === j));
        });

        tabBar.appendChild(tab);
    });

    // Insert tab bar above the first monitor block
    dashboard.insertBefore(tabBar, blocks[0]);

    // Show first tab by default
    blocks.forEach((block, i) => block.classList.toggle('active', i === 0));
    Array.from(tabBar.children).forEach((tab, i) => tab.classList.toggle('active', i === 0));
});
