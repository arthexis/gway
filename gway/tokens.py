"""Lexical tokenization for GWAY commands and recipes."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Token:
    """A lexical token with optional quote provenance."""

    value: str
    quote: str | None = None

    @property
    def literal(self) -> bool:
        return self.quote == "single"

    def __str__(self) -> str:
        return self.value


def token_value(token) -> str:
    """Return the textual value for either a Token or a plain CLI string."""
    return token.value if isinstance(token, Token) else str(token)


def is_literal(token) -> bool:
    """Return whether a token is protected by single-quote literal semantics."""
    return isinstance(token, Token) and token.literal


def is_unquoted(token) -> bool:
    """Return whether a token has no quote provenance and may be structural."""
    return not isinstance(token, Token) or token.quote is None


def tokenize(text: str) -> list[Token]:
    """Split recipe text while preserving single/double quote provenance."""
    tokens: list[Token] = []
    current: list[str] = []
    quote: str | None = None
    token_quote: str | None = None
    escaped = False
    started = False

    def emit() -> None:
        nonlocal current, token_quote, started
        if started:
            tokens.append(Token("".join(current), token_quote))
        current = []
        token_quote = None
        started = False

    for char in text:
        if escaped:
            current.append(char)
            started = True
            escaped = False
            continue

        if quote == "double" and char == "\\":
            escaped = True
            started = True
            continue

        if quote is None:
            if char.isspace():
                emit()
                continue
            if char == "'":
                if not started:
                    token_quote = "single"
                elif token_quote != "single":
                    token_quote = None
                quote = "single"
                started = True
                continue
            if char == '"':
                if not started:
                    token_quote = "double"
                elif token_quote != "double":
                    token_quote = None
                quote = "double"
                started = True
                continue
            current.append(char)
            started = True
            continue

        if quote == "single":
            if char == "'":
                quote = None
            else:
                current.append(char)
            continue

        if quote == "double":
            if char == '"':
                quote = None
            else:
                current.append(char)

    if escaped:
        current.append("\\")
    if quote is not None:
        raise ValueError(f"Unterminated {quote}-quoted string")
    emit()
    return tokens


def statements(tokens):
    """Split tokens on standalone unquoted statement separators."""
    chunks = []
    current = []

    for token in tokens:
        value = token_value(token)
        if is_unquoted(token) and value == ";":
            if current:
                chunks.append(current)
                current = []
        else:
            current.append(token)

    if current:
        chunks.append(current)
    return chunks


def chunk(tokens):
    """Split tokens on standalone unquoted positional pipeline separators."""
    chunks = []
    current = []

    for token in tokens:
        value = token_value(token)
        if is_unquoted(token) and value == "-":
            if current:
                chunks.append(current)
                current = []
        else:
            current.append(token)

    if current:
        chunks.append(current)
    return chunks
