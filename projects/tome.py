"""Persistent deck management helpers ("tomes")."""

from __future__ import annotations

import hashlib
import json
import os
import random
from dataclasses import dataclass
from pathlib import Path
from queue import Empty, Queue
from threading import Event, Thread
from typing import Any, Iterable

from gway import gw


_STANDARD_TOME_NAME = "standard"
_LAST_TOME_FILE = "_last_tome.txt"


@dataclass(frozen=True)
class CardTemplate:
    code: str
    label: str


def _tomes_root() -> Path:
    """Return the root directory where tome files are stored."""
    return Path(gw.resource("work", "tomes", dir=True))


def _last_path() -> Path:
    return _tomes_root() / _LAST_TOME_FILE


def _load_last_name() -> str | None:
    path = _last_path()
    if path.exists():
        raw = path.read_text(encoding="utf-8").strip()
        return raw or None
    return None


def _remember_last(name: str) -> None:
    if not name:
        return
    path = _last_path()
    path.write_text(name, encoding="utf-8")


_MAX_TOME_SLUG_LENGTH = 80


def _slugify(name: str) -> str:
    cleaned = []
    for ch in name:
        if ch.isalnum():
            cleaned.append(ch.lower())
        elif ch in ("-", "_"):
            cleaned.append(ch)
        else:
            cleaned.append("-")
    slug = "".join(cleaned).strip("-_")
    if not slug:
        slug = "tome"
    if len(slug) > _MAX_TOME_SLUG_LENGTH:
        digest = hashlib.sha256(name.encode("utf-8")).hexdigest()[:8]
        prefix_length = _MAX_TOME_SLUG_LENGTH - len(digest) - 1
        if prefix_length <= 0:
            slug = digest[:_MAX_TOME_SLUG_LENGTH]
        else:
            prefix = slug[:prefix_length].rstrip("-_")
            slug = f"{prefix}-{digest}" if prefix else digest
    return slug


def _resolve_name(requested: str | None) -> tuple[str, str]:
    normalized = (requested or "").strip()
    if normalized == "*":
        normalized = _load_last_name() or _STANDARD_TOME_NAME
    elif not normalized:
        normalized = _STANDARD_TOME_NAME
    return normalized, _slugify(normalized)


def _tome_path(slug: str) -> Path:
    return _tomes_root() / f"{slug}.json"


def _standard_cards() -> list[CardTemplate]:
    ranks: list[tuple[str, str]] = [
        ("A", "Ace"),
        ("2", "Two"),
        ("3", "Three"),
        ("4", "Four"),
        ("5", "Five"),
        ("6", "Six"),
        ("7", "Seven"),
        ("8", "Eight"),
        ("9", "Nine"),
        ("10", "Ten"),
        ("J", "Jack"),
        ("Q", "Queen"),
        ("K", "King"),
    ]
    suits: list[tuple[str, str]] = [
        ("S", "Spades"),
        ("H", "Hearts"),
        ("D", "Diamonds"),
        ("C", "Clubs"),
    ]
    deck: list[CardTemplate] = []
    for suit_code, suit_name in suits:
        for rank_code, rank_name in ranks:
            code = f"{rank_code}{suit_code}"
            deck.append(CardTemplate(code=code, label=f"{rank_name} of {suit_name}"))
    deck.append(CardTemplate(code="JOKER_BLACK", label="Joker (Black)"))
    deck.append(CardTemplate(code="JOKER_RED", label="Joker (Red)"))
    return deck


def _ensure_schema(data: dict[str, Any]) -> dict[str, Any]:
    cards = data.setdefault("cards", {})
    for card_id, info in list(cards.items()):
        info.setdefault("label", card_id)
        info.setdefault("note", "")
        cards[card_id] = info
    zones = data.setdefault("zones", {})
    zones.setdefault("deck", [])
    zones.setdefault("discard", [])
    zones.setdefault("hole", [])
    zones.setdefault("hands", {})
    zones.setdefault("table", [])

    binds = data.setdefault("binds", {})
    try:
        bind_sequence = int(data.get("bind_sequence", 1))
    except (TypeError, ValueError):
        bind_sequence = 1
    data["bind_sequence"] = max(1, bind_sequence)

    valid_cards = set(cards)
    assigned: dict[str, str] = {}
    for bind_id, members in list(binds.items()):
        unique_members: list[str] = []
        for card_id in members:
            if card_id in valid_cards and card_id not in assigned:
                unique_members.append(card_id)
                assigned[card_id] = bind_id
        if len(unique_members) >= 2:
            binds[bind_id] = unique_members
        else:
            binds.pop(bind_id, None)

    state = data.setdefault("card_state", {})
    for card_id in list(state):
        if card_id not in cards:
            state.pop(card_id, None)

    for card_id in cards:
        card_state = state.setdefault(card_id, {"zone": "deck"})
        bind_id = assigned.get(card_id)
        if bind_id:
            card_state["bind"] = bind_id
        else:
            card_state.pop("bind", None)
        state[card_id] = card_state
    return data


def _new_bind_id(data: dict[str, Any]) -> str:
    sequence = int(data.get("bind_sequence", 1) or 1)
    bind_id = f"bind_{sequence}"
    data["bind_sequence"] = sequence + 1
    return bind_id


def _unbind_card(data: dict[str, Any], card_id: str) -> bool:
    binds: dict[str, list[str]] = data.setdefault("binds", {})
    state = data.setdefault("card_state", {})
    info = state.setdefault(card_id, {"zone": "deck"})
    bind_id = info.pop("bind", None)
    if not bind_id:
        return False
    members = binds.get(bind_id, [])
    if card_id in members:
        members = [member for member in members if member != card_id]
    if len(members) >= 2:
        binds[bind_id] = members
        for member in members:
            state.setdefault(member, {"zone": "deck"})["bind"] = bind_id
    else:
        for member in members:
            state.setdefault(member, {"zone": "deck"}).pop("bind", None)
        binds.pop(bind_id, None)
    return True


def _merge_cards_into_bind(data: dict[str, Any], cards: Iterable[str]) -> str | None:
    binds: dict[str, list[str]] = data.setdefault("binds", {})
    state = data.setdefault("card_state", {})

    ordered: list[str] = []
    for card_id in cards:
        if card_id not in ordered:
            ordered.append(card_id)
        bind_id = state.get(card_id, {}).get("bind")
        if bind_id and bind_id in binds:
            for member in binds[bind_id]:
                if member not in ordered:
                    ordered.append(member)

    if len(ordered) < 2:
        return None

    target_bind: str | None = None
    for card_id in ordered:
        bind_id = state.get(card_id, {}).get("bind")
        if bind_id and bind_id in binds:
            target_bind = bind_id
            break

    if target_bind is None:
        target_bind = _new_bind_id(data)

    # Remove members from other binds
    for bind_id, members in list(binds.items()):
        if bind_id == target_bind:
            continue
        remaining = [card for card in members if card not in ordered]
        if len(remaining) >= 2:
            binds[bind_id] = remaining
        else:
            for member in remaining:
                state.setdefault(member, {"zone": "deck"}).pop("bind", None)
            binds.pop(bind_id, None)

    binds[target_bind] = ordered
    for card_id in ordered:
        state.setdefault(card_id, {"zone": "deck"})["bind"] = target_bind

    _trim_bind_group(data, target_bind)

    return target_bind


