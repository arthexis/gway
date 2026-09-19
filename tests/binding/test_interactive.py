from gway import Gateway
from gway.binding import bind_arguments


def _bind_interactively(
    func,
    monkeypatch,
    capsys,
    *,
    response,
    verbose=False,
):
    runtime = Gateway(interactive=True, verbose=verbose)
    runtime.context.clear()
    runtime.results.clear()
    prompts = []

    def fake_input(prompt):
        prompts.append(prompt)
        return response

    monkeypatch.setattr("builtins.input", fake_input)
    bound = bind_arguments(
        func,
        [],
        runtime=runtime,
        interactive=True,
    )
    output = capsys.readouterr().out
    return bound, prompts, output


def test_interactive_prompts_only_for_missing_required(monkeypatch, capsys):
    def create_charger(serial: str, *, limit: int = 32):
        return serial, limit

    bound, prompts, output = _bind_interactively(
        create_charger,
        monkeypatch,
        capsys,
        response="ABC",
    )

    assert bound.args == ("ABC",)
    assert bound.kwargs == {}
    assert prompts == ["serial: "]
    assert output == ""


def test_verbose_interactive_shows_documented_parameter_help(monkeypatch, capsys):
    def create_charger(serial: str, *, limit: int = 32):
        """Create one charger.

        Args:
            serial: Charger serial number used to identify the device.
        """
        return serial, limit

    bound, prompts, output = _bind_interactively(
        create_charger,
        monkeypatch,
        capsys,
        response="ABC",
        verbose=True,
    )

    assert bound.args == ("ABC",)
    assert prompts == ["serial: "]
    assert "Charger serial number used to identify the device." in output
    assert "Type: str" in output
    assert "Required" in output


def test_verbose_interactive_falls_back_to_mechanical_parameter_help(
    monkeypatch,
    capsys,
):
    def connect(port: int):
        return port

    bound, _, output = _bind_interactively(
        connect,
        monkeypatch,
        capsys,
        response="9000",
        verbose=True,
    )

    assert bound.args == (9000,)
    assert output == "port\n  Type: int\n  Required\n"


def test_non_verbose_interactive_does_not_print_parameter_help(
    monkeypatch,
    capsys,
):
    def connect(port: int):
        """Connect to one port.

        Args:
            port: TCP port exposed by the service.
        """
        return port

    bound, prompts, output = _bind_interactively(
        connect,
        monkeypatch,
        capsys,
        response="9000",
    )

    assert bound.args == (9000,)
    assert prompts == ["port: "]
    assert output == ""


def test_verbose_interactive_uses_bound_gway_operation_documentation(
    gateway,
    monkeypatch,
    capsys,
):
    gateway.verbose = True
    gateway.interactive_enabled = True

    def inspect_target(target: str):
        """Inspect one target.

        Args:
            target: Resource identity to inspect.
        """
        return target

    bound_operation = gateway.wrap("inspect_target", inspect_target)
    monkeypatch.setattr("builtins.input", lambda prompt: "alpha")

    bound = bind_arguments(
        bound_operation,
        [],
        runtime=gateway,
        interactive=True,
    )

    output = capsys.readouterr().out
    assert bound.args == ("alpha",)
    assert "Resource identity to inspect." in output
    assert "Type: str" in output
