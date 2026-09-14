from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import gway.logging as logging_module
from gway.log_http import ingest_url, publish
from gway.logging import configure


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
    monkeypatch.setenv("GWAY_LOG_TOKEN", "secret-token")
    data = b'{"run_id":"run-1","kind":"test"}\n'
    try:
        assert publish(f"http://127.0.0.1:{server.server_port}", "run-1", data) is True
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
