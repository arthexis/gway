# file: projects/games/qpig.py
"""Prototype incremental game about quantum guinea pigs."""

from gway import gw
import time
import json
import math
import base64
from bottle import request

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


def _load_state() -> dict:
    """Load state from request or return defaults."""
    data = request.forms.get("state") or request.query.get("state") or ""
    state = {}
    if data:
        try:
            raw = base64.b64decode(data.encode()).decode()
            state = json.loads(raw)
        except Exception:
            gw.debug("invalid state input")
    return {
        "pigs": int(state.get("pigs", DEFAULT_PIGS)),
        "mc": float(state.get("mc", DEFAULT_MICROCERTS)),
        "pellets": float(state.get("pellets", 0.0)),
        "time": float(state.get("time", time.time())),
        "avail": int(state.get("avail", DEFAULT_AVAILABLE)),
        "enc_small": int(state.get("enc_small", DEFAULT_ENC_SMALL)),
        "enc_large": int(state.get("enc_large", DEFAULT_ENC_LARGE)),
        "last_add": float(state.get("last_add", time.time())),
        "veggies": state.get("veggies", {}).copy(),
        "food": state.get("food", []).copy(),
        "offer": state.get("offer"),
    }


def _dump_state(state: dict) -> str:
    raw = json.dumps(state)
    return base64.b64encode(raw.encode()).decode()


def _get_offer(state: dict, now: float) -> tuple[str, int, int]:
    offer = state.get("offer")
    if offer and now - offer.get("time", 0) < OFFER_EXPIRY:
        return offer["kind"], int(offer["qty"]), int(offer["price"])
    import random

    kind = random.choice(VEGGIE_TYPES)
    qty = random.randint(1, 3)
    price = VEGGIE_BASE_PRICE + random.randint(-VEGGIE_PRICE_SPREAD, VEGGIE_PRICE_SPREAD)
    price = max(5, min(20, price))
    state["offer"] = {"kind": kind, "qty": qty, "price": price, "time": now}
    return kind, qty, price


