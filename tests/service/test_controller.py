import asyncio
import json
import os
from pathlib import Path
import socket
import subprocess
import time

import pytest

from fastmcp import Client
from fastmcp.client.auth import BearerAuth

from gway import Gateway
from gway.install.service import ServiceInstallState
from gway.sampler import root as sampler_root
from gway.security.scopes import ScopeRegistry
from gway.security.tokens import TokenRegistry
from gway.service.model import Service


class FakeBackend:
    def __init__(self):
        self.calls = []

    def _result(self, action, service):
        self.calls.append((action, service.identity, service.launchable.name))
        return {
            "project": service.project,
            "service": service.name,
            "action": action,
        }

    def start(self, service):
        return self._result("start", service)

    def stop(self, service):
        return self._result("stop", service)

    def restart(self, service):
        return self._result("restart", service)

    def status(self, service):
        return self._result("status", service)


@pytest.fixture
def service_gateway():
    gateway = Gateway()
    gateway.wrap("worker", lambda: "worked")
    backend = FakeBackend()
    gateway._service_controller.backend = backend
    return gateway, backend


def test_service_list_contains_named_presets():
    gateway = Gateway()

    listed = gateway("service list")

    assert listed == [
        {
            "project": "gway",
            "service": "remote-auth",
            "description": "Gway remote OAuth and account service",
            "launchable": "operation",
            "target": "remote.serve",
        },
        {
            "project": "gway",
            "service": "sous-chef",
            "description": "Gway single-worker recipe scheduler",
            "launchable": "operation",
            "target": "sous.chef",
        },
    ]


def test_service_list_can_filter_presets_by_project():
    gateway = Gateway()
    gateway.wrap("demo worker", lambda: None)
    launchable = gateway.launchables["demo.worker"]
    preset = Service.from_launchable(
        "demo",
        "worker",
        launchable.root or ".",
        launchable,
        description="Demo worker",
    )
    gateway._service_presets[preset.identity] = preset

    assert gateway("service list --project demo") == [
        {
            "project": "demo",
            "service": "worker",
            "description": "Demo worker",
            "launchable": "operation",
            "target": "demo.worker",
        }
    ]


def test_service_inspect_materializes_policy_for_any_operation(service_gateway):
    gateway, _ = service_gateway

    inspected = gateway("service inspect worker")

    assert inspected["project"] == "gway"
    assert inspected["service"] == "worker"
    assert inspected["launchable"]["name"] == "worker"
    assert inspected["restart"] == "on-failure"
    assert inspected["attempts"] == 3


@pytest.mark.parametrize("action", ["start", "stop", "restart", "status"])
def test_service_lifecycle_commands_delegate_to_backend(service_gateway, action):
    gateway, backend = service_gateway

    result = gateway(f"service {action} worker")

    assert result == {
        "project": "gway",
        "service": "worker",
        "action": action,
    }
    assert backend.calls == [(action, ("gway", "worker"), "worker")]


def test_unknown_service_target_has_clear_resolution_error(service_gateway):
    gateway, _ = service_gateway

    with pytest.raises(LookupError):
        gateway("service start missing-operation")


@pytest.mark.parametrize("timeout", ["0", "-1", "nan", "inf", "-inf"])
def test_service_timeout_rejects_non_positive_or_non_finite_values(
    service_gateway,
    timeout,
):
    gateway, backend = service_gateway

    with pytest.raises(
        ValueError, match="service timeout must be a finite positive number"
    ):
        gateway(f"service restart --timeout {timeout} worker")

    assert backend.calls == []


@pytest.mark.parametrize(
    "timeout",
    [float("nan"), float("inf"), float("-inf")],
)
def test_timeout_normalizer_rejects_non_finite_numeric_values(
    service_gateway,
    timeout,
):
    gateway, _ = service_gateway

    with pytest.raises(
        ValueError, match="service timeout must be a finite positive number"
    ):
        gateway._service_controller._timeout(timeout)


@pytest.mark.parametrize(
    ("value", "expected"),
    [("0.5", 0.5), ("40", 40.0), (125.25, 125.25)],
)
def test_timeout_normalizer_accepts_finite_positive_values(
    service_gateway,
    value,
    expected,
):
    gateway, _ = service_gateway

    assert gateway._service_controller._timeout(value) == expected



def test_mcp_recipe_resolves_as_generic_gway_service():
    gateway = Gateway()
    recipe = sampler_root() / "mcp" / "server.rx"

    definition = gateway._service_controller._definition(
        (str(recipe),),
        name="mcp-server",
    )

    assert definition.identity == ("gway", "mcp-server")
    assert definition.launchable.kind == "recipe"
    assert definition.launchable.name == "server"
    assert definition.launchable.target == recipe.resolve()
    assert definition.launchable.command[:3] == ("{python}", "-m", "gway")
    assert definition.launchable.command[3] == str(recipe.resolve())


