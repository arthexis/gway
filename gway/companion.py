"""Out-of-process recipe companion execution using a managed Python environment."""

from dataclasses import dataclass
import inspect
import pickle
from pathlib import Path
import struct
import subprocess
import sys
import threading
import traceback

from .ingestion.base import IngestedOperation, register_operation


_HEADER = struct.Struct("!Q")


def _read_message(stream):
    header = stream.read(_HEADER.size)
    if not header:
        raise EOFError("companion worker closed its protocol stream")
    if len(header) != _HEADER.size:
        raise EOFError("truncated companion worker message header")
    size = _HEADER.unpack(header)[0]
    payload = stream.read(size)
    if len(payload) != size:
        raise EOFError("truncated companion worker message")
    return pickle.loads(payload)


def _write_message(stream, value):
    payload = pickle.dumps(value, protocol=pickle.HIGHEST_PROTOCOL)
    stream.write(_HEADER.pack(len(payload)))
    stream.write(payload)
    stream.flush()


_WORKER = r"""
import importlib.util
import inspect
import pickle
from pathlib import Path
import struct
import sys
import traceback

HEADER = struct.Struct("!Q")


def read_message():
    header = sys.stdin.buffer.read(HEADER.size)
    if not header:
        raise EOFError
    if len(header) != HEADER.size:
        raise EOFError
    size = HEADER.unpack(header)[0]
    payload = sys.stdin.buffer.read(size)
    if len(payload) != size:
        raise EOFError
    return pickle.loads(payload)


def write_message(value):
    payload = pickle.dumps(value, protocol=pickle.HIGHEST_PROTOCOL)
    sys.__stdout__.buffer.write(HEADER.pack(len(payload)))
    sys.__stdout__.buffer.write(payload)
    sys.__stdout__.buffer.flush()


def safe_default(value):
    if value is inspect.Parameter.empty:
        return ("empty", None)
    try:
        pickle.dumps(value, protocol=pickle.HIGHEST_PROTOCOL)
    except Exception:
        return ("repr", repr(value))
    return ("value", value)


def describe(module):
    operations = []
    for name in dir(module):
        if name.startswith("_"):
            continue
        try:
            value = getattr(module, name)
        except Exception:
            continue
        if not callable(value):
            continue
        try:
            signature = inspect.signature(value)
        except (TypeError, ValueError):
            continue
        parameters = []
        for parameter in signature.parameters.values():
            default_kind, default = safe_default(parameter.default)
            parameters.append(
                {
                    "name": parameter.name,
                    "kind": parameter.kind.name,
                    "default_kind": default_kind,
                    "default": default,
                }
            )
        operations.append({"name": name, "parameters": parameters})
    return operations


path = Path(sys.argv[1]).expanduser().resolve()
module_name = "_gway_recipe_companion_" + path.stem
spec = importlib.util.spec_from_file_location(module_name, path)
if spec is None or spec.loader is None:
    raise ImportError(f"Unable to load recipe companion: {path}")
module = importlib.util.module_from_spec(spec)
sys.modules[module_name] = module

# Reserve stdout for the binary protocol. Normal companion prints are visible on stderr.
sys.stdout = sys.stderr

try:
    spec.loader.exec_module(module)
    write_message({"ok": True, "operations": describe(module)})
except BaseException as exception:
    write_message(
        {
            "ok": False,
            "error": f"{type(exception).__name__}: {exception}",
            "traceback": traceback.format_exc(),
        }
    )
    raise SystemExit(1)

while True:
    try:
        request = read_message()
    except EOFError:
        break

    if request.get("op") == "close":
        write_message({"ok": True, "result": None})
        break

    name = request["name"]
    try:
        result = getattr(module, name)(*request.get("args", ()), **request.get("kwargs", {}))
        write_message({"ok": True, "result": result})
    except BaseException as exception:
        write_message(
            {
                "ok": False,
                "error": f"{type(exception).__name__}: {exception}",
                "traceback": traceback.format_exc(),
            }
        )
"""


_KIND = {
    name: value
    for name, value in inspect._ParameterKind.__members__.items()
}


