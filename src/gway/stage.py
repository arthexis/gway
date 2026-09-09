from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum


class StageSyntaxError(ValueError):
    """Raised when argv cannot be split into valid Gway stages."""


class StageKind(StrEnum):
    COMMAND = "command"
    SOLVE = "solve"


@dataclass(frozen=True, slots=True)
class Stage:
    """One lexical Gway stage before command execution."""

    tokens: tuple[str, ...]
    kind: StageKind
    explicit_solve: bool = False


def split_stage_tokens(argv: Sequence[str]) -> tuple[tuple[str, ...], ...]:
    """Split argv on standalone chain dashes while respecting ``--``.

    A standalone ``-`` is structural until a ``--`` literal boundary is seen
    in the current stage. ``[-]`` is not special here; it remains an ordinary
    token and is decoded only after stage boundaries have been identified.
    """
    stages: list[tuple[str, ...]] = []
    current: list[str] = []
    literal = False

    for token in argv:
        if token == "-" and not literal:
            if not current:
                raise StageSyntaxError("chain contains an empty stage")
            stages.append(tuple(current))
            current = []
            literal = False
            continue

        current.append(token)
        if token == "--" and not literal:
            literal = True

    if not current:
        if stages:
            raise StageSyntaxError("chain contains an empty stage")
        return ()

    stages.append(tuple(current))
    return tuple(stages)


def decode_bracket_escapes(token: str) -> str:
    """Decode Gway's lexical bracket escapes in one token."""
    left = "\x00gway-left-bracket\x00"
    right = "\x00gway-right-bracket\x00"
    return (
        token.replace("[[", left)
        .replace("]]", right)
        .replace("[-]", "-")
        .replace(left, "[")
        .replace(right, "]")
    )


def decode_stage_escapes(tokens: Sequence[str]) -> tuple[str, ...]:
    """Decode lexical escapes after a stage has already been split."""
    return tuple(decode_bracket_escapes(token) for token in tokens)


def _is_implicit_solve_start(token: str) -> bool:
    if token == "[-]" or token.startswith("[["):
        return False
    return token.startswith("[")


def classify_stage(tokens: Sequence[str]) -> Stage:
    """Classify a non-empty stage without executing or resolving it.

    ``%`` is structural only as the exact first token. A bracket-leading first
    token denotes implicit solve unless it starts with a lexical bracket escape.
    All other occurrences of ``%`` are ordinary literal tokens.
    """
    raw = tuple(tokens)
    if not raw:
        raise StageSyntaxError("cannot classify an empty stage")

    if raw[0] == "%":
        if len(raw) == 1:
            raise StageSyntaxError("solve stage requires a template")
        return Stage(
            tokens=decode_stage_escapes(raw[1:]),
            kind=StageKind.SOLVE,
            explicit_solve=True,
        )

    kind = StageKind.SOLVE if _is_implicit_solve_start(raw[0]) else StageKind.COMMAND
    return Stage(tokens=decode_stage_escapes(raw), kind=kind)


def parse_stages(argv: Sequence[str]) -> tuple[Stage, ...]:
    """Split and classify argv according to the P0 stage grammar."""
    return tuple(classify_stage(tokens) for tokens in split_stage_tokens(argv))


__all__ = [
    "Stage",
    "StageKind",
    "StageSyntaxError",
    "classify_stage",
    "decode_bracket_escapes",
    "decode_stage_escapes",
    "parse_stages",
    "split_stage_tokens",
]
