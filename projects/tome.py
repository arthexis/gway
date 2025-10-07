"""Persistent deck management helpers ("tomes")."""

from __future__ import annotations

import json
import os
import random
import time
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
    zones.setdefault("table", [])
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
            "table": [],
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
        if table:
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
) -> dict[str, Any]:
    """Open a resizable pygame window visualizing the tome state.

    The viewer shows the discard pile ("used tome") as a face-down stack with a
    card count in the lower-right corner while rendering the drawn cards face up
    on the table. When ``mask`` is provided, only that mask's hand is displayed;
    otherwise all hands are shown. The display automatically reloads the tome
    file when it changes on disk so it can be left open while other commands
    manipulate the tome.
    """

    name, data, path = _load_tome_data(tome)

    import pygame

    pygame.init()
    try:
        pygame.display.set_mode((960, 720), pygame.RESIZABLE)
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

    card_positions: dict[str, pygame.Rect] = {}
    draw_order: list[str] = []
    dragging_card: str | None = None
    drag_offset = (0, 0)
    card_info: dict[str, dict[str, Any]] = {}
    table_line_y = 0

    mask_filter = _default_mask(mask) if mask is not None else None
    last_mtime = path.stat().st_mtime if path.exists() else None
    refresh_interval = max(0.1, float(refresh_interval))
    next_refresh = time.monotonic()

    table_color = (16, 99, 45)
    card_color = (245, 245, 245)
    card_border = (30, 30, 30)
    face_down_color = (80, 55, 33)
    text_color = (10, 10, 10)
    face_down_text = (230, 230, 230)
    guide_color = (220, 220, 220)

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

    running = True
    displayed_cards = 0
    discard_count = len(data.get("zones", {}).get("discard", []))

    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN and event.key in (pygame.K_ESCAPE, pygame.K_q):
                running = False
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                mouse_pos = event.pos
                for key in reversed(draw_order):
                    rect = card_positions.get(key)
                    if rect and rect.collidepoint(mouse_pos):
                        dragging_card = key
                        drag_offset = (mouse_pos[0] - rect.x, mouse_pos[1] - rect.y)
                        draw_order.remove(key)
                        draw_order.append(key)
                        break
            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                if dragging_card:
                    rect = card_positions.get(dragging_card)
                    info = card_info.get(dragging_card)
                    if rect and info:
                        if rect.bottom < table_line_y and info.get("zone") != "table":
                            moved = _move_hand_cards_to_table(data, info["holder"], [info["card_id"]])
                            if moved:
                                new_key = f"table::{info['card_id']}"
                                card_positions[new_key] = pygame.Rect(
                                    rect.x,
                                    rect.y,
                                    card_width,
                                    card_height,
                                )
                                card_positions.pop(dragging_card, None)
                                if dragging_card in draw_order:
                                    draw_order.remove(dragging_card)
                                if new_key not in draw_order:
                                    draw_order.append(new_key)
                                _save_tome(path, data)
                                try:
                                    last_mtime = path.stat().st_mtime
                                except OSError:
                                    last_mtime = None
                        elif rect.bottom >= table_line_y and info.get("zone") != "hand":
                            target_holder = info.get("holder")
                            if not target_holder and mask_filter:
                                target_holder = mask_filter
                            if not target_holder:
                                target_holder = _default_mask(None)
                            moved = _move_table_cards_to_hand(data, target_holder, [info["card_id"]])
                            if moved:
                                new_key = f"hand:{target_holder}:{info['card_id']}"
                                card_positions[new_key] = pygame.Rect(
                                    rect.x,
                                    rect.y,
                                    card_width,
                                    card_height,
                                )
                                card_positions.pop(dragging_card, None)
                                if dragging_card in draw_order:
                                    draw_order.remove(dragging_card)
                                if new_key not in draw_order:
                                    draw_order.append(new_key)
                                _save_tome(path, data)
                                try:
                                    last_mtime = path.stat().st_mtime
                                except OSError:
                                    last_mtime = None
                    dragging_card = None
            elif event.type == pygame.MOUSEMOTION and dragging_card:
                rect = card_positions.get(dragging_card)
                if rect is not None and event.buttons[0]:
                    rect.x = event.pos[0] - drag_offset[0]
                    rect.y = event.pos[1] - drag_offset[1]
                elif not event.buttons[0]:
                    dragging_card = None

        now = time.monotonic()
        if now >= next_refresh:
            next_refresh = now + refresh_interval
            if path.exists():
                try:
                    mtime = path.stat().st_mtime
                except OSError:
                    mtime = None
                if mtime and (last_mtime is None or mtime > last_mtime):
                    try:
                        loaded = json.loads(path.read_text(encoding="utf-8"))
                    except (OSError, json.JSONDecodeError):
                        pass
                    else:
                        data = _ensure_schema(loaded)
                        name = data.get("name", name)
                        last_mtime = mtime
                        discard_count = len(data.get("zones", {}).get("discard", []))

        surface = pygame.display.get_surface()
        if surface is None:
            break
        width, height = surface.get_size()
        surface.fill(table_color)

        columns = max(1, (width - padding) // (card_width + padding))

        discard_rect = pygame.Rect(
            width - card_width - padding,
            height - card_height - padding,
            card_width,
            card_height,
        )
        table_line_y = max(0, discard_rect.y - 16)
        table_area_bottom = table_line_y - hand_gap
        max_table_y = max(padding, table_area_bottom - card_height)

        zones = data.get("zones", {})
        table_cards: list[str] = zones.get("table", [])
        hands: dict[str, list[str]] = zones.get("hands", {})

        updated_info: dict[str, dict[str, Any]] = {}

        for index, card_id in enumerate(table_cards):
            key = f"table::{card_id}"
            rect = card_positions.get(key)
            if rect is None:
                col = index % columns
                row = index // columns
                x = padding + col * (card_width + padding)
                y = padding + row * (card_height + padding)
                if y + card_height > table_area_bottom:
                    y = max_table_y
                rect = pygame.Rect(x, y, card_width, card_height)
                card_positions[key] = rect
            else:
                rect.width = card_width
                rect.height = card_height

            payload = _card_payload(card_id, data)
            updated_info[key] = {
                "zone": "table",
                "holder": payload.get("holder"),
                "card_id": card_id,
                "payload": payload,
            }

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
                if rect is None:
                    rect = pygame.Rect(x, row_y, card_width, card_height)
                    card_positions[key] = rect
                elif dragging_card != key:
                    rect.x = x
                    rect.y = row_y
                    rect.width = card_width
                    rect.height = card_height
                else:
                    rect.width = card_width
                    rect.height = card_height

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

            pygame.draw.rect(surface, card_color, rect, border_radius=12)
            pygame.draw.rect(surface, card_border, rect, width=3, border_radius=12)

            payload = info["payload"]
            lines = _wrap_text(payload.get("label", info["card_id"]), card_width - 20)
            holder_name = info.get("holder")
            if holder_name and (mask_filter is None or info.get("zone") == "table"):
                lines.append(f"[{holder_name}]")

            text_y = rect.y + 12
            for line in lines[:6]:
                rendered = font.render(line, True, text_color)
                surface.blit(rendered, (rect.x + 10, text_y))
                text_y += rendered.get_height() + 4

            note = payload.get("note")
            if note:
                note_lines = _wrap_text(note, card_width - 20)
                for line in note_lines[:4]:
                    rendered = small_font.render(line, True, text_color)
                    surface.blit(rendered, (rect.x + 10, text_y))
                    text_y += rendered.get_height() + 2
        pygame.draw.rect(surface, face_down_color, discard_rect, border_radius=12)
        pygame.draw.rect(surface, card_border, discard_rect, width=3, border_radius=12)

        title_text = font.render("Used Tome", True, face_down_text)
        count_text = font.render(str(discard_count), True, face_down_text)
        surface.blit(title_text, (discard_rect.x + 12, discard_rect.y + 16))
        surface.blit(count_text, (discard_rect.x + 12, discard_rect.y + 16 + title_text.get_height() + 8))

        deck_count = len(zones.get("deck", []))
        deck_text = small_font.render(f"Deck: {deck_count}", True, face_down_text)
        surface.blit(deck_text, (discard_rect.x + 12, discard_rect.bottom - deck_text.get_height() - 16))

        pygame.display.flip()
        clock.tick(30)

    pygame.quit()

    return {
        "tome": name,
        "displayed_cards": displayed_cards,
        "discard_count": discard_count,
        "table_cards": len(data.get("zones", {}).get("table", [])),
        "message": "Viewer closed",
    }
