from __future__ import annotations

import importlib
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import gway.logging as logging_module
from gway.logs.http import endpoint, publish
from gway.logging import configure, write_event
from gway.logs import PublisherBinding


def test_importing_logging_before_logs_package_is_safe() -> None:
    module = importlib.import_module("gway.logging")
    assert callable(module.current_run_id)


def _binding(destination: str, *, token: str = "secret-token") -> PublisherBinding:
    return PublisherBinding(
        provider="fixture",
        destination=destination,
        configuration={
            "transport": "http",
            "url_template": f"{destination}/ingest/{{run_id}}",
            "method": "POST",
            "headers": {
                "Authorization": "Bearer {FIXTURE_TOKEN}",
                "Content-Type": "application/x-ndjson",
            },
        },
        environment={"FIXTURE_TOKEN": token},
    )


def test_endpoint_comes_from_provider_binding() -> None:
    binding = _binding("https://logs.example")
    assert endpoint(binding, "run/1") == "https://logs.example/ingest/run%2F1"

    missing = PublisherBinding(
        provider="fixture",
        destination="https://logs.example",
        configuration={"transport": "http"},
    )
    assert endpoint(missing, "run-1") is None


def test_endpoint_rejects_remote_plain_http() -> None:
    assert endpoint(_binding("http://logs.example"), "run-1") is None
    assert endpoint(_binding("http://127.0.0.1:8040"), "run-1") == (
        "http://127.0.0.1:8040/ingest/run-1"
    )


def test_publish_uses_provider_declared_endpoint_and_headers() -> None:
    received: dict[str, object] = {}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers["Content-Length"])
            received["path"] = self.path
            received["authorization"] = self.headers.get("Authorization")
            received["content_type"] = self.headers.get("Content-Type")
            received["body"] = self.rfile.read(length)
            self.send_response(202)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, format: str, *args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    destination = f"http://127.0.0.1:{server.server_port}"
    data = b'{"run_id":"run-1","kind":"test"}\n'
    try:
        assert publish(_binding(destination), "run-1", data) is True
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert received == {
        "path": "/ingest/run-1",
        "authorization": "Bearer secret-token",
        "content_type": "application/x-ndjson",
        "body": data,
    }


def test_publish_rejects_redirect_without_forwarding_provider_headers() -> None:
    redirected_requests: list[str | None] = []

    class TargetHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            redirected_requests.append(self.headers.get("Authorization"))
            self.send_response(200)
            self.end_headers()

        def do_POST(self) -> None:  # noqa: N802
            redirected_requests.append(self.headers.get("Authorization"))
            self.send_response(200)
            self.end_headers()

        def log_message(self, format: str, *args: object) -> None:
            return

    target = ThreadingHTTPServer(("127.0.0.1", 0), TargetHandler)
    target_thread = threading.Thread(target=target.serve_forever, daemon=True)
    target_thread.start()

    class RedirectHandler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            self.send_response(302)
            self.send_header(
                "Location",
                f"http://127.0.0.1:{target.server_port}/target",
            )
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, format: str, *args: object) -> None:
            return

    source = ThreadingHTTPServer(("127.0.0.1", 0), RedirectHandler)
    source_thread = threading.Thread(target=source.serve_forever, daemon=True)
    source_thread.start()
    source_destination = f"http://127.0.0.1:{source.server_port}"
    try:
        assert publish(_binding(source_destination), "run-1", b"{}\n") is False
    finally:
        source.shutdown()
        source.server_close()
        source_thread.join(timeout=2)
        target.shutdown()
        target.server_close()
        target_thread.join(timeout=2)

    assert redirected_requests == []


def test_logging_remote_destination_publishes_each_event(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("GWAY_LOG_DIR", str(tmp_path))
    monkeypatch.setenv("GWAY_RUN_ID", "remote-run")
    calls: list[tuple[str, str, bytes]] = []

    def capture(destination: str, run_id: str, data: bytes) -> bool:
        calls.append((destination, run_id, data))
        return True

    monkeypatch.setattr(logging_module, "publish_remote", capture)
    configure(tags=("watchtower",), to=("https://logs.example",))

    assert calls
    destination, run_id, body = calls[-1]
    assert destination == "https://logs.example"
    assert run_id == "remote-run"
    event = json.loads(body)
    assert event["kind"] == "log.configure"
    assert event["tags"] == ["watchtower"]


def test_failed_remote_sink_is_disabled_for_current_run(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("GWAY_LOG_DIR", str(tmp_path))
    monkeypatch.setenv("GWAY_RUN_ID", "failed-remote-run")
    calls: list[tuple[str, str, bytes]] = []

    def fail(destination: str, run_id: str, data: bytes) -> bool:
        calls.append((destination, run_id, data))
        return False

    monkeypatch.setattr(logging_module, "publish_remote", fail)
    configure(to=("https://logs.example",))
    write_event("test.one", "one")
    write_event("test.two", "two")

    assert len(calls) == 1
