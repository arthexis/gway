from __future__ import annotations

from gway.transfer import render_transfer

from .django import DjangoAdapter


class TransferDjangoAdapter(DjangoAdapter):
    """Django adapter variant that restores opaque chain values before Django parses argv."""

    def run(self, path: tuple[str, ...], argv: list[str]) -> object:
        restored = [render_transfer(value) for value in argv]
        return super().run(path, restored)


__all__ = ["TransferDjangoAdapter"]