def _move_card_to_hole(data: dict[str, Any], card_id: str) -> None:
    zones = data.setdefault("zones", {})
    state = data.setdefault("card_state", {})

    info = state.setdefault(card_id, {"zone": "deck"})
    current_zone = info.get("zone")
    holder = info.get("holder")

    if info.get("bind"):
        _unbind_card(data, card_id)

    if current_zone == "table":
        table = zones.setdefault("table", [])
        if card_id in table:
            table.remove(card_id)
    elif current_zone == "hand" and holder:
        hands = zones.setdefault("hands", {})
        hand_cards = list(hands.get(holder, []))
        if card_id in hand_cards:
            hand_cards.remove(card_id)
            if hand_cards:
                hands[holder] = hand_cards
            else:
                hands.pop(holder, None)
    elif current_zone == "deck":
        deck = zones.setdefault("deck", [])
        if card_id in deck:
            deck.remove(card_id)
    elif current_zone == "discard":
        discard = zones.setdefault("discard", [])
        if card_id in discard:
            discard.remove(card_id)
    elif current_zone and current_zone not in {"hole"}:
        zone_cards = zones.get(current_zone)
        if isinstance(zone_cards, list) and card_id in zone_cards:
            zone_cards.remove(card_id)
            zones[current_zone] = zone_cards

    hole = zones.setdefault("hole", [])
    if card_id not in hole:
        hole.append(card_id)

    info = state.setdefault(card_id, {})
    info["zone"] = "hole"
    info.pop("holder", None)
    info.pop("bind", None)
    state[card_id] = info


def _trim_bind_group(data: dict[str, Any], bind_id: str, *, max_size: int = 5) -> list[str]:
    binds: dict[str, list[str]] = data.setdefault("binds", {})
    removed: list[str] = []

    if bind_id not in binds:
        return removed

    while len(binds.get(bind_id, [])) > max_size:
        members = list(binds.get(bind_id, []))
        if not members:
            break
        card_id = random.choice(members)
        removed.append(card_id)
        _move_card_to_hole(data, card_id)

    return removed


def _trim_all_bind_groups(data: dict[str, Any], *, max_size: int = 5) -> list[str]:
    removed: list[str] = []
    binds: dict[str, list[str]] = data.setdefault("binds", {})
    for bind_id in list(binds):
        removed.extend(_trim_bind_group(data, bind_id, max_size=max_size))
    return removed


def _new_tome(name: str, slug: str) -> dict[str, Any]:
    templates = _standard_cards()
    random_cards = [card.code for card in templates]
    random.shuffle(random_cards)
    cards = {
        card.code: {"label": card.label, "note": ""}
        for card in templates
    }
    state = {code: {"zone": "deck"} for code in cards}
    return {
        "name": name,
        "slug": slug,
        "cards": cards,
        "zones": {
            "deck": random_cards,
            "discard": [],
            "hole": [],
            "hands": {},
            "table": [],
        },
        "card_state": state,
        "binds": {},
        "bind_sequence": 1,
    }


def _load_tome_data(requested: str | None) -> tuple[str, dict[str, Any], Path]:
    name, slug = _resolve_name(requested)
    path = _tome_path(slug)
    if not path.exists():
        data = _new_tome(name, slug)
        path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    else:
        data = json.loads(path.read_text(encoding="utf-8"))
        data = _ensure_schema(data)
        if not data.get("name"):
            data["name"] = name
        if not data.get("slug"):
            data["slug"] = slug
    _remember_last(name)
    return name, data, path