def _process_state(state: dict, action: str | None = None) -> dict:
    """Update and optionally mutate the farm state."""
    gw.debug(f"_process_state start: action={action}")
    pigs = state["pigs"]
    mc = state["mc"]
    pellets = state["pellets"]
    last_time = state["time"]
    avail = state["avail"]
    enc_small = state["enc_small"]
    enc_large = state["enc_large"]
    last_add = state["last_add"]
    veggies = state["veggies"]
    food = state["food"]
    gw.debug(
        "initial state: pigs=%s mc=%s pellets=%s avail=%s enc_small=%s enc_large=%s veggies=%s food=%s",
        pigs,
        mc,
        pellets,
        avail,
        enc_small,
        enc_large,
        veggies,
        food,
    )

    now = time.time()
    dt = max(0.0, min(now - last_time, 3600))
    gw.debug(f"time delta={dt}")

    upkeep_mc = ((UPKEEP_SMALL_HR * enc_small) + (UPKEEP_LARGE_HR * enc_large)) * (
        dt / 3600
    )
    mc = max(0.0, mc - upkeep_mc)
    gw.debug(f"after upkeep: mc={mc}")

    fill_time = FILL_TIME + enc_small * ENC_TIME_SMALL + enc_large * ENC_TIME_LARGE
    cert_frac = mc / CERTAINTY_MAX
    cert_frac = 1.0 - (1.0 - cert_frac) * math.exp(-dt / fill_time)
    mc = min(CERTAINTY_MAX, cert_frac * CERTAINTY_MAX)
    gw.debug(f"after fill: mc={mc}")

    # handle food buffs
    food = [f for f in food if f[1] > now]
    buff_active = any(f[2] > now for f in food)
    buff_mult = 2.0 if buff_active else 1.0

    intervals = int(dt / QP_INTERVAL)
    if intervals > 0:
        import random
        base_prob = QP_BASE_CHANCE * (1 + (cert_frac - 0.5) * QP_CERT_BONUS * 2)
        prob = min(1.0, base_prob * buff_mult)
        gw.debug(f"pellet gen: intervals={intervals} prob={prob} pigs={pigs}")
        for _ in range(intervals):
            for _ in range(pigs):
                if random.random() < prob:
                    pellets += 1
                    if random.random() < prob:
                        pellets += 1
        last_time += intervals * QP_INTERVAL

    # chance for bonus pellets from active veggies
    nibbling = [f[0] for f in food if f[1] > now]
    if nibbling:
        import random
        gw.debug(f"nibbling: {nibbling}")
        for kind in nibbling:
            chance = VEGGIE_BONUS.get(kind, 0.0)
            if random.random() < chance:
                pellets += 1

    # replenish adoption queue
    while now - last_add >= ADOPTION_INTERVAL and avail <= ADOPTION_THRESHOLD:
        avail = min(avail + ADOPTION_ADD, ADOPTION_THRESHOLD)
        last_add += ADOPTION_INTERVAL
        gw.debug(f"adoption queue replenished -> avail={avail}")

    offer_kind, offer_qty, offer_price = _get_offer(state, now)

    capacity = enc_small + enc_large * 2
    if action == "adopt" and avail > 0 and pigs < capacity:
        pigs += 1
        avail -= 1
        gw.debug(f"action adopt -> pigs={pigs} avail={avail}")
    elif action == "buy_small" and mc >= SMALL_COST and (enc_small + enc_large) < ENCLOSURE_MAX:
        mc -= SMALL_COST
        enc_small += 1
        gw.debug(f"action buy_small -> enc_small={enc_small} mc={mc}")
    elif action == "buy_large" and mc >= LARGE_COST and (enc_small + enc_large) < ENCLOSURE_MAX:
        mc -= LARGE_COST
        enc_large += 1
        gw.debug(f"action buy_large -> enc_large={enc_large} mc={mc}")
    elif action == "buy_veggie":
        total = offer_price * offer_qty
        if mc >= total:
            mc -= total
            veggies[offer_kind] = veggies.get(offer_kind, 0) + offer_qty
            offer_kind, offer_qty, offer_price = _get_offer(state, now)
            gw.debug(f"action buy_veggie -> veggies={veggies} mc={mc}")
    elif action and action.startswith("place_"):
        kind = action.split("_", 1)[1]
        slots = (enc_small + enc_large) * 3
        if veggies.get(kind, 0) > 0 and len(food) < slots:
            veggies[kind] -= 1
            if veggies[kind] == 0:
                del veggies[kind]
            eat, linger = VEGGIE_EFFECTS.get(kind, (60, 30))
            food.append([kind, now + eat, now + eat + linger])
            gw.debug(f"action place_{kind} -> food={food} veggies={veggies}")

    state.update(
        {
            "pigs": pigs,
            "mc": mc,
            "pellets": pellets,
            "time": last_time,
            "avail": avail,
            "enc_small": enc_small,
            "enc_large": enc_large,
            "last_add": last_add,
            "veggies": veggies,
            "food": food,
            "offer": {
                "kind": offer_kind,
                "qty": offer_qty,
                "price": offer_price,
                "time": state.get("offer", {}).get("time", now),
            },
        }
    )
    gw.debug(f"_process_state end -> {state}")
    return state


def render_qpig_farm_stats(state: dict) -> str:
    """Return the farm stats block."""
    gw.debug("render_qpig_farm_stats called")
    pigs = state["pigs"]
    mc = state["mc"]
    pellets = state["pellets"]
    avail = state["avail"]
    enc_small = state["enc_small"]
    enc_large = state["enc_large"]
    veggies = state["veggies"]
    food = state["food"]
    capacity = enc_small + enc_large * 2
    veg_list = ", ".join(f"{k}:{v}" for k, v in veggies.items()) or "none"
    food_list = ", ".join(f"{f[0]}" for f in food) or "none"
    html = [
        f"<p>You have <b>{pigs}</b> quantum pigs (capacity {capacity}).</p>",
        f"<p>Certainty: <b>{int(mc)}</b> MC / {CERTAINTY_MAX}</p>",
        f"<p>QPellets: <b>{int(pellets)}</b></p>",
        f"<p>Veggies: {veg_list}</p>",
        f"<p>Food placed: {food_list}</p>",
        f"<p>Pigs waiting for adoption: {avail}</p>",
    ]
    return "\n".join(html)


