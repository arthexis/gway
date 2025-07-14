# file: projects/games/qpig.py
"""Prototype incremental game about quantum guinea pigs."""

from gway import gw
import json
import base64
import random
import yaml
from bottle import request

DEFAULT_MAX_QPIGS = 2

DEFAULT_PIGS = 1
DEFAULT_MICROCERTS = 500  # 0.5 Cert
DEFAULT_ENC_SMALL = 1
DEFAULT_ENC_LARGE = 0
DEFAULT_AVAILABLE = 3
DEFAULT_VEGGIES = {}
DEFAULT_FOOD = []
DEFAULT_VCREDS = 100  # starting amount of V-Creds

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

# Example market stall inventory
_MARKET_STALLS = [
    (
        "Veggie Wagon",
        [
            {"cost": 5, "icon": "🥕", "name": "Carrot Bundle"},
            {"cost": 8, "icon": "🥬", "name": "Lettuce Head"},
            {"cost": 10, "icon": "🌿", "name": "Cilantro Bunch"},
        ],
    ),
    (
        "Piggery Provisions",
        [
            {"cost": 15, "icon": "🧴", "name": "Water Bottle"},
            {"cost": 20, "icon": "🛏️", "name": "Straw Bedding"},
        ],
    ),
]


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
        "activity": "Resting",
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
    vcreds = int(state.get("vcreds", DEFAULT_VCREDS)) if isinstance(state, dict) else DEFAULT_VCREDS
    if not isinstance(pigs, list) or not pigs:
        pigs = [_new_pig() for _ in range(DEFAULT_PIGS)]
    else:
        for pig in pigs:
            if isinstance(pig, dict):
                pig.setdefault("activity", "Resting")
    return {"garden": {"max_qpigs": max_qpigs, "qpellets": qpellets, "pigs": pigs},
            "vcreds": vcreds}


def _dump_state(state: dict) -> str:
    raw = json.dumps(state)
    return base64.b64encode(raw.encode()).decode()



def _process_state(state: dict, action: str | None = None) -> dict:
    """Minimal state processor (placeholder for future logic)."""
    gw.debug(f"_process_state called with action={action}")
    return state


# -------------------------------------------------------------
# Activity state machine helpers
# -------------------------------------------------------------

def fitness_chance(attrs: dict) -> bool:
    """Return True if a fitness-based roll succeeds."""
    return random.random() * 100 < float(attrs.get("fitness", 0))


def curiosity_chance(attrs: dict) -> bool:
    """Return True if a curiosity-based roll succeeds."""
    return random.random() * 100 < float(attrs.get("curiosity", 0))


def handling_chance(attrs: dict) -> bool:
    """Return True if a handling-based roll succeeds."""
    return random.random() * 100 < float(attrs.get("handling", 0))


def alertness_chance(attrs: dict) -> bool:
    """Return True if an alertness-based roll succeeds."""
    return random.random() * 100 < float(attrs.get("alertness", 0))


_DEFAULT_STATE_MACHINE: dict[str, dict[str, str]] = {
    "Resting": {"Resting placidly": "fitness_chance"},
    "Resting placidly": {"Exploring pen": "curiosity_chance"},
    "Exploring pen": {"Running laps": "fitness_chance"},
    "Running laps": {"Resting": "handling_chance"},
}


def _load_state_machine() -> dict[str, dict[str, str]]:
    """Load transitions from YAML file or return defaults."""
    try:
        path = gw.resource("work", "games", "qpig", "transitions.yml")
        if path.is_file():
            with open(path, "r", encoding="utf-8") as fh:
                data = yaml.safe_load(fh) or {}
                if isinstance(data, dict):
                    return data
    except Exception as exc:  # pragma: no cover - file IO
        gw.debug(f"failed to load transitions: {exc}")
    return _DEFAULT_STATE_MACHINE



# Simple finite state machine for pig activities
_STATE_MACHINE: dict[str, dict[str, str]] = _load_state_machine()


def api_next_activity(*, act: str = "Resting", alertness: float = 0.0,
                      curiosity: float = 0.0, fitness: float = 0.0,
                      handling: float = 0.0, **_):
    """Determine the next activity using the FSM based on pig stats."""
    attrs = {
        "alertness": float(alertness or 0),
        "curiosity": float(curiosity or 0),
        "fitness": float(fitness or 0),
        "handling": float(handling or 0),
    }

    transitions = _STATE_MACHINE.get(act, {})
    for nxt, cond in transitions.items():
        if isinstance(cond, str):
            func = globals().get(cond)
            if callable(func):
                if func(attrs):
                    return {"activity": nxt}
            elif cond.endswith('%'):
                attr = cond[:-1].lower()
                chance = attrs.get(attr, 0)
                if random.random() * 100 < chance:
                    return {"activity": nxt}

    return {"activity": act}


