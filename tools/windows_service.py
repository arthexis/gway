"""Utility to run gway recipes as a Windows service.

Usage examples::

    python windows_service.py install --name gway-test --recipe demo
    python windows_service.py remove --name gway-test [--force]
    python windows_service.py start --name gway-test
    python windows_service.py stop  --name gway-test
    python windows_service.py run   --name gway-test --recipe demo

The ``install`` command registers a Windows service that runs::

    %PYTHON% windows_service.py run --name <name> --recipe <recipe>

on startup. ``remove`` stops (optionally force-kills) and deletes the
service.
"""

import os
import sys
import argparse
import re
import subprocess


def _create_service_class(name: str, display_name: str, recipe: str | None, debug: bool) -> type:
    """Return a module-level service class unique to ``name``."""
    cls_name = "Service_" + re.sub(r"[^a-zA-Z0-9_]", "_", name)

    class Service(GatewayService):
        pass

    Service.__name__ = cls_name
    Service._svc_name_ = name
    Service._svc_display_name_ = display_name
    Service.recipe = recipe
    Service.debug = debug
    globals()[cls_name] = Service
    return Service


def _format_display_name(name: str) -> str:
    """Return a human friendly Windows service display name."""
    parts = re.split(r"[-_]+", name)
    return " ".join("GWAY" if p.lower() == "gway" else p.capitalize() for p in parts)

try:
    import win32serviceutil
    import win32service
    import win32event
except Exception:  # pragma: no cover - not on Windows
    win32serviceutil = None  # type: ignore


class GatewayService(win32serviceutil.ServiceFramework if win32serviceutil else object):
    """Service subclass launching ``gway.bat -r <recipe>``."""

    _svc_name_ = "gway"
    _svc_display_name_ = "GWAY"
    _svc_description_ = "Run GWAY recipe as a Windows service"

    recipe: str | None = None
    debug: bool = False
    process: subprocess.Popen | None = None

    def __init__(self, args):
        if win32serviceutil:
            super().__init__(args)
            self.stop_event = win32event.CreateEvent(None, 0, 0, None)
        else:  # pragma: no cover - not on Windows
            raise RuntimeError("win32serviceutil not available")

    def SvcStop(self):  # pragma: no cover - requires Windows
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        if self.process and self.process.poll() is None:
            try:
                self.process.terminate()
                self.process.wait(10)
            except Exception:
                pass
        win32event.SetEvent(self.stop_event)

    def SvcDoRun(self):  # pragma: no cover - requires Windows
        bat = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "gway.bat"))
        cmd = ["cmd", "/c", bat]
        if self.debug:
            cmd.append("-d")
        if self.recipe:
            cmd.extend(["-r", self.recipe])
        self.process = subprocess.Popen(cmd, cwd=os.path.dirname(bat))
        self.ReportServiceStatus(win32service.SERVICE_RUNNING)
        win32event.WaitForSingleObject(self.stop_event, win32event.INFINITE)
        if self.process and self.process.poll() is None:
            self.process.terminate()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Manage GWAY Windows service")
    parser.add_argument("command", choices=["install", "remove", "run", "start", "stop"])
    parser.add_argument("--name", required=True, help="Service name")
    parser.add_argument("--recipe", help="Recipe to run")
    parser.add_argument("--force", action="store_true", help="Force kill on remove")
    parser.add_argument("--debug", action="store_true", help="Run gway in debug mode")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)

    if not win32serviceutil:
        raise RuntimeError("pywin32 is required on Windows")

    display_name = _format_display_name(args.name)

    Service = _create_service_class(
        args.name,
        display_name,
        args.recipe,
        args.debug,
    )
    cls_name = Service.__name__

    if args.command == "install":
        if not args.recipe:
            raise SystemExit("--recipe is required for install")
        exe_args = (
            f'"{os.path.abspath(__file__)}" run --name {args.name} --recipe {args.recipe}'
        )
        if args.debug:
            exe_args += " --debug"
        win32serviceutil.InstallService(
            pythonClassString=f"{__name__}.{cls_name}",
            serviceName=args.name,
            displayName=display_name,
            exeName=win32serviceutil.LocatePythonServiceExe(),
            exeArgs=exe_args,
            startType=win32service.SERVICE_AUTO_START,
            description=f"GWAY Service ({args.recipe})",
        )
        print(f"Service {args.name} installed.")
    elif args.command == "remove":
        def _svc_missing(exc: Exception) -> bool:
            return getattr(exc, "winerror", None) == 1060

        try:
            win32serviceutil.StopService(args.name)
        except Exception as exc:
            if not _svc_missing(exc):
                print(f"Failed to stop {args.name}: {exc}")

        if args.force:
            subprocess.run(
                ["taskkill", "/F", "/FI", f"SERVICES eq {args.name}"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

        try:
            win32serviceutil.RemoveService(args.name)
        except Exception as exc:
            if _svc_missing(exc):
                print(f"Service {args.name} does not exist.")
            else:
                raise
        else:
            print(f"Service {args.name} removed.")
    elif args.command == "start":
        win32serviceutil.StartService(args.name)
    elif args.command == "stop":
        win32serviceutil.StopService(args.name)
    elif args.command == "run":
        win32serviceutil.HandleCommandLine(Service, argv=[sys.argv[0]])
    else:  # pragma: no cover - unreachable
        raise SystemExit(f"Unknown command {args.command}")


if __name__ == "__main__":  # pragma: no cover
    main()

