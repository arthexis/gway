# file: projects/games/qpig.py
"""Prototype incremental game about quantum guinea pigs."""

from gway import gw
import json
import base64
import random
from bottle import request

DEFAULT_MAX_QPIGS = 2

DEFAULT_PIGS = 1
DEFAULT_MICROCERTS = 500  # 0.5 Cert
DEFAULT_ENC_SMALL = 1
DEFAULT_ENC_LARGE = 0
DEFAULT_AVAILABLE = 3
DEFAULT_VEGGIES = {}
DEFAULT_FOOD = []

ENCLOSURE_MAX = 8

CERTAINTY_MAX = 1000  # stored in microcerts
FILL_TIME = 10 * 60  # base seconds from 0 to 1
ENC_TIME_SMALL = 5 * 60
ENC_TIME_LARGE = 8 * 60

SMALL_COST = 650
LARGE_COST = 920
UPKEEP_SMALL_HR = 2.0
UPKEEP_LARGE_HR = 3.0

ADOPTION_ADD = 2
ADOPTION_INTERVAL = 3 * 3600
ADOPTION_THRESHOLD = 7

# QP generation: 50% chance every 30s plus +/-25% from Certainty
QP_INTERVAL = 30.0  # seconds between pellet attempts
QP_BASE_CHANCE = 0.5
QP_CERT_BONUS = 0.25

VEGGIE_TYPES = ["carrot", "lettuce", "cilantro", "cucumber"]
VEGGIE_BASE_PRICE = 12
VEGGIE_PRICE_SPREAD = 8

# chance to generate an extra pellet while nibbling
VEGGIE_BONUS = {
    "carrot": 0.25,
    "lettuce": 0.15,
    "cilantro": 0.3,
    "cucumber": 0.2,
}

# how long each veggie is eaten and how long the boost lingers, in seconds
VEGGIE_EFFECTS = {
    "carrot": (60, 30),
    "lettuce": (90, 45),
    "cilantro": (120, 60),
    "cucumber": (75, 40),
}


OFFER_EXPIRY = 300  # seconds


_ADJECTIVES = ["Fluffy", "Happy", "Cheery", "Bouncy", "Chubby", "Sunny"]
_NOUNS = ["Nibbler", "Snout", "Whisker", "Hopper", "Wiggler", "Sniffer"]


def _random_name() -> str:
    """Generate a cute two-word name."""
    return f"{random.choice(_ADJECTIVES)} {random.choice(_NOUNS)}"


def _new_pig() -> dict:
    """Create a new pig with random stats."""
    return {
        "name": _random_name(),
        "alertness": round(random.uniform(1, 4), 2),
        "curiosity": round(random.uniform(1, 4), 2),
        "fitness": round(random.uniform(1, 4), 2),
        "handling": round(random.uniform(1, 4), 2),
        "face": random.randint(1, 70),
    }


def _load_state() -> dict:
    """Load simplified state from request or defaults."""
    data = request.forms.get("state") or request.query.get("state") or ""
    state = {}
    if data:
        try:
            raw = base64.b64decode(data.encode()).decode()
            state = json.loads(raw)
        except Exception:
            gw.debug("invalid state input")
    garden = state.get("garden", {}) if isinstance(state, dict) else {}
    max_qpigs = int(garden.get("max_qpigs", DEFAULT_MAX_QPIGS))
    qpellets = int(garden.get("qpellets", 0))
    pigs = garden.get("pigs") if isinstance(garden, dict) else None
    if not isinstance(pigs, list) or not pigs:
        pigs = [_new_pig() for _ in range(DEFAULT_PIGS)]
    return {"garden": {"max_qpigs": max_qpigs, "qpellets": qpellets, "pigs": pigs}}


def _dump_state(state: dict) -> str:
    raw = json.dumps(state)
    return base64.b64encode(raw.encode()).decode()



def _process_state(state: dict, action: str | None = None) -> dict:
    """Minimal state processor (placeholder for future logic)."""
    gw.debug(f"_process_state called with action={action}")
    return state