def render_market_stalls():
    """Render available stalls and their wares."""
    rows = []
    for stall, items in _MARKET_STALLS:
        rows.append(f'<div class="market-stall"><strong>{stall}</strong>')
        rows.append('<table>')
        for item in items:
            cost = item.get("cost", 0)
            icon = item.get("icon", "")
            name = item.get("name", "")
            rows.append(
                f'<tr><td><button data-cost="{cost}">{cost} VC</button>'
                f'</td><td>{icon}</td><td>{name}</td></tr>'
            )
        rows.append('</table></div>')
    return "\n".join(rows)




def view_qpig_farm(*, action: str = None, **_):
    """Main Quantum Piggy farm view."""
    gw.debug("view_qpig_farm called")
    state = _load_state()
    state_b64 = _dump_state(state)
    garden = state["garden"]
    max_qpigs = garden["max_qpigs"]
    qpellets = garden.get("qpellets", 0)
    pigs = garden.get("pigs", [])
    vcreds = state.get("vcreds", DEFAULT_VCREDS)

    html = [
        '<link rel="stylesheet" href="/static/games/qpig/qpig_farm.css">',
        '<h1>Quantum Piggy Farm</h1>',
        '<div class="qpig-garden tab-garden">',
        '<div class="qpig-tabs">',
        '<button class="qpig-tab active" data-tab="garden">Garden Shed</button>',
        '<button class="qpig-tab" data-tab="market">Market Street</button>',
        '<button class="qpig-tab" data-tab="lab">Laboratory</button>',
        '<button class="qpig-tab" data-tab="travel">Travel Abroad</button>',
        '<button class="qpig-tab" data-tab="settings">Game Settings</button>',
        '</div>',
        '<div id="qpig-panel-garden" class="qpig-panel active">',
        f'<div class="qpig-top"><span id="qpig-count">Q-Pigs: {len(pigs)}/{max_qpigs}</span><span id="qpig-pellets">Q-Pellets: {qpellets}</span></div>',
        '<div class="qpig-pigs">',
    ]
    for pig in pigs:
        html.extend([
            '<div class="qpig-pig-card">',
            '<div class="qpig-pig-info">',
            f'<div><span class="qpig-pig-name">{pig["name"]}</span> — '
            f'<em>{pig.get("activity", "Resting")}</em></div>',
            f'<div class="qpig-pig-stats">Alertness: {pig["alertness"]} '
            f'Curiosity: {pig["curiosity"]} Fitness: {pig["fitness"]} '
            f'Handling: {pig["handling"]}</div>',
            '</div>',
            f'<img class="qpig-photo" src="https://i.pravatar.cc/30?img={pig.get("face",1)}" width="30" height="30">',
            '</div>',
        ])
    html.extend([
        '</div>',  # close qpig-pigs
        '</div>',  # close qpig-panel-garden
        f'<div id="qpig-panel-market" class="qpig-panel">'
        f'<div class="qpig-top"><span id="qpig-vcreds">Available V-Creds: {vcreds}</span></div>'
        f'<div id="market-stalls" gw-render="market_stalls">{render_market_stalls()}</div></div>',
        '<div id="qpig-panel-lab" class="qpig-panel">'
        f'<div class="qpig-top">'
        f'<span id="qpig-lab-pellets">Q-Pellets: {qpellets}</span>'
        f'<span id="qpig-lab-vcreds">V-Creds: {vcreds}</span>'
        '</div>Laboratory coming soon</div>',
        '<div id="qpig-panel-travel" class="qpig-panel"><div class="qpig-top"></div>Travel Abroad coming soon</div>',
        '<div id="qpig-panel-settings" class="qpig-panel"><div class="qpig-top"></div>',
        '<div class="qpig-buttons">',
        "<button type='button' id='qpig-save' title='Save'>💾 Save</button>",
        "<button type='button' id='qpig-load' title='Load'>📂 Load</button>",
        '</div>',
        '</div>',
        '</div>',  # close qpig-garden
    ])

    html.append(f'<script>window.qpigInitState="{state_b64}";</script>')
    return "\n".join(html)