def _signature(description):
    parameters = []
    for item in description["parameters"]:
        default_kind = item["default_kind"]
        if default_kind == "empty":
            default = inspect.Parameter.empty
        elif default_kind == "value":
            default = item["default"]
        else:
            # An opaque default cannot safely cross interpreter environments.
            # Treat it as optional while avoiding an import into the host process.
            default = None
        parameters.append(
            inspect.Parameter(
                item["name"],
                kind=_KIND[item["kind"]],
                default=default,
            )
        )
    return inspect.Signature(parameters)


@dataclass
class CompanionWorker:
    """One companion module imported and executed by its recipe interpreter."""

    recipe: Path
    companion: Path
    python: Path
    process: subprocess.Popen
    operations: tuple[dict, ...]
    _lock: threading.Lock

    @classmethod
    def start(cls, recipe, companion, python):
        recipe = Path(recipe).expanduser().resolve()
        companion = Path(companion).expanduser().resolve()
        python = Path(python).expanduser().resolve()
        process = subprocess.Popen(
            [str(python), "-u", "-c", _WORKER, str(companion)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=None,
            cwd=str(companion.parent),
        )
        if process.stdin is None or process.stdout is None:
            process.kill()
            raise RuntimeError("Unable to establish recipe companion worker pipes")
        response = _read_message(process.stdout)
        if not response.get("ok"):
            process.wait()
            detail = response.get("traceback") or response.get("error")
            raise RuntimeError(f"Recipe companion import failed:\n{detail}")
        return cls(
            recipe=recipe,
            companion=companion,
            python=python,
            process=process,
            operations=tuple(response.get("operations", ())),
            _lock=threading.Lock(),
        )

    def call(self, name, args, kwargs):
        if self.process.poll() is not None:
            raise RuntimeError(f"Recipe companion worker exited: {self.companion}")
        assert self.process.stdin is not None
        assert self.process.stdout is not None
        with self._lock:
            _write_message(
                self.process.stdin,
                {"op": "call", "name": name, "args": tuple(args), "kwargs": dict(kwargs)},
            )
            response = _read_message(self.process.stdout)
        if not response.get("ok"):
            detail = response.get("traceback") or response.get("error")
            raise RuntimeError(f"Recipe companion operation failed:\n{detail}")
        return response.get("result")

    def close(self):
        if self.process.poll() is not None:
            return
        try:
            assert self.process.stdin is not None
            assert self.process.stdout is not None
            with self._lock:
                _write_message(self.process.stdin, {"op": "close"})
                _read_message(self.process.stdout)
        except (BrokenPipeError, EOFError, OSError):
            pass
        finally:
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.terminate()
                self.process.wait(timeout=2)


def _active_worker(runtime, recipe):
    recipe = Path(recipe).expanduser().resolve()
    for frame in reversed(getattr(runtime, "_recipe_frames", ()) or ()):
        if frame.path == recipe and frame.companion_worker is not None:
            return frame.companion_worker
    raise RuntimeError(f"Recipe companion is not active: {recipe}")


def _proxy(runtime, recipe, name, signature):
    def invoke(*args, **kwargs):
        return _active_worker(runtime, recipe).call(name, args, kwargs)

    invoke.__name__ = name
    invoke.__doc__ = f"Invoke {name!r} in the managed recipe environment."
    invoke.__signature__ = signature
    return invoke


def register_worker_operations(runtime, worker):
    """Register managed companion callables without importing the module in host Python."""
    root = (worker.companion.stem,)
    registered = []
    for description in worker.operations:
        name = description["name"]
        operation = IngestedOperation(
            (*root, name),
            _proxy(runtime, worker.recipe, name, _signature(description)),
            source=worker.companion,
            kind="recipe-companion-worker",
            metadata={
                "recipe": str(worker.recipe),
                "companion": str(worker.companion),
                "python": str(worker.python),
            },
        )
        existing = runtime.ops.resolve(operation.name)
        if existing is not None:
            continue
        registered.append(register_operation(runtime, operation))
    return registered
