import sys

from gway.gateway import Gateway


def test_package_main_file_is_discovered_without_execution(tmp_path):
    package = tmp_path / "demo"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    marker = tmp_path / "ran.txt"
    (package / "__main__.py").write_text(
        "from pathlib import Path\n"
        "import sys\n"
        f"Path({str(marker)!r}).write_text('ran', encoding='utf-8')\n"
        "ARGS = sys.argv[1:]\n",
        encoding="utf-8",
    )

    runtime = Gateway()
    runtime.ingest_path(package)

    assert not marker.exists()

    result = runtime("demo one two")

    assert marker.read_text(encoding="utf-8") == "ran"
    assert result["ARGS"] == ["one", "two"]


def test_callable_module_main_remains_signature_aware(tmp_path):
    module = tmp_path / "demo.py"
    module.write_text(
        "def __main__(name='world'):\n"
        "    return f'hello {name}'\n",
        encoding="utf-8",
    )

    runtime = Gateway()
    runtime.ingest_path(module)

    assert runtime("demo Ada") == "hello Ada"


def test_callable_main_precedes_package_main_file(tmp_path):
    package = tmp_path / "demo"
    package.mkdir()
    marker = tmp_path / "package-main-ran.txt"
    (package / "__init__.py").write_text(
        "def __main__(name='world'):\n"
        "    return f'callable {name}'\n",
        encoding="utf-8",
    )
    (package / "__main__.py").write_text(
        "from pathlib import Path\n"
        f"Path({str(marker)!r}).write_text('ran', encoding='utf-8')\n",
        encoding="utf-8",
    )

    runtime = Gateway()
    runtime.ingest_path(package)

    assert runtime("demo Ada") == "callable Ada"
    assert not marker.exists()


def test_package_main_restores_sys_argv(tmp_path):
    package = tmp_path / "demo"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "__main__.py").write_text(
        "import sys\n"
        "ARGS = list(sys.argv)\n",
        encoding="utf-8",
    )

    runtime = Gateway()
    runtime.ingest_path(package)
    original = sys.argv

    result = runtime("demo alpha")

    assert result["ARGS"][1:] == ["alpha"]
    assert sys.argv is original
