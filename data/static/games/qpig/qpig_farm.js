// file: data/static/games/qpig/qpig_farm.js
// All Quantum Piggy Farm logic lives here. The server only supplies the HTML
// skeleton used by this script.

const QPIG_KEY = 'qpig_state';
const LAB_KEY = 'qpig_lab';

// ------------------------- Helpers -------------------------
const ADJECTIVES = ['Fluffy', 'Happy', 'Cheery', 'Bouncy', 'Chubby', 'Sunny'];
const NOUNS = ['Nibbler', 'Snout', 'Whisker', 'Hopper', 'Wiggler', 'Sniffer'];

function randomName() {
    return ADJECTIVES[Math.floor(Math.random() * ADJECTIVES.length)] +
        ' ' + NOUNS[Math.floor(Math.random() * NOUNS.length)];
}

function newPig() {
    function rnd() { return +(1 + Math.random() * 3).toFixed(2); }
    return {
        name: randomName(),
        alertness: rnd(),
        curiosity: rnd(),
        fitness: rnd(),
        handling: rnd(),
        face: 1 + Math.floor(Math.random() * 70),
        activity: 'Resting'
    };
}

function defaultState() {
    return {
        garden: {
            max_qpigs: 2,
            qpellets: 0,
            pigs: [newPig()]
        },
        vcreds: 100
    };
}

