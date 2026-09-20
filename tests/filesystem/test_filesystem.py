import pytest


def test_copy_resolves_sigils(gateway, tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("hello", encoding="utf-8")
    gateway.context["target"] = "copied.txt"

    result = gateway(
        [
            "copy",
            str(source),
            "--to",
            str(tmp_path / "[target]"),
        ]
    )

    expected = tmp_path / "copied.txt"
    assert result == expected
    assert expected.read_text(encoding="utf-8") == "hello"


def test_copy_to_directory_uses_source_name(gateway, tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("hello", encoding="utf-8")
    destination = tmp_path / "destination"
    destination.mkdir()

    result = gateway(["copy", str(source), "--to", str(destination)])

    expected = destination / source.name
    assert result == expected
    assert expected.read_text(encoding="utf-8") == "hello"


def test_copy_directory_recursively(gateway, tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "nested.txt").write_text("hello", encoding="utf-8")
    destination = tmp_path / "copy"

    result = gateway(["copy", str(source), "--to", str(destination)])

    assert result == destination
    assert (destination / "nested.txt").read_text(encoding="utf-8") == "hello"


def test_move_resolves_paths(gateway, tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("hello", encoding="utf-8")
    gateway.context["target"] = "moved.txt"

    result = gateway(
        [
            "move",
            str(source),
            "--to",
            str(tmp_path / "[target]"),
        ]
    )

    expected = tmp_path / "moved.txt"
    assert result == expected
    assert not source.exists()
    assert expected.read_text(encoding="utf-8") == "hello"


def test_link_resolves_sigils(gateway, tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("hello", encoding="utf-8")
    gateway.context["name"] = "enabled"

    result = gateway(
        [
            "link",
            str(source),
            "--to",
            str(tmp_path / "[name].conf"),
        ]
    )

    expected = tmp_path / "enabled.conf"
    assert result == expected
    assert expected.is_symlink()
    assert expected.resolve() == source.resolve()


def test_remove_deletes_file(gateway, tmp_path):
    target = tmp_path / "remove-me.txt"
    target.write_text("bye", encoding="utf-8")

    result = gateway(["remove", str(target)])

    assert result == target
    assert not target.exists()


def test_remove_deletes_symlink_without_target(gateway, tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("keep", encoding="utf-8")
    link = tmp_path / "link.txt"
    link.symlink_to(source)

    result = gateway(["remove", str(link)])

    assert result == link
    assert not link.exists()
    assert source.read_text(encoding="utf-8") == "keep"


def test_remove_only_removes_empty_directory(gateway, tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    result = gateway(["remove", str(empty)])
    assert result == empty
    assert not empty.exists()

    populated = tmp_path / "populated"
    populated.mkdir()
    (populated / "file.txt").write_text("keep", encoding="utf-8")

    with pytest.raises(OSError):
        gateway(["remove", str(populated)])

    assert populated.exists()


@pytest.mark.parametrize(
    ("operation", "command"),
    [
        ("copy", ("cp", "-a")),
        ("move", ("mv",)),
        ("link", ("ln", "-s")),
    ],
)
def test_privileged_transfer_operations_use_execution_identity(
    gateway,
    tmp_path,
    host_calls,
    operation,
    command,
):
    source = tmp_path / "source.txt"
    source.write_text("hello", encoding="utf-8")
    destination = tmp_path / f"{operation}.txt"
    result = gateway(
        [
            operation,
            str(source),
            "--to",
            str(destination),
            "--as",
            "www-data",
        ]
    )

    assert result == destination
    expected = [
        (
            ("sudo", "-u", "www-data", *command, str(source), str(destination)),
            {"check": True},
        )
    ]
    if operation == "link":
        expected.insert(
            0,
            (
                ("sudo", "-u", "www-data", "test", "-e", str(source)),
                {"check": True},
            ),
        )
    assert host_calls == expected


def test_privileged_remove_uses_execution_identity(
    gateway,
    tmp_path,
    host_calls,
):
    target = tmp_path / "remove-me.txt"
    target.write_text("hello", encoding="utf-8")
    result = gateway(["remove", str(target), "--sudo"])

    assert result == target
    assert host_calls == [
        (
            ("sudo", "rm", "-f", str(target)),
            {"check": True},
        )
    ]


def test_filesystem_rejects_conflicting_execution_identity(gateway, tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("hello", encoding="utf-8")
    destination = tmp_path / "destination.txt"

    with pytest.raises(ValueError, match="conflicts with --as"):
        gateway(
            [
                "copy",
                str(source),
                "--to",
                str(destination),
                "--sudo",
                "--as",
                "www-data",
            ]
        )


def test_link_is_idempotent_when_existing_symlink_matches(gateway, tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("hello", encoding="utf-8")
    destination = tmp_path / "linked.txt"
    destination.symlink_to(source)

    result = gateway(["link", str(source), "--to", str(destination)])

    assert result == destination
    assert destination.resolve() == source.resolve()


def test_privileged_link_skips_existing_matching_symlink(
    gateway,
    tmp_path,
    host_calls,
):
    source = tmp_path / "source.txt"
    source.write_text("hello", encoding="utf-8")
    destination = tmp_path / "linked.txt"
    destination.symlink_to(source)

    result = gateway(["link", str(source), "--to", str(destination), "--as", "root"])

    assert result == destination
    assert host_calls == [(("sudo", "test", "-e", str(source)), {"check": True})]


def test_link_rejects_missing_source(gateway, tmp_path):
    source = tmp_path / "missing.txt"
    destination = tmp_path / "linked.txt"

    with pytest.raises(FileNotFoundError):
        gateway(["link", str(source), "--to", str(destination)])

    assert not destination.is_symlink()


def test_privileged_link_checks_source_before_creating(
    gateway,
    tmp_path,
    host_calls,
):
    source = tmp_path / "source.txt"
    source.write_text("hello", encoding="utf-8")
    destination = tmp_path / "linked.txt"

    gateway(["link", str(source), "--to", str(destination), "--as", "root"])

    assert host_calls[0] == (
        ("sudo", "test", "-e", str(source)),
        {"check": True},
    )
    assert host_calls[1] == (
        ("sudo", "ln", "-s", str(source), str(destination)),
        {"check": True},
    )
