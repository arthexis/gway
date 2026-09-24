from types import SimpleNamespace

from gway.console import _extract_mutation_policy, _run_cli
from gway.mutation import MUTATE_UNSET


def _args(*, mutation_policy=MUTATE_UNSET):
    return SimpleNamespace(
        resume=None,
        recipe=None,
        expression=None,
        silent=True,
        json=False,
        mutation_policy=mutation_policy,
    )


def test_mutation_cli_flags_do_not_consume_command_tokens():
    policy, remaining = _extract_mutation_policy(["--mutate", "inspect", "status"])

    assert policy is True
    assert remaining == ["inspect", "status"]


def test_named_mutation_cli_policy_uses_equals_form():
    policy, remaining = _extract_mutation_policy(
        ["--mutate=refresh", "inspect", "status"]
    )

    assert policy == "refresh"
    assert remaining == ["inspect", "status"]


def test_no_mutate_is_monotonic_with_later_cli_policy():
    policy, remaining = _extract_mutation_policy(
        ["-M", "--mutate=refresh", "inspect"]
    )

    assert policy is False
    assert remaining == ["inspect"]


def test_cli_no_mutate_reaches_compatible_callable(gateway):
    seen = []

    def inspect(*, mutate=True):
        seen.append(mutate)
        return "ok"

    gateway.inspect = gateway.wrap("inspect_state", inspect)

    assert _run_cli(None, _args(mutation_policy=False), ["inspect"], runtime=gateway) == 0
    assert seen == [False]


def test_cli_named_mutation_policy_reaches_compatible_callable(gateway):
    seen = []

    def inspect(*, mutate=False):
        seen.append(mutate)
        return "ok"

    gateway.inspect = gateway.wrap("inspect_state", inspect)

    assert (
        _run_cli(
            None,
            _args(mutation_policy="refresh"),
            ["inspect"],
            runtime=gateway,
        )
        == 0
    )
    assert seen == ["refresh"]
