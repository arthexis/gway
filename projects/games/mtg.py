# file: projects/mtg.py

import requests
from html import escape
from gway import gw
import json
import random
import re

NAME_SUGGESTIONS = [
    "Black Lotus", "Lightning Bolt", "Sol Ring", "Emrakul", "Shivan Dragon", "Griselbrand",
    "Birds of Paradise", "Snapcaster Mage", "Brainstorm", "Thoughtseize", "Giant Growth",
    "Force of Will", "Serra Angel", "Tarmogoyf", "Jace, the Mind Sculptor", "Thragtusk",
    "Ugin, the Spirit Dragon", "Blood Moon", "Phyrexian Obliterator", "Walking Ballista",
]
TYPE_SUGGESTIONS = [
    "Creature", "Instant", "Artifact", "Planeswalker", "Sorcery", "Enchantment",
    "Land", "Legendary", "Vampire", "Goblin", "Angel", "Dragon", "Zombie", "Elf",
    "Dinosaur", "Vehicle", "Saga", "God", "Giant", "Wizard",
]
TEXT_SUGGESTIONS = [
    "draw a card", "flying", "hexproof", "trample", "protection", "haste", "lifelink",
    "indestructible", "counter target", "exile", "destroy", "untap", "discards",
    "target", "deathtouch", "double strike", "token", "flash", "defender",
    "proliferate", "mill",
]
SET_SUGGESTIONS = [
    "Alpha", "Beta", "Unlimited", "Revised", "Mirage", "Zendikar", "Theros", "Dominaria",
    "Strixhaven", "Kamigawa", "Innistrad", "Ravnica", "Kaldheim", "Eldraine", "Modern",
    "New Capenna", "Phyrexia", "War", "Tarkir", "Ixalan",
]

TOTAL_CARD_COUNT = 98256

REMINDER_PATTERN = re.compile(r"\([^)]+reminder text[^)]+\)", re.IGNORECASE)

