import os
from pathlib import Path

import pytest

from gway.appserver import ApplicationHTTPAdapter
from gway.appspec import AppSpec, ViewSpec


def test_static_file_view_serves_bytes_and_infers_content_type(gateway, tmp_path):
    source = tmp_path / "robots.txt"
    source.write_text("User-agent: *\n", encoding="utf-8")
    app = AppSpec().add(
        ViewSpec(route="/robots.txt", static=str(source))
    )
    application = ApplicationHTTPAdapter(gateway, app)

    assert application.response("GET", "/robots.txt") == (
        200,
        {"content-type": "text/plain"},
        b"User-agent: *\n",
    )
    assert application.response("HEAD", "/robots.txt") == (
        200,
        {"content-type": "text/plain"},
        b"User-agent: *\n",
    )


def test_static_content_type_override(gateway, tmp_path):
    source = tmp_path / "manifest.json"
    source.write_text("{}", encoding="utf-8")
    app = AppSpec().add(
        ViewSpec(
            route="/manifest",
            static=str(source),
            content_type="application/manifest+json",
        )
    )

    assert ApplicationHTTPAdapter(gateway, app).response("GET", "/manifest") == (
        200,
        {"content-type": "application/manifest+json"},
        b"{}",
    )


def test_static_directory_mount_serves_nested_files(gateway, tmp_path):
    root = tmp_path / "static"
    nested = root / "css"
    nested.mkdir(parents=True)
    (nested / "app.css").write_text("body{}", encoding="utf-8")
    app = AppSpec().add(
        ViewSpec(
            route="/assets",
            static=str(root),
            directory=True,
        )
    )

    status, headers, payload = ApplicationHTTPAdapter(gateway, app).response(
        "GET",
        "/assets/css/app.css",
    )

    assert status == 200
    assert headers["content-type"] == "text/css"
    assert payload == b"body{}"


def test_static_directory_missing_file_returns_404(gateway, tmp_path):
    root = tmp_path / "static"
    root.mkdir()
    app = AppSpec().add(
        ViewSpec(route="/assets", static=str(root), directory=True)
    )

    assert ApplicationHTTPAdapter(gateway, app).response(
        "GET",
        "/assets/missing.js",
    ) == (404, {}, {"error": "not_found"})


@pytest.mark.parametrize(
    "path",
    (
        "/assets/../secret.txt",
        "/assets/%2e%2e/secret.txt",
        "/assets/%2E%2E/secret.txt",
    ),
)
def test_static_directory_rejects_traversal(gateway, tmp_path, path):
    root = tmp_path / "static"
    root.mkdir()
    (tmp_path / "secret.txt").write_text("secret", encoding="utf-8")
    app = AppSpec().add(
        ViewSpec(route="/assets", static=str(root), directory=True)
    )

    assert ApplicationHTTPAdapter(gateway, app).response("GET", path) == (
        404,
        {},
        {"error": "not_found"},
    )


def test_static_directory_rejects_symlink_escape(gateway, tmp_path):
    if not hasattr(os, "symlink"):
        pytest.skip("symlinks unavailable")
    root = tmp_path / "static"
    root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    link = root / "escape.txt"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("symlink creation unavailable")

    app = AppSpec().add(
        ViewSpec(route="/assets", static=str(root), directory=True)
    )

    assert ApplicationHTTPAdapter(gateway, app).response(
        "GET",
        "/assets/escape.txt",
    ) == (404, {}, {"error": "not_found"})


def test_explicit_handler_route_wins_over_static_directory_prefix(gateway, tmp_path):
    root = tmp_path / "static"
    root.mkdir()
    (root / "health").write_text("static", encoding="utf-8")
    gateway.wrap("site.health", lambda: {"status": "ok"})

    app = AppSpec(
        views=(
            ViewSpec(route="/assets", static=str(root), directory=True),
            ViewSpec("site.health", route="/assets/health"),
        )
    )

    assert ApplicationHTTPAdapter(gateway, app).response(
        "GET",
        "/assets/health",
    ) == (200, {}, {"status": "ok"})


def test_static_view_rejects_non_read_methods():
    with pytest.raises(ValueError, match="only GET and HEAD"):
        ViewSpec(
            route="/assets",
            static="/tmp/assets",
            methods=("POST",),
        )


def test_static_and_handler_views_conflict_on_same_route(gateway, tmp_path):
    source = tmp_path / "health.txt"
    source.write_text("ok", encoding="utf-8")

    with pytest.raises(ValueError, match="Conflicting view"):
        AppSpec(
            views=(
                ViewSpec(route="/health", static=str(source)),
                ViewSpec("site.health", route="/health"),
            )
        )


def test_static_source_is_captured_relative_to_recipe(gateway, tmp_path):
    recipe_dir = tmp_path / "recipe"
    recipe_dir.mkdir()
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    source = static_dir / "robots.txt"
    source.write_text("robots", encoding="utf-8")
    recipe = recipe_dir / "site.rx"
    recipe.write_text(
        "setup app site\n"
        "view --route /robots.txt --static ../static/robots.txt\n",
        encoding="utf-8",
    )

    app = gateway(recipe)

    assert Path(app.views[0].static) == source.resolve()
    assert ApplicationHTTPAdapter(gateway, app).response(
        "GET",
        "/robots.txt",
    ) == (200, {"content-type": "text/plain"}, b"robots")
