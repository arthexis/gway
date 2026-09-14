from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import gway.logging as logging_module
from gway.log_http import ingest_url, publish
from gway.logging import configure, write_event


def test_ingest_url_accepts_service_root_and_api_root() -> None:
    expected = "https://logs.example/api/logs/run-1/events"
    assert ingest_url("https://logs.example", "run-1") == expected
    assert ingest_url("https://logs.example/api/logs", "run-1") == expected
    assert ingest_url("file:///tmp/logs", "run-1") is None


def test_publish_posts_ndjson_with_bearer_token(monkeypatch) -> None:
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
    monkeypatch.setenv("GWAY_LOG_TOKEN", "secret-token")
    monkeypatch.setenv("GWAY_LOG_DESTINATION", destination)
    data = b'{"run_id":"run-1","kind":"test"}\n'
    try:
        assert publish(destination, "run-1", data) is True
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert received == {
        "path": "/api/logs/run-1/events",
        "authorization": "Bearer secret-token",
        "content_type": "application/x-ndjson",
        "body": data,
    }


def test_environment_bearer_is_not_sent_to_another_destination(monkeypatch) -> None:
    monkeypatch.setenv("GWAY_LOG_TOKEN", "secret-token")
    monkeypatch.setenv("GWAY_LOG_DESTINATION", "https://logs.example")

    assert (
        publish(
            "https://other.example",
            "run-1",
            b'{"run_id":"run-1"}\n',
        )
        is False
    )


def test_publish_rejects_redirect_without_forwarding_bearer(monkeypatch) -> None:
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
                "Location", f"http://127.0.0.1:{target.server_port}/api/logs/run-1/events"
            )
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, format: str, *args: object) -> None:
            return

    source = ThreadingHTTPServer(("127.0.0.1", 0), RedirectHandler)
    source_thread = threading.Thread(target=source.serve_forever, daemon=True)
    source_thread.start()
    source_destination = f"http://127.0.0.1:{source.server_port}"
    monkeypatch.setenv("GWAY_LOG_TOKEN", "secret-token")
    monkeypatch.setenv("GWAY_LOG_DESTINATION", source_destination)
    try:
        assert (
            publish(
                source_destination,
                "run-1",
                b'{"run_id":"run-1"}\n',
            )
            is False
        )
    finally:
        source.shutdown()
        source.server_close()
        source_thread.join(timeout=2)
        target.shutdown()
        target.server_close()
        target_thread.join(timeout=2)

    assert redirected_requests == []


def test_logging_http_destination_publishes_each_event(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("GWAY_LOG_DIR", str(tmp_path))
    monkeypatch.setenv("GWAY_RUN_ID", "remote-run")
    calls: list[tuple[str, str, bytes]] = []

    def capture(destination: str, run_id: str, data: bytes) -> bool:
        calls.append((destination, run_id, data))
        return True

    monkeypatch.setattr(logging_module, "publish_http", capture)
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

    monkeypatch.setattr(logging_module, "publish_http", fail)
    configure(to=("https://logs.example",))
    write_event("test.one", "one")
    write_event("test.two", "two")

    assert len(calls) == 1
