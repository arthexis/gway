from gway import Sigil as PublicSigil
from gway.sigil import Sigil


def test_constructor_implies_outer_brackets():
    assert str(Sigil("charger")) == "[charger]"


def test_constructor_preserves_existing_outer_brackets():
    assert str(Sigil("[charger]")) == "[charger]"


def test_constructor_treats_inner_brackets_as_nested_sigils():
    assert str(Sigil("chargers [index]")) == "[chargers [index]]"


def test_sigil_is_context_free_until_resolution():
    sigil = Sigil("site")
    assert sigil.text == "site"
    assert not hasattr(sigil, "context")


def test_modulo_resolves_sigil_against_mapping():
    assert Sigil("site") % {"site": "MTY"} == "MTY"


def test_reverse_modulo_resolves_context_against_sigil():
    assert {"site": "MTY"} % Sigil("site") == "MTY"


def test_sigil_is_exported_from_top_level_package():
    assert PublicSigil is Sigil


def test_sigil_modulo_uses_gateway_engine(gateway):
    gateway.context["site"] = "MTY"
    gateway.wrap("decorate", lambda value: f"<{value}>")

    assert Sigil("decorate [site]") % gateway == "<MTY>"