def test_mcp_recipe_installs_through_generic_process_backend(tmp_path, monkeypatch):
    gateway = Gateway()
    recipe = sampler_root() / "mcp" / "server.rx"
    data_root = tmp_path / "gway-data"
    monkeypatch.setenv("GWAY_DATA_DIR", str(data_root))

    records = gateway._service_controller.install(
        str(recipe),
        backend="process",
        name="mcp-server",
    )

    assert len(records) == 1
    record = records[0]
    assert record.project == "gway"
    assert record.service == "mcp-server"
    assert record.backend == "process"
    assert record.backend_id == "mcp-server"
    assert record.command[:3] == ("{python}", "-m", "gway")
    assert record.command[3] == str(recipe.resolve())

    persisted = ServiceInstallState(data_root / "services-installed").get("gway")
    assert persisted == records



def test_installed_mcp_process_service_lifecycle(tmp_path, monkeypatch):
    gateway = Gateway()
    recipe = sampler_root() / "mcp" / "server.rx"
    data_root = tmp_path / "gway-data"
    monkeypatch.setenv("GWAY_DATA_DIR", str(data_root))

    gateway._service_controller.install(
        str(recipe),
        backend="process",
        name="mcp-server",
        restart="no",
    )

    started = gateway._service_controller.start(
        str(recipe),
        name="mcp-server",
    )
    first_pid = started["pid"]

    try:
        assert started["project"] == "gway"
        assert started["service"] == "mcp-server"
        assert started["running"] is True
        assert first_pid is not None

        deadline = time.monotonic() + 5
        status = gateway._service_controller.status(
            str(recipe),
            name="mcp-server",
        )
        while time.monotonic() < deadline and not status["running"]:
            time.sleep(0.05)
            status = gateway._service_controller.status(
                str(recipe),
                name="mcp-server",
            )

        assert status["running"] is True
        assert status["pid"] == first_pid

        restarted = gateway._service_controller.restart(
            str(recipe),
            name="mcp-server",
        )
        assert restarted["running"] is True
        assert restarted["pid"] is not None
        assert restarted["pid"] != first_pid

        restarted_status = gateway._service_controller.status(
            str(recipe),
            name="mcp-server",
        )
        assert restarted_status["running"] is True
        assert restarted_status["pid"] == restarted["pid"]
    finally:
        stopped = gateway._service_controller.stop(
            str(recipe),
            name="mcp-server",
        )

    assert stopped == {
        "project": "gway",
        "service": "mcp-server",
        "running": False,
        "pid": None,
        "started_at": None,
        "stale": False,
    }



