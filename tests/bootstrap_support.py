import subprocess


def render_arthexis_bootstrap(sampler_path, target, *, yes):
    script = sampler_path("bootstrap/arthexis.sh").read_text(encoding="utf-8")
    script = script.replace("[installer_yes|0]", "1" if yes else "0")
    script = script.replace("[installer_title]", "Satellite")
    script = script.replace("[domain]", "install.example.test")
    script = script.replace("[[", "[").replace("]]", "]")
    target.write_text(script, encoding="utf-8")
    target.chmod(0o755)


def write_executable(path, content):
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def install_fake_arthexis_runtime(home):
    runtime_bin = home / ".venv" / "bin"
    runtime_bin.mkdir(parents=True, exist_ok=True)
    for executable in ("python", "celery"):
        write_executable(runtime_bin / executable, "#!/bin/sh\nexit 0\n")


def run_checked(command, *, env):
    return subprocess.run(
        command,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
