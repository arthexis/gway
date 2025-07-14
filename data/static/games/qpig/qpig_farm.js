// file: data/static/games/qpig/qpig_farm.js

const QPIG_KEY = 'qpig_state';
if (!sessionStorage.getItem(QPIG_KEY) && window.qpigInitState) {
    sessionStorage.setItem(QPIG_KEY, window.qpigInitState);
}

function loadState() {
    const data = sessionStorage.getItem(QPIG_KEY) || window.qpigInitState || '';
    try {
        return JSON.parse(atob(data));
    } catch (e) {
        return {};
    }
}

function saveState(st) {
    sessionStorage.setItem(QPIG_KEY, btoa(JSON.stringify(st)));
}

function updateCounters(st) {
    const cnt = document.getElementById('qpig-count');
    if (cnt) cnt.textContent = `Q-Pigs: ${st.garden.pigs.length}/${st.garden.max_qpigs}`;
    const pel = document.getElementById('qpig-pellets');
    if (pel) pel.textContent = `Q-Pellets: ${st.garden.qpellets}`;
    const vc = document.getElementById('qpig-vcreds');
    if (vc) vc.textContent = `Available V-Creds: ${st.vcreds}`;
    const pelLab = document.getElementById('qpig-lab-pellets');
    if (pelLab) pelLab.textContent = `Q-Pellets: ${st.garden.qpellets}`;
    const vcLab = document.getElementById('qpig-lab-vcreds');
    if (vcLab) vcLab.textContent = `V-Creds: ${st.vcreds}`;
}

function producePellet(st, idx) {
    const p = st.garden.pigs[idx];
    if (!p || p.pooping) {
        return;
    }
    p.pooping = true;
    p.prevActivity = p.activity;
    p.activity = 'Pooping.';
    setTimeout(() => {
        const cur = loadState();
        const pig = (cur.garden.pigs || [])[idx];
        if (!pig) return;
        cur.garden.qpellets = (cur.garden.qpellets || 0) + 1;
        if (pig.activity === 'Pooping.' && pig.pooping) {
            pig.activity = pig.prevActivity || pig.activity;
        }
        delete pig.prevActivity;
        delete pig.pooping;
        saveState(cur);
        updateCounters(cur);
    }, 2000);
}

async function tick() {
    const st = loadState();
    for (let i = 0; i < (st.garden.pigs || []).length; i++) {
        const p = st.garden.pigs[i];
        if (Math.random() * 100 < (p.curiosity || 0)) {
            try {
                const url = `/api/games/qpig/next-activity?act=${encodeURIComponent(p.activity || '')}&alertness=${p.alertness}&curiosity=${p.curiosity}&fitness=${p.fitness}&handling=${p.handling}`;
                const res = await fetch(url);
                const data = await res.json();
                if (data.activity) {
                    p.activity = data.activity;
                }
            } catch (e) {}
        }
        if (Math.random() * 100 < (p.fitness || 0)) {
            producePellet(st, i);
        }
    }
    saveState(st);
    updateCounters(st);
}
updateCounters(loadState());
setInterval(() => { tick(); }, 1000);
const save = document.getElementById('qpig-save');
if (save) {
    save.addEventListener('click', () => {
        const data = sessionStorage.getItem(QPIG_KEY) || '';
        const blob = new Blob([data], { type: 'application/octet-stream' });
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = 'qpig-save.qpg';
        a.click();
        setTimeout(() => URL.revokeObjectURL(a.href), 1000);
    });
}
const load = document.getElementById('qpig-load');
if (load) {
    load.addEventListener('click', () => {
        const inp = document.createElement('input');
        inp.type = 'file';
        inp.accept = '.qpg';
        inp.onchange = e => {
            const f = e.target.files[0];
            if (!f) return;
            const r = new FileReader();
            r.onload = ev => {
                sessionStorage.setItem(QPIG_KEY, ev.target.result.trim());
                location.reload();
            };
            r.readAsText(f);
        };
        inp.click();
    });
}
const tabs = document.querySelectorAll('.qpig-tab');
const panels = document.querySelectorAll('.qpig-panel');
const garden = document.querySelector('.qpig-garden');
tabs.forEach(t => t.addEventListener('click', () => {
    tabs.forEach(x => x.classList.remove('active'));
    panels.forEach(p => p.classList.remove('active'));
    t.classList.add('active');
    const panel = document.getElementById('qpig-panel-' + t.dataset.tab);
    if (panel) panel.classList.add('active');
    if (garden) {
        garden.className = garden.className.replace(/\btab-\w+\b/, '').trim();
        garden.classList.add('tab-' + t.dataset.tab);
    }
}));

// Quantum Lab operations
const LAB_KEY = 'qpig_lab';

function loadLabState() {
    try { return JSON.parse(sessionStorage.getItem(LAB_KEY) || '{}'); } catch (e) { return {}; }
}

function saveLabState(st) {
    sessionStorage.setItem(LAB_KEY, JSON.stringify(st));
}

function startLabOp(op, secs) {
    const finish = Date.now() + secs * 1000;
    saveLabState({ op, finish, duration: secs * 1000 });
    updateLabProgress();
}

function handleLabOpComplete(op) {
    if (op === 'collect') {
        collectPellets();
    } else {
        console.log('lab operation complete:', op);
    }
}

function collectPellets() {
    const state = loadState();
    let pellets = state.garden.qpellets || 0;
    if (pellets <= 0) return;
    const rewards = Array.from({ length: pellets }, () => 1 + Math.floor(Math.random() * 4));
    let drained = 0;
    const drain = setInterval(() => {
        const st = loadState();
        if (st.garden.qpellets > 0) {
            st.garden.qpellets -= 1;
            saveState(st);
            updateCounters(st);
        }
        drained += 1;
        if (drained >= pellets) {
            clearInterval(drain);
            const fin = loadState();
            fin.vcreds = (fin.vcreds || 0) + rewards.reduce((a, b) => a + b, 0);
            saveState(fin);
            updateCounters(fin);
        }
    }, 100);
}

function updateLabProgress() {
    const st = loadLabState();
    const bar = document.getElementById('lab-progress');
    const btns = document.querySelectorAll('#qpig-lab-ops button');
    if (!bar) return;
    if (!st.finish || Date.now() >= st.finish) {
        bar.style.display = 'none';
        btns.forEach(b => b.disabled = false);
        if (st.finish && Date.now() >= st.finish) {
            handleLabOpComplete(st.op);
        }
        saveLabState({});
        return;
    }
    const remaining = st.finish - Date.now();
    bar.style.display = 'block';
    bar.max = st.duration;
    bar.value = st.duration - remaining;
    btns.forEach(b => b.disabled = true);
}

document.querySelectorAll('#qpig-lab-ops button').forEach(b => {
    b.addEventListener('click', () => {
        const secs = parseInt(b.dataset.time || '0', 10);
        if (secs > 0) startLabOp(b.dataset.op, secs);
    });
});

updateLabProgress();
setInterval(updateLabProgress, 500);
