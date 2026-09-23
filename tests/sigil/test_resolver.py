import pytest

from gway.sigil import Sigil
from gway.sigil.resolver import Environment, Resolver


def test_context_lookup(gateway):
    gateway.context["site"] = "MTY"
    assert gateway.resolve("[site]") == "MTY"


def test_environment_is_a_resolver_source(gateway, monkeypatch):
    monkeypatch.setenv("GWAY_TEST_SITE", "Monterrey")
    assert gateway.resolve("[GWAY_TEST_SITE]") == "Monterrey"


def test_unresolved_sigil_raises(gateway):
    with pytest.raises(KeyError):
        gateway.resolve("[does_not_exist]")


def test_result_precedes_context_and_environment(gateway, monkeypatch):
    monkeypatch.setenv("CHARGER", "environment")
    gateway.context["charger"] = "context"
    gateway.results.insert("charger", "result")
    assert gateway.resolve("[charger]") == "result"


def test_context_precedes_environment(gateway, monkeypatch):
    monkeypatch.setenv("SITE", "environment")
    gateway.context["site"] = "context"
    assert gateway.resolve("[site]") == "context"


def test_gateway_modulo_resolves_sigil_instance(gateway):
    gateway.context["site"] = "MTY"
    assert gateway % Sigil("site") == "MTY"


def test_gateway_modulo_resolves_sigil_text(gateway):
    gateway.context["site"] = "MTY"
    assert gateway % "[site]" == "MTY"


def test_environment_normalization_belongs_to_environment_source(monkeypatch):
    monkeypatch.setenv("SITE", "environment")

    resolver = Resolver([("config", Environment())])

    assert resolver.find_value("site") == "environment"


def test_source_names_do_not_change_resolution_behavior():
    resolver = Resolver([("env", {"site": "literal"})])

    assert resolver.find_value("site") == "literal"


def test_gway_prefix_is_ordinary_semantic_data(gateway):
    gateway.context["gway"] = {"site": "MTY"}

    assert gateway.resolve("[gway site]") == "MTY"


def test_resolver_does_not_fall_back_to_its_own_attributes(gateway):
    with pytest.raises(KeyError):
        gateway.resolve("[resolve]")


def test_none_is_a_resolved_semantic_value(gateway):
    gateway.context["optional"] = None

    assert gateway.resolve("[optional]") is None
    assert gateway.resolve("[optional|fallback]") is None


def test_literal_raise_default_is_not_internal_control_value(gateway):
    assert gateway.resolve("[missing]", default="_raise") == "_raise"


@pytest.mark.parametrize(
    "requested",
    [
        "status_code",
        "status-code",
        "status code",
        "StatusCode",
        "STATUS_CODE",
    ],
)
def test_resolver_semantic_mapping_keys_ignore_case_and_separators(
    gateway,
    requested,
):
    gateway.context["Status Code"] = 200

    assert gateway.resolve(f"[{requested}]") == 200


def test_resolver_nested_mapping_path_uses_semantic_key_matching(gateway):
    gateway.context["service"] = {
        "Health Status": {
            "Status-Code": 200,
        }
    }

    assert gateway.resolve("[service health_status status_code]") == 200
    assert gateway.resolve("[service HealthStatus STATUS-CODE]") == 200


def test_resolver_rejects_ambiguous_semantic_mapping_keys(gateway):
    gateway.context.update(
        {
            "status-code": 200,
            "status_code": 500,
        }
    )

    with pytest.raises(KeyError, match="ambiguous"):
        gateway.resolve("[status code]")


def test_environment_precedes_inline_fallback(gateway, monkeypatch):
    monkeypatch.setenv("SITE", "environment")

    assert gateway.resolve("[site|fallback]") == "environment"


def test_inline_fallback_is_used_only_after_semantic_sources_are_missing(
    gateway, monkeypatch
):
    monkeypatch.delenv("SITE", raising=False)

    assert gateway.resolve("[site|fallback]") == "fallback"


def test_semantic_candidates_use_topics_then_subject(gateway):
    with gateway.topics("dns", "godaddy"):
        assert gateway.candidates("api_key") == (
            "dns.godaddy.api_key",
            "godaddy.dns.api_key",
            "godaddy.api_key",
            "dns.api_key",
            "api_key",
        )


def test_semantic_candidate_derivation_is_generic(gateway):
    with gateway.topics("database", "postgres"):
        assert gateway.candidates("password") == (
            "database.postgres.password",
            "postgres.database.password",
            "postgres.password",
            "database.password",
            "password",
        )


def test_semantic_topics_nest_and_restore(gateway):
    assert gateway.semantic_topics == ()
    with gateway.topics("dns"):
        assert gateway.semantic_topics == ("dns",)
        with gateway.topics("godaddy"):
            assert gateway.semantic_topics == ("dns", "godaddy")
        assert gateway.semantic_topics == ("dns",)
    assert gateway.semantic_topics == ()


def test_semantic_specificity_precedes_source_precedence(gateway):
    gateway.results.insert("api_key", "generic-result")
    gateway.context["dns.godaddy.api_key"] = "specific-context"

    with gateway.topics("dns", "godaddy"):
        assert gateway.resolve("[api_key]") == "specific-context"


def test_same_semantic_candidate_preserves_source_precedence(gateway):
    gateway.context["dns.godaddy.api_key"] = "context"
    gateway.results.insert("dns.godaddy.api_key", "result")

    with gateway.topics("dns", "godaddy"):
        assert gateway.resolve("[api_key]") == "result"


def test_most_local_individual_topic_precedes_broader_topic(gateway):
    gateway.context["dns.api_key"] = "dns-key"
    gateway.context["godaddy.api_key"] = "godaddy-key"

    with gateway.topics("dns", "godaddy"):
        assert gateway.resolve("[api_key]") == "godaddy-key"


def test_semantic_topic_resolution_preserves_ambiguity_detection(gateway):
    gateway.context.update(
        {
            "dns.godaddy.api-key": "one",
            "dns.godaddy.api_key": "two",
        }
    )

    with gateway.topics("dns", "godaddy"):
        with pytest.raises(KeyError, match="ambiguous"):
            gateway.resolve("[api_key]")


def test_topic_order_is_semantically_equivalent(gateway):
    gateway.context["dns.godaddy.api_key"] = "canonical"

    with gateway.topics("godaddy", "dns"):
        assert gateway.resolve("[api_key]") == "canonical"


def test_declared_topic_order_is_preferred_when_both_orders_exist(gateway):
    gateway.context["dns.godaddy.api_key"] = "declared"
    gateway.context["godaddy.dns.api_key"] = "permuted"

    with gateway.topics("dns", "godaddy"):
        assert gateway.resolve("[api_key]") == "declared"
