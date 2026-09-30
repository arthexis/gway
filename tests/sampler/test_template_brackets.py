"""Contract tests for templates published through Gway render recipes."""

import re

from gway.sampler import root as sampler_root


_RENDER_SOURCE = re.compile(r"^\s*render\s+(\S+)", re.MULTILINE)
_ESCAPED_LITERAL = re.compile(r"\[\[[^\[\]\n]*\]\]")
_GWAY_SIGIL = re.compile(
    r"\[(?:"
    r"[a-z_][a-z0-9_]*(?:[. ][a-z0-9_]+)*"
    r"|[\"'][^\[\]\n]+[\"']"
    r")(?:\|[^\[\]\n]*)?\]"
)


def _published_render_templates(sampler_root):
    seen = set()
    for recipe in sampler_root.rglob("*.rx"):
        source = recipe.read_text(encoding="utf-8")
        for match in _RENDER_SOURCE.finditer(source):
            name = match.group(1)
            if "[" in name and not (recipe.parent / name).is_file():
                # Dynamic template-source names cannot be resolved statically.
                continue
            path = recipe.parent / name
            if path.is_file() and path not in seen:
                seen.add(path)
                yield path


def _unescaped_bracket_lines(content):
    protected = _ESCAPED_LITERAL.sub("", content)
    protected = _GWAY_SIGIL.sub("", protected)
    return [
        (number, line)
        for number, line in enumerate(protected.splitlines(), start=1)
        if "[" in line or "]" in line
    ]


def test_published_render_templates_escape_literal_square_brackets():
    """Literal engine brackets must use [[...]] so Gway can render safely."""
    root = sampler_root()
    failures = {}
    for path in _published_render_templates(root):
        lines = _unescaped_bracket_lines(path.read_text(encoding="utf-8"))
        if lines:
            failures[str(path.relative_to(root))] = lines

    assert not failures, (
        "published templates contain single-bracket engine syntax; "
        "use [[...]] for literal square brackets and reserve [...] "
        f"for Gway sigils: {failures}"
    )