def view_qpig_farm(*, action: str = None, **_):
    """Main Quantum Piggy farm view."""
    gw.debug("view_qpig_farm called")
    state = _load_state()
    state_b64 = _dump_state(state)
    garden = state["garden"]
    max_qpigs = garden["max_qpigs"]
    qpellets = garden.get("qpellets", 0)
    pigs = garden.get("pigs", [])

    html = [
        '<link rel="stylesheet" href="/static/games/qpig/farm.css">',
        '<h1>Quantum Piggy Farm</h1>',
        '<div class="qpig-garden">',
        '<div class="qpig-tabs">',
        '<button class="qpig-tab active" data-tab="garden">Garden Shed</button>',
        '<button class="qpig-tab" data-tab="market">Market Street</button>',
        '<button class="qpig-tab" data-tab="lab">Laboratory</button>',
        '<button class="qpig-tab" data-tab="travel">Travel Abroad</button>',
        '</div>',
        '<div id="qpig-panel-garden" class="qpig-panel active">',
        f'<div class="qpig-top"><span id="qpig-count">Q-Pigs: {len(pigs)}/{max_qpigs}</span><span id="qpig-pellets">Q-Pellets: {qpellets}</span></div>',
        '<div class="qpig-pigs">',
    ]
    for pig in pigs:
        html.extend([
            '<div class="qpig-pig-card">',
            f'<div><div class="qpig-pig-name">{pig["name"]}</div>',
            f'<div class="qpig-pig-stats">Alertness: {pig["alertness"]} '
            f'Curiosity: {pig["curiosity"]} Fitness: {pig["fitness"]} '
            f'Handling: {pig["handling"]}</div></div>',
            f'<img class="qpig-photo" src="https://i.pravatar.cc/30?img={pig.get("face",1)}" width="30" height="30"></div>',
        ])
    html.extend([
        '</div>',  # close qpig-pigs
        '<div class="qpig-buttons">',
        "<button type='button' id='qpig-save' title='Save'>💾</button>",
        "<button type='button' id='qpig-load' title='Load'>📂</button>",
        '</div>',
        '</div>',  # close qpig-panel-garden
        '<div id="qpig-panel-market" class="qpig-panel"><div class="qpig-top"></div>Market Street coming soon</div>',
        '<div id="qpig-panel-lab" class="qpig-panel"><div class="qpig-top"></div>Laboratory coming soon</div>',
        '<div id="qpig-panel-travel" class="qpig-panel"><div class="qpig-top"></div>Travel Abroad coming soon</div>',
        '</div>',  # close qpig-garden
    ])

    script = """
<script>
const KEY='qpig_state';
if(!sessionStorage.getItem(KEY)) sessionStorage.setItem(KEY, '{state_b64}');

function loadState(){{
  const data=sessionStorage.getItem(KEY)||'{state_b64}';
  try{{return JSON.parse(atob(data));}}catch(e){{return {{}};}}
}}

function saveState(st){{
  sessionStorage.setItem(KEY, btoa(JSON.stringify(st)));
}}

function updateCounters(st){{
  const cnt=document.getElementById('qpig-count');
  if(cnt) cnt.textContent=`Q-Pigs: ${{st.garden.pigs.length}}/${{st.garden.max_qpigs}}`;
  const pel=document.getElementById('qpig-pellets');
  if(pel) pel.textContent=`Q-Pellets: ${{st.garden.qpellets}}`;
}}

function tick(){{
  const st=loadState();
  (st.garden.pigs||[]).forEach(p=>{{
    if(Math.random()*100 < (p.fitness||0)){{
      st.garden.qpellets=(st.garden.qpellets||0)+1;
    }}
  }});
  saveState(st);
  updateCounters(st);
}}
updateCounters(loadState());
setInterval(tick,1000);
const save=document.getElementById('qpig-save');
if(save){{save.addEventListener('click',()=>{{const data=sessionStorage.getItem(KEY)||'';const blob=new Blob([data],{{type:'application/octet-stream'}});const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='qpig-save.qpg';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);}});}}
const load=document.getElementById('qpig-load');
if(load){{load.addEventListener('click',()=>{{const inp=document.createElement('input');inp.type='file';inp.accept='.qpg';inp.onchange=e=>{{const f=e.target.files[0];if(!f)return;const r=new FileReader();r.onload=ev=>{{sessionStorage.setItem(KEY, ev.target.result.trim());location.reload();}};r.readAsText(f);}};inp.click();}});}}
const canvas=document.getElementById('qpig-canvas');
if(canvas){{const ctx=canvas.getContext('2d');const img=new Image();img.src='/static/games/qpig/pig.png';img.onload=()=>{{ctx.imageSmoothingEnabled=false;ctx.drawImage(img,0,0);}};}}
const tabs=document.querySelectorAll('.qpig-tab');
const panels=document.querySelectorAll('.qpig-panel');
tabs.forEach(t=>t.addEventListener('click',()=>{{
  tabs.forEach(x=>x.classList.remove('active'));
  panels.forEach(p=>p.classList.remove('active'));
  t.classList.add('active');
  const panel=document.getElementById('qpig-panel-'+t.dataset.tab);
  if(panel) panel.classList.add('active');
}}));
</script>
""".format(state_b64=state_b64)

    html.append(script)
    return "\n".join(html)
