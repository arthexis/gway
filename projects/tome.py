"""Persistent deck management helpers ("tomes")."""

from __future__ import annotations

import json
import os
import random
from dataclasses import dataclass
from pathlib import Path
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
    return slug or "tome"


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
    zones.setdefault("hands", {})
    state = data.setdefault("card_state", {})
    for card_id in cards:
        state.setdefault(card_id, {"zone": "deck"})
    return data


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
            "hands": {},
        },
        "card_state": state,
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
    return payload


def shuffle(tome: str | None = None, *, all: bool = False, mask: str | None = None) -> dict[str, Any]:
    """Shuffle the selected tome, optionally recalling all cards before shuffling."""
    name, data, path = _load_tome_data(tome)
    zones = data.setdefault("zones", {})
    deck: list[str] = zones.setdefault("deck", [])
    hands: dict[str, list[str]] = zones.setdefault("hands", {})
    discard: list[str] = zones.setdefault("discard", [])
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
