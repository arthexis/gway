from gway import Gateway
from gway.binding import bind_arguments


def test_interactive_prompts_only_for_missing_required(monkeypatch):
    runtime = Gateway(interactive=True)
    runtime.context.clear()
    runtime.results.clear()

    def create_charger(serial: str, *, limit: int = 32):
        return serial, limit

    prompts = []

    def fake_input(prompt):
        prompts.append(prompt)
        return "ABC"

    monkeypatch.setattr("builtins.input", fake_input)
    bound = bind_arguments(
        create_charger,
        [],
        runtime=runtime,
        interactive=True,
    )

    assert bound.args == ("ABC",)
    assert bound.kwargs == {}
    assert prompts == ["serial: "]



def test_verbose_interactive_shows_documented_parameter_help(monkeypatch, capsys):
    runtime = Gateway(interactive=True, verbose=True)
    runtime.context.clear()
    runtime.results.clear()

    def create_charger(serial: str, *, limit: int = 32):
        """Create one charger.

        Args:
            serial: Charger serial number used to identify the device.
        """
        return serial, limit

    prompts = []

    def fake_input(prompt):
        prompts.append(prompt)
        return "ABC"

    monkeypatch.setattr("builtins.input", fake_input)
    bound = bind_arguments(
        create_charger,
        [],
        runtime=runtime,
        interactive=True,
    )

    output = capsys.readouterr().out
    assert bound.args == ("ABC",)
    assert prompts == ["serial: "]
    assert "serial\n" in output
    assert "Charger serial number used to identify the device." in output
    assert "Type: str" in output
    assert "Required" in output


def test_verbose_interactive_falls_back_to_mechanical_parameter_help(
    monkeypatch,
    capsys,
):
    runtime = Gateway(interactive=True, verbose=True)
    runtime.context.clear()
    runtime.results.clear()

    def connect(port: int):
        return port

    monkeypatch.setattr("builtins.input", lambda prompt: "9000")
    bound = bind_arguments(
        connect,
        [],
        runtime=runtime,
        interactive=True,
    )

    output = capsys.readouterr().out
    assert bound.args == (9000,)
    assert output == "port\n  Type: int\n  Required\n"


def test_non_verbose_interactive_does_not_print_parameter_help(
    monkeypatch,
    capsys,
):
    runtime = Gateway(interactive=True, verbose=False)
    runtime.context.clear()
    runtime.results.clear()

    def connect(port: int):
        """Connect to one port.

        Args:
            port: TCP port exposed by the service.
        """
        return port

    prompts = []

    def fake_input(prompt):
        prompts.append(prompt)
        return "9000"

    monkeypatch.setattr("builtins.input", fake_input)
    bound = bind_arguments(
        connect,
        [],
        runtime=runtime,
        interactive=True,
    )

    assert bound.args == (9000,)
    assert prompts == ["port: "]
    assert capsys.readouterr().out == ""


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
