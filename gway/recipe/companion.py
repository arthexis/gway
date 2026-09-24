"""Out-of-process recipe companion execution using a managed Python environment."""

from dataclasses import dataclass
import inspect
import pickle
from pathlib import Path
import struct
import subprocess
import threading

from ..environment import process_environment
from ..ingestion.base import IngestedOperation, register_operation
from ..security.authentication import authenticate_bearer
from ..security.oauth import OAuthRegistry
from ..security.tokens import TokenRegistry


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

environment_path = Path(sys.argv[2]).expanduser().resolve()
environment_spec = importlib.util.spec_from_file_location(
    "_gway_process_environment",
    environment_path,
)
if environment_spec is None or environment_spec.loader is None:
    raise ImportError(f"Unable to load Gway environment substrate: {environment_path}")
environment_module = importlib.util.module_from_spec(environment_spec)
environment_spec.loader.exec_module(environment_module)
process_environment = environment_module.process_environment


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


_child_request_id = 0


def request_parent(method, **params):
    global _child_request_id
    _child_request_id += 1
    request_id = f"child:{_child_request_id}"
    write_message(
        {
            "type": "request",
            "id": request_id,
            "method": method,
            "params": params,
        }
    )
    while True:
        message = read_message()
        if message.get("type") != "response":
            raise RuntimeError(
                f"Unexpected message while awaiting parent response: {message!r}"
            )
        if message.get("id") != request_id:
            raise RuntimeError(
                f"Unexpected RPC response id {message.get('id')!r}; "
                f"expected {request_id!r}"
            )
        if not message.get("ok"):
            detail = message.get("traceback") or message.get("error")
            raise RuntimeError(f"Parent Gateway request failed:\n{detail}")
        return message.get("result")


class ParentGateway:
    def list_operations(self):
        return request_parent("gateway.list")

    def describe_operation(self, name):
        return request_parent("gateway.describe", name=name)

    def call_operation(self, name, *args, **kwargs):
        return request_parent(
            "gateway.call",
            name=name,
            args=tuple(args),
            kwargs=dict(kwargs),
        )

    def execute(self, command):
        return request_parent("gateway.execute", command=command)

    def authenticate_bearer(self, bearer, resource=None):
        return request_parent(
            "gateway.authenticate_bearer",
            bearer=bearer,
            resource=resource,
        )

    def execute_authenticated(self, bearer, command, resource=None, mutate=None):
        params = {
            "bearer": bearer,
            "command": command,
            "resource": resource,
        }
        if mutate is not None:
            params["mutate"] = mutate
        return request_parent("gateway.execute_authenticated", **params)


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
module.__dict__["_gway_parent"] = ParentGateway()
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

    request_id = request.get("id")
    method = request.get("method")
    params = request.get("params", {})

    if request.get("type") != "request" or request_id is None:
        write_message(
            {
                "type": "response",
                "id": request_id,
                "ok": False,
                "error": f"Invalid RPC request: {request!r}",
            }
        )
        continue

    if method == "companion.close":
        write_message(
            {"type": "response", "id": request_id, "ok": True, "result": None}
        )
        break

    try:
        if method != "companion.call":
            raise LookupError(f"Unknown companion RPC method: {method}")
        name = params["name"]
        environment = dict(params.get("environment") or {})
        previous_environment = {
            key: process_environment.get(key)
            for key in environment
        }
        try:
            for key, value in environment.items():
                if value is None:
                    process_environment.remove(key)
                else:
                    process_environment.set(key, value)
            result = getattr(module, name)(
                *params.get("args", ()),
                **params.get("kwargs", {}),
            )
        finally:
            for key, value in previous_environment.items():
                process_environment.restore(key, value)
        write_message(
            {"type": "response", "id": request_id, "ok": True, "result": result}
        )
    except BaseException as exception:
        write_message(
            {
                "type": "response",
                "id": request_id,
                "ok": False,
                "error": f"{type(exception).__name__}: {exception}",
                "traceback": traceback.format_exc(),
            }
        )
