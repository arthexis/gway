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
import subprocess

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
        cmd = [bat, "-r", self.recipe] if self.recipe else [bat]
        self.process = subprocess.Popen(cmd, cwd=os.path.dirname(bat))
        win32event.WaitForSingleObject(self.stop_event, win32event.INFINITE)
        if self.process and self.process.poll() is None:
            self.process.terminate()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Manage GWAY Windows service")
    parser.add_argument("command", choices=["install", "remove", "run", "start", "stop"])
    parser.add_argument("--name", required=True, help="Service name")
    parser.add_argument("--recipe", help="Recipe to run")
    parser.add_argument("--force", action="store_true", help="Force kill on remove")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)

    if not win32serviceutil:
        raise RuntimeError("pywin32 is required on Windows")

    class Service(GatewayService):
        _svc_name_ = args.name
        _svc_display_name_ = args.name
        recipe = args.recipe

    if args.command == "install":
        if not args.recipe:
            raise SystemExit("--recipe is required for install")
        exe_args = (
            f'"{os.path.abspath(__file__)}" run --name {args.name} --recipe {args.recipe}'
        )
        win32serviceutil.InstallService(
            pythonClassString=f"{__name__}.GatewayService",
            serviceName=args.name,
            displayName=args.name,
            exeName=win32serviceutil.LocatePythonServiceExe(),
            exeArgs=exe_args,
            startType=win32service.SERVICE_AUTO_START,
            description=f"GWAY Service ({args.recipe})",
        )
        print(f"Service {args.name} installed.")
    elif args.command == "remove":
        try:
            win32serviceutil.StopService(args.name)
        except Exception:
            pass
        if args.force:
            subprocess.run(["taskkill", "/F", "/FI", f"SERVICES eq {args.name}"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        win32serviceutil.RemoveService(args.name)
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