def _save_tome(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def _default_mask(provided: str | None) -> str:
    if provided:
        return str(provided)
    client_name = gw.find_value('CLIENT', fallback=None)
    if not client_name:
        client_name = gw.find_value('client', fallback=None)
    if not client_name:
        client_name = gw.context.get('CLIENT') or gw.context.get('client')
    if not client_name:
        client_name = os.environ.get('CLIENT')
    return str(client_name or "default")


def _card_payload(card_id: str, data: dict[str, Any]) -> dict[str, Any]:
    card = data.get("cards", {}).get(card_id, {"label": card_id, "note": ""})
    state = data.get("card_state", {}).get(card_id, {})
    payload = {
        "id": card_id,
        "label": card.get("label", card_id),
        "note": card.get("note", ""),
        "zone": state.get("zone", "unknown"),
    }
    holder = state.get("holder")
    if holder:
        payload["holder"] = holder
    bind_id = state.get("bind")
    if bind_id:
        payload["bind"] = bind_id
    return payload


_CARD_VALUE_MAP: dict[str, tuple[int, int]] = {
    "A": (1, 11),
    "2": (2, 2),
    "3": (3, 3),
    "4": (4, 4),
    "5": (5, 5),
    "6": (6, 6),
    "7": (7, 7),
    "8": (8, 8),
    "9": (9, 9),
    "10": (10, 10),
    "J": (10, 10),
    "Q": (10, 10),
    "K": (10, 10),
    "JOKER": (0, 0),
}


_RANK_WORD_MAP: dict[str, str] = {
    "ace": "A",
    "two": "2",
    "three": "3",
    "four": "4",
    "five": "5",
    "six": "6",
    "seven": "7",
    "eight": "8",
    "nine": "9",
    "ten": "10",
    "jack": "J",
    "queen": "Q",
    "king": "K",
    "joker": "JOKER",
}


def _resolve_card_rank(card_id: str, label: str | None = None) -> str | None:
    """Return the canonical rank code for a card identifier and label."""

    if card_id:
        upper = card_id.upper()
        if upper.startswith("10"):
            return "10"
        if "JOKER" in upper:
            return "JOKER"
        if upper and upper[0] in _CARD_VALUE_MAP:
            return upper[0]
    if label:
        lowered = label.strip().lower()
        if not lowered:
            return None
        if "joker" in lowered:
            return "JOKER"
        first_word = lowered.split()[0]
        return _RANK_WORD_MAP.get(first_word)
    return None


def _card_value_range(card_id: str, *, label: str | None = None) -> tuple[int, int] | None:
    """Return the blackjack value range for a given card."""

    rank = _resolve_card_rank(card_id, label)
    if not rank:
        return None
    return _CARD_VALUE_MAP.get(rank)


def shuffle(tome: str | None = None, *, all: bool = False, mask: str | None = None) -> dict[str, Any]:
    """Shuffle the selected tome, optionally recalling all cards before shuffling."""
    name, data, path = _load_tome_data(tome)
    zones = data.setdefault("zones", {})
    deck: list[str] = zones.setdefault("deck", [])
    hands: dict[str, list[str]] = zones.setdefault("hands", {})
    discard: list[str] = zones.setdefault("discard", [])
    hole: list[str] = zones.setdefault("hole", [])
    table: list[str] = zones.setdefault("table", [])
    state = data.setdefault("card_state", {})

    recalled: list[str] = []
    if all:
        for holder, cards in list(hands.items()):
            if cards:
                recalled.extend(cards)
                hands[holder] = []
        hands = {holder: cards for holder, cards in hands.items() if cards}
        zones["hands"] = hands
        if discard:
            recalled.extend(discard)
            zones["discard"] = []
        if hole:
            recalled.extend(hole)
            zones["hole"] = []
        if table:
            for card_id in list(table):
                _unbind_card(data, card_id)
            recalled.extend(table)
            zones["table"] = []
        for card_id in recalled:
            state[card_id] = {"zone": "deck"}
        deck.extend(recalled)

    random.shuffle(deck)
    data["zones"]["deck"] = deck
    _save_tome(path, data)

    return {
        "tome": name,
        "cards_in_deck": len(deck),
        "recalled": len(recalled),
        "message": "Deck shuffled" + (" with recall" if all and recalled else ""),
    }


def _draw_one(deck: list[str], state: dict[str, Any], mask: str) -> str | None:
    if not deck:
        return None
    card_id = deck.pop(0)
    state[card_id] = {"zone": "hand", "holder": mask}
    return card_id


def draw(tome: str | None = None, count: int = 1, *, mask: str | None = None) -> dict[str, Any]:
    """Draw ``count`` cards from the tome into the mask's hand."""
    name, data, path = _load_tome_data(tome)
    zones = data.setdefault("zones", {})
    deck: list[str] = zones.setdefault("deck", [])
    hands: dict[str, list[str]] = zones.setdefault("hands", {})
    state = data.setdefault("card_state", {})

    holder = _default_mask(mask)
    hand = hands.setdefault(holder, [])

    drawn: list[str] = []
    for _ in range(max(1, int(count))):
        card_id = _draw_one(deck, state, holder)
        if card_id is None:
            break
        hand.append(card_id)
        drawn.append(card_id)

    hands[holder] = hand
    data["zones"]["deck"] = deck
    data["zones"]["hands"] = hands
    _save_tome(path, data)

    return {
        "tome": name,
        "mask": holder,
        "drawn": [_card_payload(card_id, data) for card_id in drawn],
        "remaining_in_deck": len(deck),
    }


def _resolve_card_identifier(cards: Iterable[str], identifier: str | None) -> str | None:
    if identifier is None:
        return None
    normalized = identifier.strip()
    if not normalized:
        return None
    card_list = list(cards)
    if normalized.isdigit():
        index = int(normalized) - 1
        if 0 <= index < len(card_list):
            return card_list[index]
    normalized_upper = normalized.upper()
    for card_id in card_list:
        if card_id.upper() == normalized_upper:
            return card_id
    return None


def _normalize_card_queries(*candidates: Any) -> list[str]:
    queries: list[str] = []
    for candidate in candidates:
        if candidate is None:
            continue
        if isinstance(candidate, str):
            parts = [part for part in candidate.replace(",", " ").split() if part]
            queries.extend(parts)
        else:
            for item in candidate:
                if item is None:
                    continue
                parts = str(item).replace(",", " ").split()
                queries.extend(part for part in parts if part)
    return queries


def _resolve_card_queries(cards: list[str], queries: list[str]) -> tuple[list[str], list[str]]:
    remaining = list(cards)
    resolved: list[str] = []
    missing: list[str] = []
    for query in queries:
        target = _resolve_card_identifier(remaining, query)
        if target:
            resolved.append(target)
            remaining.remove(target)
        else:
            missing.append(query)
    return resolved, missing


def _move_hand_cards_to_table(
    data: dict[str, Any],
    holder: str,
    card_ids: Iterable[str],
) -> list[str]:
    zones = data.setdefault("zones", {})
    hands: dict[str, list[str]] = zones.setdefault("hands", {})
    table: list[str] = zones.setdefault("table", [])
    state = data.setdefault("card_state", {})

    hand_cards = list(hands.get(holder, []))
    moved: list[str] = []
    for card_id in card_ids:
        if card_id in hand_cards:
            hand_cards.remove(card_id)
            if card_id in table:
                table.remove(card_id)
            table.append(card_id)
            state[card_id] = {"zone": "table", "holder": holder}
            moved.append(card_id)

    if hand_cards:
        hands[holder] = hand_cards
    elif holder in hands:
        del hands[holder]

    zones["table"] = table
    zones["hands"] = hands
    return moved


def _move_table_cards_to_hand(
    data: dict[str, Any],
    holder: str,
    card_ids: Iterable[str],
) -> list[str]:
    zones = data.setdefault("zones", {})
    hands: dict[str, list[str]] = zones.setdefault("hands", {})
    table: list[str] = zones.setdefault("table", [])
    state = data.setdefault("card_state", {})

    hand_cards = hands.setdefault(holder, [])
    moved: list[str] = []
    for card_id in card_ids:
        if card_id in table:
            _unbind_card(data, card_id)
            table.remove(card_id)
            hand_cards.append(card_id)
            state[card_id] = {"zone": "hand", "holder": holder}
            moved.append(card_id)

    zones["table"] = table
    zones["hands"] = hands
    return moved


def hand(tome: str | None = None, *, mask: str | None = None, card: str | None = None, note: str | None = None) -> dict[str, Any]:
    """Inspect the hand for the given mask, optionally updating a card note."""
    name, data, path = _load_tome_data(tome)
    zones = data.setdefault("zones", {})
    hands: dict[str, list[str]] = zones.setdefault("hands", {})
    cards = data.setdefault("cards", {})

    holder = _default_mask(mask)
    hand_cards = hands.get(holder, [])
    updated = None

    target_id = _resolve_card_identifier(hand_cards, card)
    if target_id and note is not None:
        card_info = cards.setdefault(target_id, {"label": target_id, "note": ""})
        card_info["note"] = note
        cards[target_id] = card_info
        data["cards"] = cards
        updated = _card_payload(target_id, data)
        _save_tome(path, data)
    elif note is not None and card and not target_id:
        # Persist no changes but update file to ensure structure is saved
        _save_tome(path, data)

    payload_hand = [_card_payload(card_id, data) for card_id in hand_cards]
    result = {
        "tome": name,
        "mask": holder,
        "cards": payload_hand,
        "count": len(payload_hand),
    }
    if updated:
        result["updated"] = updated
    elif note is not None and card and not target_id:
        result["warning"] = f"Card '{card}' not found in hand"
    return result


def bind(
    tome: str | None = None,
    *,
    mask: str | None = None,
    card: str | None = None,
    cards: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Move one or more cards from a hand onto the shared table."""

    name, data, path = _load_tome_data(tome)
    zones = data.setdefault("zones", {})
    hands: dict[str, list[str]] = zones.setdefault("hands", {})
    table: list[str] = zones.setdefault("table", [])

    holder = _default_mask(mask)
    hand_cards = list(hands.get(holder, []))
    queries = _normalize_card_queries(card, cards)
    if not queries and hand_cards:
        queries = [hand_cards[0]]

    selected, missing = _resolve_card_queries(hand_cards, queries) if queries else ([], queries)
    moved = _move_hand_cards_to_table(data, holder, selected)
    if moved or missing:
        _save_tome(path, data)

    result = {
        "tome": name,
        "mask": holder,
        "moved": [_card_payload(card_id, data) for card_id in moved],
        "table_count": len(table),
    }
    if missing:
        result["missing"] = missing
    if moved:
        result["message"] = f"Moved {len(moved)} card(s) to table"
    else:
        result["message"] = "No cards moved"
    return result


def pick(
    tome: str | None = None,
    *,
    mask: str | None = None,
    card: str | None = None,
    cards: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Return cards from the shared table to a hand."""

    name, data, path = _load_tome_data(tome)
    zones = data.setdefault("zones", {})
    table: list[str] = zones.setdefault("table", [])

    holder = _default_mask(mask)
    queries = _normalize_card_queries(card, cards)
    if not queries and table:
        queries = [table[-1]]

    selected, missing = _resolve_card_queries(table, queries) if queries else ([], queries)
    moved = _move_table_cards_to_hand(data, holder, selected)
    if moved or missing:
        _save_tome(path, data)

    hands: dict[str, list[str]] = zones.setdefault("hands", {})
    hand_cards = hands.get(holder, [])
    result = {
        "tome": name,
        "mask": holder,
        "moved": [_card_payload(card_id, data) for card_id in moved],
        "hand_count": len(hand_cards),
        "table_remaining": len(table),
    }
    if missing:
        result["missing"] = missing
    if moved:
        result["message"] = f"Picked {len(moved)} card(s) from table"
    else:
        result["message"] = "No cards picked"
    return result


def open_viewer(
    tome: str | None = None,
    *,
    mask: str | None = None,
    refresh_interval: float = 0.5,
    maximize: bool = False,
) -> dict[str, Any]:
    """Open a resizable pygame window visualizing the tome state.

    The viewer shows the discard pile ("used tome") as a face-down stack with a
    card count in the lower-right corner while rendering the drawn cards face up
    on the table. When ``mask`` is provided, only that mask's hand is displayed;
    otherwise all hands are shown. The display automatically reloads the tome
    file when it changes on disk so it can be left open while other commands
    manipulate the tome. When ``maximize`` is ``True`` the window attempts to
    match the desktop size so the viewer launches maximized.
    """

    name, data, path = _load_tome_data(tome)

    import pygame

    pygame.init()
    try:
        flags = pygame.RESIZABLE
        window_size = (960, 720)
        if maximize:
            os.environ.setdefault("SDL_VIDEO_CENTERED", "0")
            os.environ.setdefault("SDL_VIDEO_WINDOW_POS", "0,0")
            try:
                desktop_sizes = pygame.display.get_desktop_sizes()
            except pygame.error:
                desktop_sizes = []
            target_size: tuple[int, int] | None = None
            if desktop_sizes:
                width, height = desktop_sizes[0]
                if width > 0 and height > 0:
                    target_size = (int(width), int(height))
            if target_size is None:
                try:
                    display_info = pygame.display.Info()
                except pygame.error:
                    display_info = None
                if display_info:
                    width = getattr(display_info, "current_w", 0) or 0
                    height = getattr(display_info, "current_h", 0) or 0
                    if width > 0 and height > 0:
                        target_size = (int(width), int(height))
            if target_size is not None:
                window_size = target_size
        pygame.display.set_mode(window_size, flags)
    except pygame.error as exc:  # pragma: no cover - depends on environment
        pygame.quit()
        return {"tome": name, "error": f"Unable to open display: {exc}"}

    pygame.display.set_caption(f"{name} Tome Viewer")
    font = pygame.font.SysFont(None, 24)
    small_font = pygame.font.SysFont(None, 18)
    clock = pygame.time.Clock()

    card_width, card_height = 160, 220
    padding = 24
    hand_gap = 18
    bind_step_x = 26
    bind_step_y = 18

    card_positions: dict[str, pygame.Rect] = {}
    draw_order: list[str] = []
    dragging_card: str | None = None
    drag_offset = (0, 0)
    dragging_group_keys: dict[str, str] = {}
    dragging_group_members: list[str] = []
    dragging_origin_zone: str | None = None
    dragging_origin_holder: str | None = None
    dragging_anchor_card_id: str | None = None
    dragging_bind_id: str | None = None
    group_offsets: dict[str, tuple[int, int]] = {}
    card_info: dict[str, dict[str, Any]] = {}
    table_line_y = 0
    hand_drop_ratio = 0.3
    hover_raise_ratio = 0.4
    hover_speed_ratio = 0.5
    hover_offsets: dict[str, float] = {}
    discard_hover_offset = 0.0
    last_click_time = 0
    last_click_pos: tuple[int, int] | None = None
    last_click_button: int | None = None
    double_click_threshold_ms = 350

    mask_filter = _default_mask(mask) if mask is not None else None
    last_mtime = path.stat().st_mtime if path.exists() else None
    watch_interval = max(0.1, float(refresh_interval))

    updates: Queue[tuple[dict[str, Any], float]] = Queue()
    stop_event = Event()

    def _enqueue_update(updated_data: dict[str, Any], mtime: float | None) -> None:
        if mtime is None:
            return
        updates.put((updated_data, mtime))

    def _watch_file() -> None:
        local_last = last_mtime
        while not stop_event.is_set():
            if path.exists():
                try:
                    mtime = path.stat().st_mtime
                except OSError:
                    mtime = None
                if mtime and (local_last is None or mtime > local_last):
                    try:
                        loaded = json.loads(path.read_text(encoding="utf-8"))
                    except (OSError, json.JSONDecodeError):
                        pass
                    else:
                        ensured = _ensure_schema(loaded)
                        _enqueue_update(ensured, mtime)
                        local_last = mtime
            stop_event.wait(watch_interval)

    watcher = Thread(target=_watch_file, daemon=True)
    watcher.start()

    table_color = (16, 99, 45)
    card_color = (245, 245, 245)
    card_border = (30, 30, 30)
    face_down_color = (80, 55, 33)
    text_color = (10, 10, 10)
    face_down_text = (230, 230, 230)
    guide_color = (220, 220, 220)
    value_good_color = (32, 170, 70)
    value_bad_color = (200, 45, 45)

    lift_pixels = 14
    lift_duration_ms = 160
    shadow_offset = (8, 10)
    lifted_cards: dict[str, dict[str, float]] = {}

    def _current_lift_offset(key: str) -> float:
        state = lifted_cards.get(key)
        if not state:
            return 0.0
        start = float(state.get("start", 0.0))
        elapsed = max(0.0, pygame.time.get_ticks() - start)
        progress = min(1.0, elapsed / max(lift_duration_ms, 1))
        eased = 1.0 - (1.0 - progress) * (1.0 - progress)
        offset = lift_pixels * eased
        state["offset"] = offset
        return offset

    def _wrap_text(text: str, max_width: int) -> list[str]:
        words = text.split()
        if not words:
            return [""]
        lines: list[str] = []
        current = words[0]
        for word in words[1:]:
            test = f"{current} {word}"
            if font.size(test)[0] <= max_width:
                current = test
            else:
                lines.append(current)
                current = word
        lines.append(current)
        return lines

    discard_rect = pygame.Rect(0, 0, 0, 0)

    def _draw_random_card(target_holder: str) -> bool:
        nonlocal data, last_mtime
        zones = data.setdefault("zones", {})
        deck: list[str] = zones.setdefault("deck", [])
        if not deck:
            return False
        index = random.randrange(len(deck))
        card_id = deck.pop(index)
        zones["deck"] = deck
        hands: dict[str, list[str]] = zones.setdefault("hands", {})
        hand = hands.setdefault(target_holder, [])
        hand.append(card_id)
        zones["hands"][target_holder] = hand
        state = data.setdefault("card_state", {})
        state[card_id] = {"zone": "hand", "holder": target_holder}
        _save_tome(path, data)
        try:
            last_mtime = path.stat().st_mtime
        except OSError:
            last_mtime = None
        return True

    running = True
    displayed_cards = 0
    discard_count = len(data.get("zones", {}).get("discard", []))
    hole_count = len(data.get("zones", {}).get("hole", []))

    initial_trimmed = _trim_all_bind_groups(data)
    if initial_trimmed:
        _save_tome(path, data)
        discard_count = len(data.get("zones", {}).get("discard", []))
        hole_count = len(data.get("zones", {}).get("hole", []))
        try:
            last_mtime = path.stat().st_mtime
        except OSError:
            last_mtime = None

    try:
        while running:
            try:
                while True:
                    updated_data, mtime = updates.get_nowait()
                    trimmed_cards = _trim_all_bind_groups(updated_data)
                    data = updated_data
                    name = data.get("name", name)
                    discard_count = len(data.get("zones", {}).get("discard", []))
                    hole_count = len(data.get("zones", {}).get("hole", []))
                    if trimmed_cards:
                        _save_tome(path, data)
                        try:
                            last_mtime = path.stat().st_mtime
                        except OSError:
                            last_mtime = None
                    else:
                        last_mtime = mtime
            except Empty:
                pass

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN and event.key in (pygame.K_ESCAPE, pygame.K_q):
                    running = False
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    mouse_pos = event.pos
                    current_time = pygame.time.get_ticks()
                    clicked_discard = discard_rect.collidepoint(mouse_pos)
                    is_double_click = False
                    if clicked_discard:
                        if (
                            last_click_button == event.button
                            and last_click_pos is not None
                            and discard_rect.collidepoint(last_click_pos)
                            and current_time - last_click_time <= double_click_threshold_ms
                        ):
                            is_double_click = True
                        last_click_time = current_time
                        last_click_pos = mouse_pos
                        last_click_button = event.button
                        if getattr(event, "clicks", 0) >= 2 or is_double_click:
                            target_holder = mask_filter or _default_mask(None)
                            if target_holder:
                                _draw_random_card(target_holder)
                            continue
                    else:
                        last_click_time = current_time
                        last_click_pos = mouse_pos
                        last_click_button = event.button
                    mods = pygame.key.get_mods()
                    for key in reversed(draw_order):
                        rect = card_positions.get(key)
                        if not (rect and rect.collidepoint(mouse_pos)):
                            continue
                        info = card_info.get(key)
                        if not info:
                            continue
                        dragging_card = key
                        dragging_anchor_card_id = info.get("card_id")
                        dragging_origin_zone = info.get("zone")
                        dragging_origin_holder = info.get("holder")
                        dragging_bind_id = info.get("bind")
                        drag_offset = (mouse_pos[0] - rect.x, mouse_pos[1] - rect.y)
                        members = list(info.get("bind_members") or [info["card_id"]])
                        if dragging_anchor_card_id in members:
                            members.remove(dragging_anchor_card_id)
                            members.insert(0, dragging_anchor_card_id)
                        ctrl_pressed = bool(mods & pygame.KMOD_CTRL)
                        if ctrl_pressed and len(members) > 1 and dragging_anchor_card_id:
                            if _unbind_card(data, dragging_anchor_card_id):
                                _save_tome(path, data)
                                try:
                                    last_mtime = path.stat().st_mtime
                                except OSError:
                                    last_mtime = None
                                members = [dragging_anchor_card_id]
                                dragging_bind_id = None
                                payload = _card_payload(dragging_anchor_card_id, data)
                                info = {
                                    "zone": payload.get("zone", info.get("zone")),
                                    "holder": payload.get("holder"),
                                    "card_id": dragging_anchor_card_id,
                                    "payload": payload,
                                }
                                card_info[key] = info
                                dragging_origin_zone = info.get("zone")
                                dragging_origin_holder = info.get("holder")
                        dragging_group_members = members
                        group_offsets = {}
                        dragging_group_keys = {}
                        zone = dragging_origin_zone
                        anchor_member_key: str | None = None
                        for index, member in enumerate(members):
                            if zone == "table":
                                member_key = f"table::{member}"
                            else:
                                if member != dragging_anchor_card_id:
                                    continue
                                member_key = key
                            member_rect = card_positions.get(member_key)
                            if member_rect is None:
                                offset_x = bind_step_x * index
                                offset_y = bind_step_y * index
                                member_rect = pygame.Rect(
                                    rect.x + offset_x,
                                    rect.y + offset_y,
                                    card_width,
                                    card_height,
                                )
                                card_positions[member_key] = member_rect
                            else:
                                member_rect.width = card_width
                                member_rect.height = card_height
                            if member_key == key:
                                offset = (0, 0)
                            else:
                                offset = (member_rect.x - rect.x, member_rect.y - rect.y)
                            group_offsets[member] = offset
                            dragging_group_keys[member] = member_key
                            if member_key == key and member_key in draw_order:
                                draw_order.remove(member_key)
                            if member == dragging_anchor_card_id:
                                anchor_member_key = member_key
                        reordered_keys = [dragging_group_keys[m] for m in members if m in dragging_group_keys]
                        if not anchor_member_key and reordered_keys:
                            anchor_member_key = reordered_keys[0]
                        if anchor_member_key and anchor_member_key not in draw_order:
                            draw_order.append(anchor_member_key)
                        if len(members) <= 1:
                            dragging_bind_id = None
                        if dragging_origin_zone == "table":
                            now = pygame.time.get_ticks()
                            affected_keys = list(dragging_group_keys.values())
                            if dragging_card and dragging_card not in affected_keys:
                                affected_keys.append(dragging_card)
                            if not affected_keys and key:
                                affected_keys.append(key)
                            for member_key in affected_keys:
                                if member_key:
                                    lifted_cards[member_key] = {"start": float(now), "offset": 0.0}
                        break
                elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                    if dragging_card:
                        rect = card_positions.get(dragging_card)
                        info = card_info.get(dragging_card)
                        anchor_card_id = dragging_anchor_card_id or (info.get("card_id") if info else None)
                        holder = dragging_origin_holder or (info.get("holder") if info else None)
                        zone = dragging_origin_zone or (info.get("zone") if info else None)
                        moved_to_hand = False
                        lift_keys_to_clear = list(dragging_group_keys.values())
                        if dragging_card and dragging_card not in lift_keys_to_clear:
                            lift_keys_to_clear.append(dragging_card)
                        if rect and anchor_card_id:
                            if zone != "table" and rect.bottom < table_line_y and holder:
                                moved = _move_hand_cards_to_table(data, holder, [anchor_card_id])
                                if moved:
                                    new_key = f"table::{anchor_card_id}"
                                    card_positions[new_key] = rect
                                    if dragging_card != new_key:
                                        card_positions.pop(dragging_card, None)
                                    if dragging_card in draw_order:
                                        draw_order.remove(dragging_card)
                                    if new_key not in draw_order:
                                        draw_order.append(new_key)
                                    dragging_card = new_key
                                    zone = "table"
                                    dragging_origin_zone = "table"
                                    dragging_group_members = [anchor_card_id]
                                    dragging_group_keys = {anchor_card_id: new_key}
                                    group_offsets = {anchor_card_id: (0, 0)}
                                    dragging_bind_id = None
                                    _save_tome(path, data)
                                    try:
                                        last_mtime = path.stat().st_mtime
                                    except OSError:
                                        last_mtime = None
                            elif zone == "table" and rect.bottom >= table_line_y:
                                lift_offset = 0.0
                                if dragging_card:
                                    lift_offset = _current_lift_offset(dragging_card)
                                visual_bottom = rect.bottom - int(round(lift_offset))
                                if visual_bottom < table_line_y:
                                    lift_offset = 0.0
                                if visual_bottom >= table_line_y:
                                    if len(dragging_group_members) > 1 or dragging_bind_id:
                                        rect.y = max(padding, table_line_y - card_height - 4)
                                        rect.height = card_height
                                        rect.width = card_width
                                        for member, key_name in dragging_group_keys.items():
                                            if key_name == dragging_card:
                                                continue
                                            offset = group_offsets.get(member, (bind_step_x, bind_step_y))
                                            member_rect = card_positions.get(key_name)
                                            if member_rect:
                                                member_rect.x = rect.x + offset[0]
                                                member_rect.y = rect.y + offset[1]
                                                member_rect.width = card_width
                                                member_rect.height = card_height
                                    else:
                                        target_holder = holder or mask_filter or _default_mask(None)
                                        if target_holder:
                                            moved = _move_table_cards_to_hand(data, target_holder, [anchor_card_id])
                                            if moved:
                                                new_key = f"hand:{target_holder}:{anchor_card_id}"
                                                card_positions[new_key] = rect
                                                card_positions.pop(dragging_card, None)
                                                if dragging_card in draw_order:
                                                    draw_order.remove(dragging_card)
                                                if new_key not in draw_order:
                                                    draw_order.append(new_key)
                                                moved_to_hand = True
                                                _save_tome(path, data)
                                                try:
                                                    last_mtime = path.stat().st_mtime
                                                except OSError:
                                                    last_mtime = None
                        if rect and not moved_to_hand and zone == "table" and anchor_card_id:
                            table_keys = []
                            for member in dragging_group_members:
                                key_name = dragging_group_keys.get(member) or f"table::{member}"
                                table_keys.append((member, key_name))
                            collided: list[str] = []
                            for member, key_name in table_keys:
                                member_rect = card_positions.get(key_name)
                                if not member_rect:
                                    continue
                                for other_key, other_rect in card_positions.items():
                                    if other_key == key_name or not other_key.startswith("table::"):
                                        continue
                                    if other_rect is None:
                                        continue
                                    if member_rect.colliderect(other_rect):
                                        other_id = other_key.split("::", 1)[1]
                                        other_info = card_info.get(other_key)
                                        if other_info and other_info.get("bind_members") and len(other_info["bind_members"]) > 1:
                                            for candidate in other_info["bind_members"]:
                                                if candidate not in collided and candidate not in dragging_group_members:
                                                    collided.append(candidate)
                                        else:
                                            if other_id not in collided and other_id not in dragging_group_members:
                                                collided.append(other_id)
                            if collided:
                                merge_list = dragging_group_members + collided
                                bind_id = _merge_cards_into_bind(data, merge_list)
                                if bind_id:
                                    _save_tome(path, data)
                                    try:
                                        last_mtime = path.stat().st_mtime
                                    except OSError:
                                        last_mtime = None
                                    members = data.get("binds", {}).get(bind_id, [])
                                    if members:
                                        if anchor_card_id in members:
                                            anchor_index = members.index(anchor_card_id)
                                        else:
                                            anchor_index = 0
                                        base_x = rect.x - bind_step_x * anchor_index
                                        base_y = rect.y - bind_step_y * anchor_index
                                        dragging_group_members = list(members)
                                        dragging_group_keys = {}
                                        for idx, member in enumerate(members):
                                            key_name = f"table::{member}"
                                            member_rect = card_positions.get(key_name)
                                            if member_rect is None:
                                                member_rect = pygame.Rect(
                                                    base_x + bind_step_x * idx,
                                                    base_y + bind_step_y * idx,
                                                    card_width,
                                                    card_height,
                                                )
                                                card_positions[key_name] = member_rect
                                            else:
                                                member_rect.x = base_x + bind_step_x * idx
                                                member_rect.y = base_y + bind_step_y * idx
                                                member_rect.width = card_width
                                                member_rect.height = card_height
                                            dragging_group_keys[member] = key_name
                                            if key_name not in draw_order:
                                                draw_order.append(key_name)
                                        group_offsets = {
                                            member: (bind_step_x * idx, bind_step_y * idx)
                                            for idx, member in enumerate(members)
                                        }
                                        dragging_bind_id = bind_id
                        for key_name in lift_keys_to_clear:
                            lifted_cards.pop(key_name, None)
                        dragging_card = None
                        dragging_group_keys = {}
                        dragging_group_members = []
                        dragging_origin_zone = None
                        dragging_origin_holder = None
                        dragging_anchor_card_id = None
                        dragging_bind_id = None
                        group_offsets = {}
                elif event.type == pygame.MOUSEMOTION and dragging_card:
                    rect = card_positions.get(dragging_card)
                    if rect is not None and event.buttons[0]:
                        rect.x = event.pos[0] - drag_offset[0]
                        rect.y = event.pos[1] - drag_offset[1]
                        rect.width = card_width
                        rect.height = card_height
                        for member in dragging_group_members:
                            key_name = dragging_group_keys.get(member)
                            if not key_name or key_name == dragging_card:
                                continue
                            member_rect = card_positions.get(key_name)
                            offset = group_offsets.get(member)
                            if offset is None:
                                index = dragging_group_members.index(member)
                                offset = (bind_step_x * index, bind_step_y * index)
                                group_offsets[member] = offset
                            if member_rect is None:
                                member_rect = pygame.Rect(
                                    rect.x + offset[0],
                                    rect.y + offset[1],
                                    card_width,
                                    card_height,
                                )
                                card_positions[key_name] = member_rect
                            else:
                                member_rect.x = rect.x + offset[0]
                                member_rect.y = rect.y + offset[1]
                                member_rect.width = card_width
                                member_rect.height = card_height
                    elif not event.buttons[0]:
                        for key_name in list(dragging_group_keys.values()):
                            lifted_cards.pop(key_name, None)
                        if dragging_card:
                            lifted_cards.pop(dragging_card, None)
                        dragging_card = None
                        dragging_group_keys = {}
                        dragging_group_members = []
                        dragging_origin_zone = None
                        dragging_origin_holder = None
                        dragging_anchor_card_id = None
                        dragging_bind_id = None
                        group_offsets = {}

            surface = pygame.display.get_surface()
            if surface is None:
                break
            width, height = surface.get_size()
            surface.fill(table_color)

            columns = max(1, (width - padding) // (card_width + padding))

            hand_drop_offset = int(card_height * hand_drop_ratio)
            hover_raise = max(hand_drop_offset + 8, int(card_height * hover_raise_ratio))
            hover_speed = max(4, int(max(hover_raise * hover_speed_ratio, 1)))

            discard_base_y = height - card_height - padding + hand_drop_offset
            discard_rect = pygame.Rect(
                width - card_width - padding,
                discard_base_y,
                card_width,
                card_height,
            )
            hole_rect = pygame.Rect(
                padding,
                discard_base_y,
                card_width,
                card_height,
            )
            table_line_y = max(0, discard_base_y - 16)
            table_area_bottom = table_line_y - hand_gap
            max_table_y = max(padding, table_area_bottom - card_height)

            zones = data.get("zones", {})
            discard_count = len(zones.get("discard", []))
            hole_count = len(zones.get("hole", []))
            table_cards: list[str] = zones.get("table", [])
            hands: dict[str, list[str]] = zones.get("hands", {})

            updated_info: dict[str, dict[str, Any]] = {}
            hand_layouts: dict[str, pygame.Rect] = {}

            binds_map: dict[str, list[str]] = data.get("binds", {})
            state = data.get("card_state", {})
            table_groups: list[tuple[str | None, list[str]]] = []
            seen_table: set[str] = set()
            for card_id in table_cards:
                if card_id in seen_table:
                    continue
                bind_id = state.get(card_id, {}).get("bind")
                members: list[str] = []
                if bind_id and bind_id in binds_map:
                    members = [member for member in binds_map[bind_id] if member in table_cards]
                if bind_id and len(members) < 2:
                    members = []
                if members:
                    if (
                        dragging_anchor_card_id
                        and dragging_anchor_card_id in members
                        and members[0] != dragging_anchor_card_id
                    ):
                        members = [dragging_anchor_card_id] + [m for m in members if m != dragging_anchor_card_id]
                    table_groups.append((bind_id, members))
                    seen_table.update(members)
                else:
                    table_groups.append((None, [card_id]))
                    seen_table.add(card_id)

            for index, (bind_id, members) in enumerate(table_groups):
                anchor_card_id = members[0]
                anchor_key = f"table::{anchor_card_id}"
                rect = card_positions.get(anchor_key)
                if rect is None:
                    col = index % columns
                    row = index // columns
                    x = padding + col * (card_width + padding)
                    y = padding + row * (card_height + padding)
                    if y + card_height > table_area_bottom:
                        y = max_table_y
                    rect = pygame.Rect(x, y, card_width, card_height)
                    card_positions[anchor_key] = rect
                else:
                    rect.width = card_width
                    rect.height = card_height

                # Ensure members follow the anchor position
                for member_index, member in enumerate(members):
                    key = f"table::{member}"
                    offset_x = bind_step_x * member_index
                    offset_y = bind_step_y * member_index
                    if key == anchor_key:
                        member_rect = rect
                    else:
                        member_rect = card_positions.get(key)
                        desired_x = rect.x + offset_x
                        desired_y = rect.y + offset_y
                        if member_rect is None:
                            member_rect = pygame.Rect(
                                desired_x,
                                desired_y,
                                card_width,
                                card_height,
                            )
                            card_positions[key] = member_rect
                        else:
                            member_rect.x = desired_x
                            member_rect.y = desired_y
                            member_rect.width = card_width
                            member_rect.height = card_height

                non_anchor_members = members[1:]
                for member in non_anchor_members:
                    key = f"table::{member}"
                    payload = _card_payload(member, data)
                    entry = {
                        "zone": "table",
                        "holder": payload.get("holder"),
                        "card_id": member,
                        "payload": payload,
                    }
                    if bind_id and len(members) >= 2:
                        entry["bind"] = bind_id
                        entry["bind_members"] = tuple(members)
                    updated_info[key] = entry

                anchor_payload = _card_payload(anchor_card_id, data)
                anchor_entry = {
                    "zone": "table",
                    "holder": anchor_payload.get("holder"),
                    "card_id": anchor_card_id,
                    "payload": anchor_payload,
                }
                if bind_id and len(members) >= 2:
                    anchor_entry["bind"] = bind_id
                    anchor_entry["bind_members"] = tuple(members)
                updated_info[anchor_key] = anchor_entry

            if mask_filter:
                holder_sequence = [mask_filter]
            else:
                holder_sequence = [holder for holder, cards in sorted(hands.items()) if cards]

            if mask_filter and mask_filter not in holder_sequence:
                holder_sequence.append(mask_filter)

            row_index = 0
            for holder in holder_sequence:
                cards_in_hand = list(hands.get(holder, []))
                if not cards_in_hand and mask_filter is None:
                    continue
                row_y = table_line_y + hand_gap + row_index * (card_height + hand_gap)
                anchor_right = discard_rect.x - hand_gap
                for offset, card_id in enumerate(reversed(cards_in_hand)):
                    key = f"hand:{holder}:{card_id}"
                    rect = card_positions.get(key)
                    x = anchor_right - card_width - offset * (card_width + hand_gap)
                    base_rect = pygame.Rect(x, row_y, card_width, card_height)
                    if rect is None:
                        rect = base_rect.copy()
                        card_positions[key] = rect
                    elif dragging_card != key:
                        rect.x = base_rect.x
                        rect.width = card_width
                        rect.height = card_height
                    else:
                        rect.width = card_width
                        rect.height = card_height
                    hand_layouts[key] = base_rect

                    payload = _card_payload(card_id, data)
                    updated_info[key] = {
                        "zone": "hand",
                        "holder": holder,
                        "card_id": card_id,
                        "payload": payload,
                    }
                row_index += 1

            valid_keys = set(updated_info)
            for key in list(card_positions):
                if key not in valid_keys:
                    del card_positions[key]
            draw_order = [key for key in draw_order if key in valid_keys]
            for key in updated_info:
                if key not in draw_order:
                    draw_order.append(key)
            card_info = updated_info
            if dragging_card and dragging_card not in card_positions:
                dragging_card = None

            mouse_pos = pygame.mouse.get_pos()
            shift_pressed = bool(pygame.key.get_mods() & pygame.KMOD_SHIFT)
            hover_card_ids: list[str] = []
            hover_anchor_payload: dict[str, Any] | None = None
            tooltip_lines: list[tuple[str, tuple[int, int, int]]] = []
            for key in list(hover_offsets):
                if key not in hand_layouts:
                    del hover_offsets[key]
            for key, base_rect in hand_layouts.items():
                if dragging_card == key:
                    hover_offsets[key] = 0.0
                    continue
                rect = card_positions.get(key)
                if rect is None:
                    continue
                hovered = rect.collidepoint(mouse_pos)
                target_offset = -hover_raise if hovered else 0
                current_offset = hover_offsets.get(key, 0.0)
                if current_offset < target_offset:
                    current_offset = min(target_offset, current_offset + hover_speed)
                elif current_offset > target_offset:
                    current_offset = max(target_offset, current_offset - hover_speed)
                hover_offsets[key] = current_offset
                rect.x = base_rect.x
                rect.width = base_rect.width
                rect.height = base_rect.height
                rect.y = base_rect.y + int(current_offset)

            discard_current_rect = pygame.Rect(
                discard_rect.x,
                discard_base_y + int(discard_hover_offset),
                discard_rect.width,
                discard_rect.height,
            )
            hovered_discard = discard_current_rect.collidepoint(mouse_pos)
            discard_target = -hover_raise if hovered_discard else 0
            if discard_hover_offset < discard_target:
                discard_hover_offset = min(discard_target, discard_hover_offset + hover_speed)
            elif discard_hover_offset > discard_target:
                discard_hover_offset = max(discard_target, discard_hover_offset - hover_speed)
            discard_rect.y = discard_base_y + int(discard_hover_offset)

            displayed_cards = len(table_cards)
            if mask_filter:
                displayed_cards += len(hands.get(mask_filter, []))
            else:
                displayed_cards += sum(len(cards) for cards in hands.values())

            if table_line_y > 0:
                dash_length = 12
                dash_gap = 8
                step = dash_length + dash_gap
                for start_x in range(0, width, step):
                    end_x = min(start_x + dash_length, width)
                    pygame.draw.line(
                        surface,
                        guide_color,
                        (start_x, table_line_y),
                        (end_x, table_line_y),
                        2,
                    )

            for key in draw_order:
                info = card_info.get(key)
                rect = card_positions.get(key)
                if not info or rect is None:
                    continue

                card_id = info.get("card_id")
                payload = info.get("payload", {})
                render_rect = rect.copy()
                lift_offset = 0.0
                if info.get("zone") == "table":
                    lift_offset = _current_lift_offset(key)
                    if lift_offset:
                        render_rect.y -= int(round(lift_offset))

                hovered = render_rect.collidepoint(mouse_pos)
                if hovered:
                    members = list(info.get("bind_members") or [])
                    if card_id and not members:
                        members = [card_id]
                    if members:
                        hover_card_ids = [member for member in members if member]
                        if hover_card_ids:
                            hover_anchor_payload = payload

                if lift_offset:
                    shadow_rect = pygame.Rect(
                        render_rect.x + shadow_offset[0],
                        render_rect.y + shadow_offset[1] + int(round(lift_offset * 0.5)),
                        render_rect.width,
                        render_rect.height,
                    )
                    shadow_surface = pygame.Surface((shadow_rect.width, shadow_rect.height), pygame.SRCALPHA)
                    pygame.draw.rect(
                        shadow_surface,
                        (0, 0, 0, 90),
                        shadow_surface.get_rect(),
                        border_radius=12,
                    )
                    surface.blit(shadow_surface, shadow_rect.topleft)

                pygame.draw.rect(surface, card_color, render_rect, border_radius=12)
                pygame.draw.rect(surface, card_border, render_rect, width=3, border_radius=12)

                label_text = payload.get("label", card_id or key)
                lines = _wrap_text(label_text, card_width - 20)
                holder_name = info.get("holder")
                if holder_name and (mask_filter is None or info.get("zone") == "table"):
                    lines.append(f"[{holder_name}]")

                text_y = render_rect.y + 12
                for line in lines[:6]:
                    rendered = font.render(line, True, text_color)
                    surface.blit(rendered, (render_rect.x + 10, text_y))
                    text_y += rendered.get_height() + 4

                note = payload.get("note")
                if note:
                    note_lines = _wrap_text(note, card_width - 20)
                    for line in note_lines[:4]:
                        rendered = small_font.render(line, True, text_color)
                        surface.blit(rendered, (render_rect.x + 10, text_y))
                        text_y += rendered.get_height() + 2
            if hover_card_ids:
                value_data: list[tuple[str, tuple[int, int] | None]] = []
                for member_id in hover_card_ids:
                    member_payload = None
                    if hover_anchor_payload and hover_anchor_payload.get("id") == member_id:
                        member_payload = hover_anchor_payload
                    if member_payload is None:
                        member_payload = _card_payload(member_id, data)
                    label = member_payload.get("label", member_id)
                    value_range = _card_value_range(member_id, label=label)
                    value_data.append((label, value_range))

                if shift_pressed or len(value_data) <= 1:
                    for label, value_range in value_data:
                        if value_range is None:
                            tooltip_lines.append((f"{label}: –", text_color))
                            continue
                        _, high_value = value_range
                        color = value_good_color if high_value <= 21 else value_bad_color
                        tooltip_lines.append((f"{label}: {high_value}", color))
                else:
                    total = 0
                    aces = 0
                    unknown = False
                    for _, value_range in value_data:
                        if value_range is None:
                            unknown = True
                            break
                        low, high = value_range
                        total += low
                        if high > low:
                            aces += 1
                    if not unknown:
                        best_total = total
                        for _ in range(aces):
                            if best_total + 10 <= 21:
                                best_total += 10
                        color = value_good_color if best_total <= 21 else value_bad_color
                        tooltip_lines.append((f"Value: {best_total}", color))
                    else:
                        tooltip_lines.append(("Value: –", text_color))

            pygame.draw.rect(surface, face_down_color, hole_rect, border_radius=12)
            pygame.draw.rect(surface, card_border, hole_rect, width=3, border_radius=12)

            hole_title = font.render("HOLE", True, face_down_text)
            hole_count_text = font.render(str(hole_count), True, face_down_text)
            surface.blit(hole_title, (hole_rect.x + 12, hole_rect.y + 16))
            surface.blit(
                hole_count_text,
                (
                    hole_rect.x + 12,
                    hole_rect.y + 16 + hole_title.get_height() + 8,
                ),
            )

            pygame.draw.rect(surface, face_down_color, discard_rect, border_radius=12)
            pygame.draw.rect(surface, card_border, discard_rect, width=3, border_radius=12)

            title_text = font.render("Used Tome", True, face_down_text)
            count_text = font.render(str(discard_count), True, face_down_text)
            surface.blit(title_text, (discard_rect.x + 12, discard_rect.y + 16))
            surface.blit(count_text, (discard_rect.x + 12, discard_rect.y + 16 + title_text.get_height() + 8))

            deck_count = len(zones.get("deck", []))
            deck_text = small_font.render(f"Deck: {deck_count}", True, face_down_text)
            surface.blit(deck_text, (discard_rect.x + 12, discard_rect.bottom - deck_text.get_height() - 16))

            if tooltip_lines:
                tooltip_padding = 8
                text_gap = 2
                metrics = [small_font.size(text) for text, _ in tooltip_lines]
                max_width = max((w for w, _ in metrics), default=0)
                total_height = sum((h for _, h in metrics))
                tooltip_width = max_width + tooltip_padding * 2
                tooltip_height = total_height + tooltip_padding * 2
                if len(metrics) > 1:
                    tooltip_height += text_gap * (len(metrics) - 1)
                tooltip_x = mouse_pos[0] + 16
                tooltip_y = mouse_pos[1] + 16
                if tooltip_x + tooltip_width > width - padding:
                    tooltip_x = max(padding, width - tooltip_width - padding)
                if tooltip_y + tooltip_height > height - padding:
                    tooltip_y = max(padding, height - tooltip_height - padding)
                tooltip_rect = pygame.Rect(tooltip_x, tooltip_y, tooltip_width, tooltip_height)
                pygame.draw.rect(surface, card_color, tooltip_rect, border_radius=8)
                pygame.draw.rect(surface, card_border, tooltip_rect, width=1, border_radius=8)
                text_y = tooltip_rect.y + tooltip_padding
                for (text, color), (_, line_height) in zip(tooltip_lines, metrics):
                    rendered = small_font.render(text, True, color)
                    surface.blit(rendered, (tooltip_rect.x + tooltip_padding, text_y))
                    text_y += line_height + text_gap

            pygame.display.flip()
            clock.tick(30)

    finally:
        stop_event.set()
        if watcher.is_alive():
            watcher.join(timeout=1.0)
        pygame.quit()

    return {
        "tome": name,
        "displayed_cards": displayed_cards,
        "discard_count": discard_count,
        "hole_count": hole_count,
        "table_cards": len(data.get("zones", {}).get("table", [])),
        "message": "Viewer closed",
    }


def view(
    tome: str | None = None,
    *,
    mask: str | None = None,
    refresh_interval: float = 0.5,
    maximize: bool = False,
) -> dict[str, Any]:
    """Alias for :func:`open_viewer` to quickly launch the tome viewer."""

    return open_viewer(
        tome=tome,
        mask=mask,
        refresh_interval=refresh_interval,
        maximize=maximize,
    )