"""


_KIND = {
    "POSITIONAL_ONLY": inspect.Parameter.POSITIONAL_ONLY,
    "POSITIONAL_OR_KEYWORD": inspect.Parameter.POSITIONAL_OR_KEYWORD,
    "VAR_POSITIONAL": inspect.Parameter.VAR_POSITIONAL,
    "KEYWORD_ONLY": inspect.Parameter.KEYWORD_ONLY,
    "VAR_KEYWORD": inspect.Parameter.VAR_KEYWORD,
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
    _next_request_id: int = 0

    @classmethod
    def start(cls, recipe, companion, python):
        recipe = Path(recipe).expanduser().resolve()
        companion = Path(companion).expanduser().resolve()
        # Preserve the venv interpreter path. Resolving it can collapse the
        # venv's python symlink to the base interpreter and lose site-packages.
        python = Path(python).expanduser().absolute()
        environment_path = Path(__file__).resolve().parents[1] / "environment.py"
        process = subprocess.Popen(
            [
                str(python),
                "-u",
                "-c",
                _WORKER,
                str(companion),
                str(environment_path),
            ],
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

    def _request(self, runtime, method, params=None):
        if self.process.poll() is not None:
            raise RuntimeError(f"Recipe companion worker exited: {self.companion}")
        assert self.process.stdin is not None
        assert self.process.stdout is not None
        self._next_request_id += 1
        request_id = f"parent:{self._next_request_id}"
        _write_message(
            self.process.stdin,
            {
                "type": "request",
                "id": request_id,
                "method": method,
                "params": {} if params is None else dict(params),
            },
        )
        while True:
            response = _read_message(self.process.stdout)
            if response.get("type") == "request":
                _service_parent_request(runtime, self.process.stdin, response)
                continue
            if response.get("type") != "response":
                raise RuntimeError(f"Invalid companion RPC message: {response!r}")
            if response.get("id") != request_id:
                raise RuntimeError(
                    f"Unexpected companion RPC response id {response.get('id')!r}; "
                    f"expected {request_id!r}"
                )
            if not response.get("ok"):
                detail = response.get("traceback") or response.get("error")
                raise RuntimeError(f"Recipe companion operation failed:\n{detail}")
            return response.get("result")

    def call(self, runtime, name, args, kwargs):
        environment = {}
        frames = getattr(runtime, "_recipe_frames", ()) or ()
        for frame in frames:
            for key in frame.environment_restore:
                environment[key] = process_environment.get(key)
        with self._lock:
            return self._request(
                runtime,
                "companion.call",
                {
                    "name": name,
                    "args": tuple(args),
                    "kwargs": dict(kwargs),
                    "environment": environment,
                },
            )

    def close(self):
        if self.process.poll() is not None:
            return
        try:
            assert self.process.stdin is not None
            assert self.process.stdout is not None
            with self._lock:
                self._next_request_id += 1
                request_id = f"parent:{self._next_request_id}"
                _write_message(
                    self.process.stdin,
                    {
                        "type": "request",
                        "id": request_id,
                        "method": "companion.close",
                        "params": {},
                    },
                )
                response = _read_message(self.process.stdout)
                if (
                    response.get("type") != "response"
                    or response.get("id") != request_id
                    or not response.get("ok")
                ):
                    raise RuntimeError(
                        f"Invalid companion close response: {response!r}"
                    )
        except (BrokenPipeError, EOFError, OSError):
            pass
        finally:
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.terminate()
                self.process.wait(timeout=2)


def _parent_operation_names(runtime):
    records = runtime.ops._registry.records
    return tuple(sorted(records))


def _describe_parent_operation(runtime, name):
    records = runtime.ops._registry.records
    record = records.get(name)
    if record is None:
        raise LookupError(f"Unknown canonical GWAY operation: {name}")
    signature = inspect.signature(record.callable)
    parameters = []
    for parameter in signature.parameters.values():
        if parameter.default is inspect.Parameter.empty:
            default_kind = "empty"
            default = None
        else:
            try:
                pickle.dumps(parameter.default, protocol=pickle.HIGHEST_PROTOCOL)
            except Exception:
                default_kind = "repr"
                default = repr(parameter.default)
            else:
                default_kind = "value"
                default = parameter.default
        parameters.append(
            {
                "name": parameter.name,
                "kind": parameter.kind.name,
                "default_kind": default_kind,
                "default": default,
            }
        )
    return {
        "name": record.name,
        "operation": record.op,
        "subject": record.sub,
        "parameters": parameters,
        "doc": inspect.getdoc(record.callable),
    }


def _service_parent_request(runtime, stream, request):
    request_id = request.get("id")
    method = request.get("method")
    params = request.get("params", {})
    try:
        if request_id is None:
            raise ValueError("Parent RPC request requires an id")
        if method == "gateway.list":
            result = _parent_operation_names(runtime)
        elif method == "gateway.describe":
            result = _describe_parent_operation(runtime, params["name"])
        elif method == "gateway.call":
            result = runtime(
                params["name"],
                *tuple(params.get("args", ())),
                **dict(params.get("kwargs", {})),
            )
        elif method == "gateway.execute":
            with runtime.external_authority():
                result = runtime(params["command"])
        elif method in {
            "gateway.authenticate_bearer",
            "gateway.execute_authenticated",
        }:
            bearer = params["bearer"]
            registry_args = {}
            if str(bearer).startswith("gwt_"):
                registry_args["tokens"] = TokenRegistry()
            elif str(bearer).startswith("gwa_"):
                registry_args["oauth"] = OAuthRegistry()
            identity = authenticate_bearer(
                bearer,
                resource=params.get("resource"),
                **registry_args,
            )
            if method == "gateway.authenticate_bearer":
                result = {
                    "kind": identity.kind,
                    "principal": identity.principal,
                    "client_id": identity.client_id,
                    "scopes": sorted(identity.scopes),
                }
            else:
                with runtime.authorized(
                    operations=identity.authority.operations,
                    environment=identity.authority.environment,
                ):
                    with runtime.external_authority():
                        result = runtime.execute(
                            params["command"],
                            mutate=params.get("mutate", True),
                        )
        else:
            raise LookupError(f"Unknown parent Gateway RPC method: {method}")
        response = {
            "type": "response",
            "id": request_id,
            "ok": True,
            "result": result,
        }
    except BaseException as exception:
        import traceback

        response = {
            "type": "response",
            "id": request_id,
            "ok": False,
            "error": f"{type(exception).__name__}: {exception}",
            "traceback": traceback.format_exc(),
        }
    _write_message(stream, response)


def _active_worker(runtime, recipe):
    recipe = Path(recipe).expanduser().resolve()
    for frame in reversed(getattr(runtime, "_recipe_frames", ()) or ()):
        if frame.path == recipe and frame.companion_worker is not None:
            return frame.companion_worker
    raise RuntimeError(f"Recipe companion is not active: {recipe}")


def _proxy(runtime, recipe, name, signature):
    def invoke(*args, **kwargs):
        return _active_worker(runtime, recipe).call(runtime, name, args, kwargs)

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


def unregister_worker_operations(runtime, worker):
    """Hide operations previously registered for one managed companion."""
    root = worker.companion.stem
    removed = []
    for description in worker.operations:
        name = f"{root}.{description['name']}"
        operation = runtime.ops.resolve(name)
        if operation is None:
            continue
        metadata = getattr(operation, "__gway_metadata__", {})
        if (
            getattr(operation, "__gway_source_kind__", None)
            != "recipe-companion-worker"
            or metadata.get("companion") != str(worker.companion)
        ):
            continue
        runtime.ops.unregister(name)
        removed.append(name)
    return tuple(removed)