def _remove_reminders(text):
    """Remove reminder text (in parentheses, with 'reminder text' or mana/keyword reminders) from Oracle text."""
    if not text:
        return ""
    # Remove any parenthetical reminder (common patterns)
    # Examples: (This is a reminder.), (See rule 702.11), (A deck can have any number of cards named ...)
    # We'll remove parentheticals that contain "reminder" or known rulespeak
    # For now, remove any parenthetical starting with a lowercase letter
    text = re.sub(r"\(([^)]*reminder text[^)]*)\)", "", text, flags=re.I)
    text = re.sub(r"\((This is a .+?|See rule .+?|A deck can have .+?)\)", "", text, flags=re.I)
    # Also, aggressively trim known reminder text (best effort, doesn't affect core abilities)
    text = re.sub(r"\(([^)]*exile it instead[^)]*)\)", "", text, flags=re.I)
    text = re.sub(r"\(\s*For example[^\)]*\)", "", text, flags=re.I)
    # Remove any empty parentheticals or excessive spaces
    text = re.sub(r"\(\s*\)", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()

def _scryfall_search(query, limit=3):
    params = {'q': query}
    url = "https://api.scryfall.com/cards/search"
    try:
        resp = requests.get(url, params=params, timeout=6)
        resp.raise_for_status()
        data = resp.json()
        if data.get('object') == 'list' and data.get('data'):
            return data['data'][:limit]
    except Exception as e:
        gw.warn(f"Scryfall search error: {e}")
    return []

def _scryfall_random():
    try:
        resp = requests.get("https://api.scryfall.com/cards/random", timeout=6)
        resp.raise_for_status()
        card = resp.json()
        if card.get("object") == "card":
            return card
    except Exception as e:
        gw.warn(f"Scryfall random error: {e}")
    return None

def _get_cookie_hand():
    hand = gw.web.cookies.get("mtg_hand")
    if hand:
        try:
            return [c for c in hand.split("|") if c]
        except Exception:
            return []
    return []

def _set_cookie_hand(card_ids):
    gw.web.cookies.set("mtg_hand", "|".join(card_ids), path="/", max_age=14*24*3600)

def _get_cookie_discards():
    discards = gw.web.cookies.get("mtg_discards")
    if discards:
        try:
            return set(discards.split("|"))
        except Exception:
            return set()
    return set()

def _add_cookie_discard(card_id):
    discards = _get_cookie_discards()
    discards.add(card_id)
    gw.web.cookies.set("mtg_discards", "|".join(discards), path="/", max_age=14*24*3600)

def _get_cookie_turn():
    val = gw.web.cookies.get("mtg_turn")
    try:
        return int(val)
    except Exception:
        return 0

def _set_cookie_turn(turn: int):
    gw.web.cookies.set("mtg_turn", str(turn), path="/", max_age=14*24*3600)

def _get_cookie_life():
    val = gw.web.cookies.get("mtg_life")
    try:
        return int(val)
    except Exception:
        return 20

def _set_cookie_life(life: int):
    gw.web.cookies.set("mtg_life", str(life), path="/", max_age=14*24*3600)

def _render_card(card):
    name = escape(card.get("name", "Unknown"))
    set_name = escape(card.get("set_name", "-"))
    scry_uri = card.get("scryfall_uri", "#")
    card_type = escape(card.get("type_line", ""))
    # Remove reminder text from oracle_text
    text = _remove_reminders(card.get("oracle_text", ""))
    pt = ""
    if card.get("power") or card.get("toughness"):
        pt = f'P/T: {escape(str(card.get("power") or ""))}/{escape(str(card.get("toughness") or ""))}'
    img_url = card.get("image_uris", {}).get("normal", "")
    html = f"""
    <div class="mtg-card">
      <div class="mtg-title">{name}</div>
      <div class="mtg-set"><a href="{escape(scry_uri)}" target="_blank">{set_name}</a></div>
      {'<img src="'+img_url+'" alt="'+name+'" class="mtg-img">' if img_url else ''}
      <div class="mtg-type">{card_type}</div>
      <div class="mtg-text">{escape(text)}</div>
      <div class="mtg-pt">{pt}</div>
    </div>
    """
    return html

def view_search_games(
    name=None,
    type_line=None,
    oracle_text=None,
    set_name=None,
    discard=None,
    **kwargs
):
    # --- Cookie-based hand setup ---
    use_hand = (
        hasattr(gw.web, "app") and hasattr(gw.web, "cookies")
        and getattr(gw.web.app, "is_setup", lambda x: False)("web.cookies")
        and gw.web.cookies.accepted()
    )

    hand_ids = _get_cookie_hand() if use_hand else []
    discards = _get_cookie_discards() if use_hand else set()
    card_data_map = {}

    # Handle discarding from hand
    if discard and use_hand:
        if discard in hand_ids:
            hand_ids.remove(discard)
            _set_cookie_hand(hand_ids)
            _add_cookie_discard(discard)

    # --- Build query string ---
    query_parts = []
    if name:        query_parts.append(f'name:"{name}"')
    if type_line:   query_parts.append(f'type:"{type_line}"')
    if oracle_text: query_parts.append(f'o:"{oracle_text}"')
    if set_name:    query_parts.append(f'setname:"{set_name}"')
    query = " ".join(query_parts).strip()
    all_discards = set(discards)

    turn = _get_cookie_turn() if use_hand else 0
    if query and use_hand:
        turn += 1
        _set_cookie_turn(turn)

    life = _get_cookie_life() if use_hand else 20
    library = TOTAL_CARD_COUNT - len(hand_ids) - len(all_discards)

    # Hand size can be up to 8, but if at 8 only show discard
    HAND_LIMIT = 8
    hand_full = use_hand and len(hand_ids) >= HAND_LIMIT

    # --- Search for a card if a query is present and hand is not full ---
    main_card = None
    searched = bool(query)
    message = ""
    if query and (not use_hand or not hand_full):
        found = _scryfall_search(query, limit=3)
        found = [c for c in found if c.get("id") not in hand_ids and c.get("id") not in all_discards]
        if not found:
            attempts = 0
            card = None
            while attempts < 7:
                card = _scryfall_random()
                if not card:
                    break
                if card.get("id") not in hand_ids and card.get("id") not in all_discards:
                    break
                attempts += 1
            if card:
                main_card = card
                message = "<b>No cards found for your query. Here's a random card instead:</b>"
            else:
                message = "<b>No cards found and couldn't fetch a random card.</b>"
        else:
            # Pick one at random if 2 or 3 cards are found
            main_card = random.choice(found) if len(found) > 1 else found[0]

    # If we got a main_card and use_hand, add it to hand and clear form fields
    card_added = False
    if main_card and use_hand and main_card.get("id") not in hand_ids and main_card.get("id") not in all_discards:
        hand_ids.append(main_card.get("id"))
        _set_cookie_hand(hand_ids)
        card_added = True
        name = type_line = oracle_text = set_name = ""
        # <---- RECALCULATE hand_full here:
        hand_full = len(hand_ids) >= HAND_LIMIT

    html = []
    html.append('<link rel="stylesheet" href="/static/card_game.css">')
    html.append('<script src="/static/search_cards.js"></script>')
    html.append(f"""
    <script>
    window.mtgSuggestions = {{
        name: {json.dumps(NAME_SUGGESTIONS)},
        type_line: {json.dumps(TYPE_SUGGESTIONS)},
        oracle_text: {json.dumps(TEXT_SUGGESTIONS)},
        set_name: {json.dumps(SET_SUGGESTIONS)},
    }};
    </script>
    """)
    html.append("<h1>Lookup Wars</h1>")

    # Show hand (if enabled and not empty)
    if use_hand and hand_ids:
        html.append('<div class="mtg-cards-hand">')
        for cid in hand_ids:
            card = card_data_map.get(cid)
            if not card:
                try:
                    r = requests.get(f"https://api.scryfall.com/cards/{cid}", timeout=5)
                    if r.ok:
                        card = r.json()
                        card_data_map[cid] = card
                except Exception:
                    card = None
            if card:
                html.append(_render_card(card))
        html.append("</div>")

    # If hand is full, only show discard UI (don't show search form or result)
    if hand_full:
        html.append('<div class="mtg-hand-full">Your hand is full. <strong>Discard a card.</strong></div>')
        html.append('<form class="mtg-search-form" method="get" style="margin-bottom:1.2em;">')
        html.append('<label for="discard">Discard:</label> <select name="discard">')
        for cid in hand_ids:
            card = card_data_map.get(cid)
            label = escape(card.get("name")) if card else cid
            html.append(f'<option value="{cid}">{label}</option>')
        html.append('</select> <button type="submit">Discard</button></form>')
        return "\n".join(html)

    # Show main card result (if not already in hand)
    if main_card:
        if not use_hand:
            html.append('<div class="mtg-cards-hand">')
            html.append(_render_card(main_card))
            html.append('</div>')
        if message:
            html.append(f'<div style="margin-bottom:1em;color:#be6500;">{message}</div>')
    elif searched and (not use_hand or not hand_full):
        html.append('<div style="color:#ba1c0c;">No results found and no random card could be found.</div>')

    no_cards = not hand_ids and not main_card
    form_class = "mtg-search-form" + (" no-cards" if no_cards else "")
    html.append("""
    <form class=\"{form_class}\" method=\"get\">
        <div class=\"mtg-grid\">
            <div class=\"mtg-form-row\">
                <div class=\"mtg-label-row\"><label>NAME:</label><button class=\"mtg-random-btn\" type=\"button\" title=\"Random name\" onclick=\"mtgPickRandom('name')\">&#x1f3b2;</button></div>
                <input type=\"text\" name=\"name\" value=\"{name}\" placeholder=\"Black Lotus\">
            </div>
            <div class=\"mtg-form-row\">
                <div class=\"mtg-label-row\"><label>TYPE:</label><button class=\"mtg-random-btn\" type=\"button\" title=\"Random type\" onclick=\"mtgPickRandom('type_line')\">&#x1f3b2;</button></div>
                <input type=\"text\" name=\"type_line\" value=\"{type_line}\" placeholder=\"Creature\">
            </div>
            <div class=\"mtg-form-row\">
                <div class=\"mtg-label-row\"><label>RULES:</label><button class=\"mtg-random-btn\" type=\"button\" title=\"Random text\" onclick=\"mtgPickRandom('oracle_text')\">&#x1f3b2;</button></div>
                <input type=\"text\" name=\"oracle_text\" value=\"{oracle_text}\" placeholder=\"draw a card\">
            </div>
            <div class=\"mtg-form-row\">
                <div class=\"mtg-label-row\"><label>SET:</label><button class=\"mtg-random-btn\" type=\"button\" title=\"Random set\" onclick=\"mtgPickRandom('set_name')\">&#x1f3b2;</button></div>
                <input type=\"text\" name=\"set_name\" value=\"{set_name}\" placeholder=\"Alpha\">
            </div>
        </div>
        <div class=\"mtg-status\">
            <button class=\"search-btn\" type=\"submit\">Search</button>
            <span class=\"mtg-turn\">Turn: {turn}</span>
            <span class=\"mtg-library\">Library: {library}</span>
            <span class=\"mtg-life\">Life: <span class=\"mtg-life-value\">{life}</span>
                <button type=\"button\" onclick=\"mtgUpdateLife(1)\">+</button>
                <button type=\"button\" onclick=\"mtgUpdateLife(-1)\">-</button>
            </span>
        </div>
    </form>
    """.format(
        form_class=form_class,
        name=escape(name or ""), type_line=escape(type_line or ""),
        oracle_text=escape(oracle_text or ""), set_name=escape(set_name or ""),
        turn=turn, library=library, life=life
    ))

    html.append(
        '<div style="font-size:0.95em;color:#888;margin-top:2em;">Made using the <a href="https://scryfall.com/docs/api">Scryfall API</a>.</div>'
    )
    return "\n".join(html)