def view_qpig_farm(*, action: str = None, **_):
    """Main Quantum Piggy farm view."""
    gw.debug(f"view_qpig_farm called with action={action}")
    state = _load_state()
    state = _process_state(state, action)
    state_b64 = _dump_state(state)

    offer = state["offer"]
    offer_kind, offer_qty, offer_price = offer["kind"], offer["qty"], offer["price"]
    capacity = state["enc_small"] + state["enc_large"] * 2

    html = [
        '<link rel="stylesheet" href="/static/games/qpig/farm.css">',
        '<div class="qpig-garden">',
        "<h1>Quantum Piggy Farm</h1>",
        "<canvas id='qpig-canvas' width='32' height='32'></canvas>",
        '<div id="qpig-stats">',
        render_qpig_farm_stats(state),
        "</div>",
        "<form method='post' id='qpig-form' class='qpig-buttons'>",
        "<input type='hidden' name='state' id='qpig-state'>",
    ]
    if state["avail"] > 0 and state["pigs"] < capacity:
        html.append("<button type='submit' name='action' value='adopt'>Adopt Pig</button>")
    html.extend(
        [
            f"<button type='submit' name='action' value='buy_small'>Buy Enclosure ({SMALL_COST} MC)</button>",
            f"<button type='submit' name='action' value='buy_large'>Buy Large Enclosure ({LARGE_COST} MC)</button>",
            f"<button type='submit' name='action' value='buy_veggie'>Buy {offer_qty} {offer_kind}(s) ({offer_price * offer_qty} MC)</button>",
        ]
    )

    slots = (state["enc_small"] + state["enc_large"]) * 3
    if len(state["food"]) < slots:
        for k, v in state["veggies"].items():
            if v > 0:
                html.append(f"<button type='submit' name='action' value='place_{k}'>Feed {k}</button>")

    html.extend([
        "<button type='button' id='qpig-save' title='Save'>💾</button>",
        "<button type='button' id='qpig-load' title='Load'>📂</button>",
        "</form>",
        "</div>",
    ])

    script = """
<script>
const KEY='qpig_state';
sessionStorage.setItem(KEY, '{state_b64}');
const form=document.getElementById('qpig-form');
const hidden=document.getElementById('qpig-state');
if(form){{form.addEventListener('submit',()=>{{hidden.value=sessionStorage.getItem(KEY)||'';}});}}
const save=document.getElementById('qpig-save');
if(save){{save.addEventListener('click',()=>{{const data=sessionStorage.getItem(KEY)||'';const blob=new Blob([data],{{type:'application/octet-stream'}});const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='qpig-save.qpg';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);}});}}
const load=document.getElementById('qpig-load');
if(load){{load.addEventListener('click',()=>{{const inp=document.createElement('input');inp.type='file';inp.accept='.qpg';inp.onchange=e=>{{const f=e.target.files[0];if(!f)return;const r=new FileReader();r.onload=ev=>{{sessionStorage.setItem(KEY, ev.target.result.trim());location.reload();}};r.readAsText(f);}};inp.click();}});}}
const canvas=document.getElementById('qpig-canvas');
if(canvas){{const ctx=canvas.getContext('2d');const img=new Image();img.src='/static/games/qpig/pig.png';img.onload=()=>{{ctx.imageSmoothingEnabled=false;ctx.drawImage(img,0,0);}};}}
</script>
""".format(state_b64=state_b64)

    html.append(script)
    return "\n".join(html)