function loadState() {
    const raw = sessionStorage.getItem(QPIG_KEY) || '';
    if (!raw) {
        const st = defaultState();
        saveState(st);
        return st;
    }
    try { return JSON.parse(atob(raw)); } catch (e) { return defaultState(); }
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

function renderPigs(st) {
    const wrap = document.querySelector('.qpig-pigs');
    const tmpl = document.getElementById('pig-template');
    if (!wrap || !tmpl) return;
    wrap.innerHTML = '';
    st.garden.pigs.forEach(p => {
        const card = tmpl.cloneNode(true);
        card.id = '';
        card.style.display = '';
        card.querySelector('.qpig-pig-name').textContent = p.name;
        card.querySelector('.qpig-pig-activity').textContent = p.activity;
        card.querySelector('.qpig-pig-stats').textContent =
            `Alertness: ${p.alertness} Curiosity: ${p.curiosity} ` +
            `Fitness: ${p.fitness} Handling: ${p.handling}`;
        card.querySelector('.qpig-photo').src =
            `https://i.pravatar.cc/30?img=${p.face}`;
        wrap.appendChild(card);
    });
}

// --------------------- State machine -----------------------
function fitnessChance(a) { return Math.random() * 100 < (a.fitness || 0); }
function curiosityChance(a) { return Math.random() * 100 < (a.curiosity || 0); }
function handlingChance(a) { return Math.random() * 100 < (a.handling || 0); }
function alertnessChance(a) { return Math.random() * 100 < (a.alertness || 0); }

const STATE_MACHINE = {
    'Resting': { 'Resting placidly': 'fitnessChance' },
    'Resting placidly': { 'Exploring pen': 'curiosityChance' },
    'Exploring pen': { 'Running laps': 'fitnessChance' },
    'Running laps': { 'Resting': 'handlingChance' }
};

function nextActivity(act, attrs) {
    const transitions = STATE_MACHINE[act] || {};
    for (const [nxt, cond] of Object.entries(transitions)) {
        if (typeof cond === 'string') {
            const fn = globalThis[cond];
            if (typeof fn === 'function') {
                if (fn(attrs)) return nxt;
            } else if (cond.endsWith('%')) {
                const attr = cond.slice(0, -1).toLowerCase();
                if (Math.random() * 100 < (attrs[attr] || 0)) return nxt;
            }
        }
    }
    return act;
}

function startPooping(st, idx) {
    const p = st.garden.pigs[idx];
    if (!p || p.pooping) return;
    p.pooping = true;
    p.prevActivity = p.activity;
    p.activity = 'Pooping';
    renderPigs(st);
    setTimeout(() => {
        const cur = loadState();
        const pig = (cur.garden.pigs || [])[idx];
        if (!pig || !pig.pooping) return;
        cur.garden.qpellets = (cur.garden.qpellets || 0) + 1;
        pig.activity = pig.prevActivity || pig.activity;
        delete pig.prevActivity;
        delete pig.pooping;
        saveState(cur);
        renderPigs(cur);
        updateCounters(cur);
    }, 2000);
}

const ACTIVITY_TRANSITIONS = [
    function checkPooping(st, p, idx) {
        if (Math.random() * 100 < (p.fitness || 0)) {
            startPooping(st, idx);
        }
    },
    function checkStateMachine(_st, p) {
        if (!p.pooping && Math.random() * 100 < (p.curiosity || 0)) {
            p.activity = nextActivity(p.activity, p);
        }
    }
];

function tick() {
    const st = loadState();
    st.garden.pigs.forEach((p, idx) => {
        ACTIVITY_TRANSITIONS.forEach(fn => fn(st, p, idx));
    });
    saveState(st);
    renderPigs(st);
    updateCounters(st);
}

// ----------------------- Market ----------------------------
const MARKET_STALLS = [
    ['Veggie Wagon', [
        { cost: 5, icon: '🥕', name: 'Carrot Bundle' },
        { cost: 8, icon: '🥬', name: 'Lettuce Head' },
        { cost: 10, icon: '🌿', name: 'Cilantro Bunch' }
    ]],
    ['Piggery Provisions', [
        { cost: 15, icon: '🧴', name: 'Water Bottle' },
        { cost: 20, icon: '🛏️', name: 'Straw Bedding' }
    ]]
];

function renderMarketStalls() {
    const cont = document.getElementById('market-stalls');
    if (!cont) return;
    cont.innerHTML = '';
    MARKET_STALLS.forEach(([stall, items]) => {
        const div = document.createElement('div');
        div.className = 'market-stall';
        div.innerHTML = `<strong>${stall}</strong>`;
        const table = document.createElement('table');
        items.forEach(item => {
            const row = document.createElement('tr');
            row.innerHTML = `<td><button data-cost="${item.cost}">${item.cost} VC</button></td>` +
                             `<td>${item.icon}</td><td>${item.name}</td>`;
            table.appendChild(row);
        });
        div.appendChild(table);
        cont.appendChild(div);
    });
}

// --------------------- Quantum Lab -------------------------
function loadLabState() {
    try { return JSON.parse(sessionStorage.getItem(LAB_KEY) || '{}'); } catch { return {}; }
}

function saveLabState(st) { sessionStorage.setItem(LAB_KEY, JSON.stringify(st)); }

function startLabOp(op, secs) {
    const finish = Date.now() + secs * 1000;
    saveLabState({ op, finish, duration: secs * 1000 });
    updateLabProgress();
}

function handleLabOpComplete(op) {
    if (op === 'collect') {
        collectPellets();
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

// ----------------------- Setup -----------------------------
document.addEventListener('DOMContentLoaded', () => {
    renderMarketStalls();
    const st = loadState();
    renderPigs(st);
    updateCounters(st);
    setInterval(tick, 1000);

    document.querySelectorAll('.qpig-tab').forEach(t => {
        const panels = document.querySelectorAll('.qpig-panel');
        const garden = document.querySelector('.qpig-garden');
        t.addEventListener('click', () => {
            document.querySelectorAll('.qpig-tab').forEach(x => x.classList.remove('active'));
            panels.forEach(p => p.classList.remove('active'));
            t.classList.add('active');
            const panel = document.getElementById('qpig-panel-' + t.dataset.tab);
            if (panel) panel.classList.add('active');
            if (garden) {
                garden.className = garden.className.replace(/\btab-\w+\b/, '').trim();
                garden.classList.add('tab-' + t.dataset.tab);
            }
        });
    });

    document.querySelectorAll('#qpig-lab-ops button').forEach(b => {
        b.addEventListener('click', () => {
            const secs = parseInt(b.dataset.time || '0', 10);
            if (secs > 0) startLabOp(b.dataset.op, secs);
        });
    });

    const saveBtn = document.getElementById('qpig-save');
    if (saveBtn) {
        saveBtn.addEventListener('click', () => {
            const data = sessionStorage.getItem(QPIG_KEY) || '';
            const blob = new Blob([data], { type: 'application/octet-stream' });
            const a = document.createElement('a');
            a.href = URL.createObjectURL(blob);
            a.download = 'qpig-save.qpg';
            a.click();
            setTimeout(() => URL.revokeObjectURL(a.href), 1000);
        });
    }

    const loadBtn = document.getElementById('qpig-load');
    if (loadBtn) {
        loadBtn.addEventListener('click', () => {
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

    updateLabProgress();
    setInterval(updateLabProgress, 500);
});