def test_deployed_mcp_service_accepts_real_http_bearer_client(tmp_path, monkeypatch):
    gateway = Gateway()
    captured_process = {}
    real_popen = subprocess.Popen

    def diagnostic_popen(*args, **kwargs):
        kwargs["stderr"] = subprocess.PIPE
        process = real_popen(*args, **kwargs)
        captured_process["process"] = process
        return process

    monkeypatch.setattr("gway.service.runtime.subprocess.Popen", diagnostic_popen)
    data_root = tmp_path / "gway-data"
    cache_root = tmp_path / "gway-cache"
    monkeypatch.setenv("GWAY_DATA_DIR", str(data_root))
    monkeypatch.setenv("GWAY_CACHE_DIR", str(cache_root))

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]

    deployment = tmp_path / "mcp-deployment"
    deployment.mkdir()
    source_root = sampler_root() / "mcp"
    recipe = deployment / "server.rx"
    recipe.write_text(
        (source_root / "server.rx")
        .read_text(encoding="utf-8")
        .replace("[mcp_port|8000]", str(port)),
        encoding="utf-8",
    )
    (deployment / "server.py").write_text(
        (source_root / "server.py").read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    scopes = ScopeRegistry()
    scopes.replace("logs-read", operations={"log.sources"}, environment=())
    issued = TokenRegistry().create("deployed-client", scopes={"logs-read"})

    gateway._service_controller.install(
        str(recipe),
        backend="process",
        name="mcp-server",
        restart="no",
    )
    started = gateway._service_controller.start(
        str(recipe),
        name="mcp-server",
    )

    async def call():
        async with Client(
            f"http://127.0.0.1:{port}/mcp",
            auth=BearerAuth(issued.bearer),
        ) as client:
            tools = [tool.name for tool in await client.list_tools()]
            result = await client.call_tool("gway", {"command": "log sources"})
            return tools, json.loads(result.content[0].text)

    try:
        assert started["running"] is True
        deadline = time.monotonic() + 30
        while True:
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                    break
            except OSError:
                if time.monotonic() >= deadline:
                    process = captured_process.get("process")
                    stderr = ""
                    if process is not None and process.poll() is not None:
                        _, stderr = process.communicate()
                    status = gateway._service_controller.status(
                        str(recipe),
                        name="mcp-server",
                    )
                    raise AssertionError(
                        "deployed MCP service did not become ready: "
                        f"{status}\n{stderr}"
                    )
                time.sleep(0.05)

        tools, sources = asyncio.run(call())
        assert tools == ["gway"]
        assert any(item["identity"] == "gway" for item in sources)
    finally:
        stopped = gateway._service_controller.stop(
            str(recipe),
            name="mcp-server",
        )

    assert stopped["running"] is False


def test_mcp_sampler_contains_no_service_manager_lifecycle_logic():
    root = sampler_root() / "mcp"
    text = "\n".join(
        path.read_text(encoding="utf-8").casefold()
        for path in sorted(root.glob("*"))
        if path.suffix in {".py", ".rx"}
    )

    forbidden = (
        "systemctl",
        "daemon-reload",
        "pidfile",
        "daemonize",
        "[service]",
        "wantedby=",
    )
    for marker in forbidden:
        assert marker not in text



def test_required_service_companion_repairs_missing_dependency(
    tmp_path,
    monkeypatch,
):
    data_root = tmp_path / "gway-data"
    cache_root = tmp_path / "gway-cache"
    bin_root = tmp_path / "bin"
    bin_root.mkdir()
    monkeypatch.setenv("GWAY_DATA_DIR", str(data_root))
    monkeypatch.setenv("GWAY_CACHE_DIR", str(cache_root))
    monkeypatch.setenv("PATH", f"{bin_root}:{os.environ['PATH']}")

    fake_uv = bin_root / "uv"
    fake_uv.write_text(
        "#!/usr/bin/env python3\n"
        "from pathlib import Path\n"
        "import subprocess\n"
        "import sys\n"
        "\n"
        "args = sys.argv[1:]\n"
        "if args[0] == 'venv':\n"
        "    subprocess.check_call([sys.executable, '-m', 'venv', args[1]])\n"
        "elif args[:2] == ['pip', 'compile']:\n"
        "    source = Path(args[args.index('--python') + 2])\n"
        "    output = Path(args[args.index('--output-file') + 1])\n"
        "    output.write_text(source.read_text(encoding='utf-8'), encoding='utf-8')\n"
        "elif args[:2] == ['pip', 'sync']:\n"
        "    python = Path(args[args.index('--python') + 1])\n"
        "    site_packages = subprocess.check_output(\n"
        "        [str(python), '-c', "
        "\"import site; print(site.getsitepackages()[0])\"],\n"
        "        text=True,\n"
        "    ).strip()\n"
        "    Path(site_packages, 'service_only_dependency.py').write_text(\n"
        "        \"VALUE = 'required'\\n\", encoding='utf-8'\n"
        "    )\n"
        "else:\n"
        "    raise SystemExit(f'unexpected fake uv invocation: {args!r}')\n",
        encoding="utf-8",
    )
    fake_uv.chmod(0o755)

    marker = tmp_path / "imports.txt"
    recipe = tmp_path / "requiredservice.rx"
    recipe.write_text(
        "require service_only_dependency\n"
        "requiredservice record\n",
        encoding="utf-8",
    )
    recipe.with_suffix(".py").write_text(
        "from pathlib import Path\n"
        "import service_only_dependency\n"
        f"_marker = Path({str(marker)!r})\n"
        "def record():\n"
        "    previous = _marker.read_text() if _marker.exists() else ''\n"
        "    _marker.write_text(previous + service_only_dependency.VALUE)\n",
        encoding="utf-8",
    )

    gateway = Gateway()
    gateway(recipe)
    assert marker.read_text(encoding="utf-8") == "required"

    gateway._service_controller.install(
        str(recipe),
        backend="process",
        name="required-service",
        restart="no",
    )

    from gway.recipe.environment import environment_python, recipe_environment

    environment = recipe_environment(gateway, recipe)
    python = environment_python(environment)
    site_packages = Path(
        subprocess.check_output(
            [str(python), "-c", "import site; print(site.getsitepackages()[0])"],
            text=True,
        ).strip()
    )
    (site_packages / "service_only_dependency.py").unlink()

    gateway._service_controller.start(str(recipe), name="required-service")
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if marker.read_text(encoding="utf-8") == "requiredrequired":
                break
            time.sleep(0.05)
        assert marker.read_text(encoding="utf-8") == "requiredrequired"
    finally:
        gateway._service_controller.stop(str(recipe), name="required-service")
