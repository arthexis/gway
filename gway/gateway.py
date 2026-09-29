# file: gway/gateway.py

from contextlib import contextmanager, nullcontext
import inspect
from contextvars import ContextVar

from .runner import invoke
from .bindings import Bindings
from . import log as gway_log
from .normalization import complete_arguments
from .mutation import (
    MUTATE_UNSET,
    MutationError,
    mutates,
    public_signature,
    supports_no_mutate,
)
from .environment import process_environment
from .operations import registry_views, split_operation
from .publication import publish
from .sigil import Resolver
from .sigil.resolver import Environment
from .state import RequestMapping, RequestState


class Gateway(Resolver):
    """Minimal GWAY runtime: resolution, callable wrapping, and request-local context."""

    def __init__(
        self,
        *,
        context=None,
        name="gw",
        debug=False,
        verbose=False,
        silent=False,
        log_level=None,
        interactive=False,
        timed=False,
        cache=None,
        **values,
    ):
        self.name = name
        self._sigil_dispatch_enabled = False
        self._cache_explicit = cache is not None
        self.environment = process_environment
        self.bindings = Bindings()
        self.logger = gway_log._child(name, level=log_level)
        for level_name, level in gway_log._levels(self.logger).items():
            setattr(self, level_name, level)
        self.ops, self.subs = registry_views()

        from .routes import OperationRoutes
        from .sampler import expand as expand_sampler

        self.operation_routes = OperationRoutes()
        self.operation_routes.register("sampler", expand_sampler)

        from .launchable import Launchables

        self.launchables = Launchables()
        self._service_presets = {}
        self._ingested = {}
        self._guide_rules = ()
        self._guide_documents = ()

        self.gway_identity = None

        from .cache import Cache
        from .journal import JournalManager
        self._root_state = RequestState()
        self._request_state_var = ContextVar(
            f"gway_request_state_{id(self)}",
            default=None,
        )
        self.debug_enabled = bool(debug)
        self.verbose = bool(verbose)
        self.silent = bool(silent)
        self.interactive_enabled = bool(interactive)
        self.timed_enabled = bool(timed)

        if context:
            self.context.update(context)
        if values:
            self.context.update(
                {key: value for key, value in values.items() if value is not None}
            )
        self.context["verbose"] = self.verbose
        self.context["silent"] = self.silent

        super().__init__(
            [
                ("results", RequestMapping(self, "results")),
                ("context", RequestMapping(self, "context")),
                ("bindings", self.bindings),
                (
                    "env",
                    Environment(
                        reader=self._environment_value,
                        names=self._environment_names,
                    ),
                ),
            ]
        )

        from . import builtin
        from .ingestion.python import ingest_module

        ingest_module(self, builtin, transparent=True)

        self.install = self.wrap("install", self._install)
        self.uninstall = self.wrap("uninstall", self._uninstall)
        self.products = self.wrap("products", self._products)
        self.extensions = self.wrap("extensions", self._extensions)

        from .source import inspect_source, search_source_corpus

        self.search_source = self.wrap(
            "search.source",
            lambda query, kind=None, topic=(), context=0, mutate=False: (
                search_source_corpus(
                    self,
                    query,
                    kind=kind,
                    topic=topic,
                    context=context,
                    mutate=mutate,
                )
            ),
            op="search",
            sub="source",
        )

        self.source = self.wrap(
            "source",
            lambda *operation, search=None, context=2, all=False, mutate=False: (
                inspect_source(
                    self,
                    *operation,
                    search=search,
                    context=context,
                    all=all,
                    mutate=mutate,
                )
            ),
        )

        from .filesystem import Filesystem
        from .rendering import Renderer

        self._filesystem = Filesystem(self)
        self.copy = self.wrap("copy", self._filesystem.copy)
        self.move = self.wrap("move", self._filesystem.move)
        self.link = self.wrap("link", self._filesystem.link)
        self.remove = self.wrap("remove", self._filesystem.remove)

        self._renderer = Renderer(self)
        self.render = self.wrap("render", self._renderer.render)

        self.commit = self.wrap("commit", self._commit_journal)
        self.rollback = self.wrap("rollback", self._rollback_journal)
        self.clear = self.wrap("clear", self._clear_context)
        self.default = self.wrap("default", self._default_context, op="default", sub="default")
        self.pipe = self.wrap("pipe", self._pipe_context, op="pipe", sub="pipe")
        self.set_env = self.wrap("set.env", self._set_environment, op="set", sub="env")
        self.clear_env = self.wrap(
            "clear.env", self._clear_environment, op="clear", sub="env"
        )
        self.ops.register_alias("set-env", self.set_env)
        self.ops.register_alias("clear-env", self.clear_env)
        self.require = self.wrap("require", self._require)
        self.help = self.wrap("help", self._help)
        self.resolve_target = self._resolve_target
        self.guide = self.wrap("guide", self._guide)
        self.node = self.wrap("node", self._node)
        self.wrap("ingest", self.ingest)
        self.recipe = self.wrap("recipe", self._run_sampler_recipe)
        self.recipe_check = self.wrap(
            "recipe.check",
            self._check_recipes,
            op="recipe",
            sub="check",
        )
        self.reload = self.wrap("reload", self._reload)

        from .providers.core import register as register_core_provider
        from .providers.godaddy import register as register_godaddy_provider
        from .config import bootstrap

        register_core_provider(self)
        register_godaddy_provider(self)

        from .install.identity import running_gway_identity

        self.gway_identity = running_gway_identity(paths=self.install_paths())
        bootstrap(self)

        if isinstance(cache, Cache):
            self.cache = cache
        else:
            with self.topics("cache"):
                configured_cache = self.resolve("[cache_dir]", default=cache)
            self.cache = Cache(configured_cache)
        self._root_state.journal = JournalManager(
            self.cache.root / "rollback",
            rollback_executor=self._execute_operation_rollback,
        )
        self.security_path = self.cache.root / "security" / "state.sqlite"

        with self.topics("log"):
            log_source = self.resolve("[source]", default="gway")
        gway_log._set_default_source(log_source)

        from .ingestion.python import ingest_python
        from .security.client import Controller as OAuthClientController
        from .security.controller import Controller as SecurityController
        from .security.scope import Controller as ScopeController
        from .security.token import Controller as TokenController
        from .remote.service import register as register_remote_service
        from .service.controller import Controller
        from .souschef.controller import Controller as SousChefController
        from .souschef.service import register as register_souschef_service

        register_souschef_service(self)
        register_remote_service(self)

        self._service_controller = Controller(self)
        ingest_python(self, self._service_controller, path=("service",))
        self._security_controller = SecurityController(self)
        ingest_python(
            self,
            self._security_controller,
            path=("security",),
        )
        self._oauth_client_controller = OAuthClientController(self)
        ingest_python(
            self,
            self._oauth_client_controller,
            path=("security", "oauth", "client"),
        )
        self._scope_controller = ScopeController(self)
        ingest_python(
            self,
            self._scope_controller,
            path=("security", "scope"),
        )
        self._token_controller = TokenController(self)
        ingest_python(
            self,
            self._token_controller,
            path=("security", "token"),
        )

        from .httpops import Controller as HTTPController

        self._http_controller = HTTPController()
        ingest_python(self, self._http_controller, path=("http",))

        from .githubops import ADMIN_OPERATIONS as github_admin
        from .githubops import Controller as GitHubController
        from .githubops import WRITE_OPERATIONS as github_writes

        self._github_controller = GitHubController(self)
        ingest_python(self, self._github_controller, path=("github",))

        from .watchtower import register as register_watchtower

        register_watchtower(self)

        from .observation import register as register_observation

        register_observation(self)
        for record in self.ops.records():
            if record.name.startswith("github."):
                operation = record.name.removeprefix("github.")
                access = "write" if operation in github_writes else "read"
                metadata = dict(getattr(record.callable, "__gway_metadata__", {}) or {})
                topics = (*metadata.get("topics", ()), "github", "source", access)
                if operation in github_admin:
                    topics = (*topics, "admin")
                metadata["topics"] = tuple(dict.fromkeys(topics))
                record.callable.__gway_metadata__ = metadata
                record.callable.mutates = access == "write"
                record.callable.__gway_mutates__ = record.callable.mutates
                if access == "read":
                    record.callable.__gway_supports_no_mutate__ = True

        from .dns import Controller as DNSController
        from .network import Controller as NetworkController

        self._dns_controller = DNSController(self)
        ingest_python(self, self._dns_controller, path=("dns",))
        self._network_controller = NetworkController(self)
        ingest_python(self, self._network_controller, path=("network",))

        self._souschef_controller = SousChefController(self)
        ingest_python(self, self._souschef_controller, path=("sous", "chef"))
        self._sigil_dispatch_enabled = True

    def converge_security_scopes(self, *, retire_missing=True):
        """Converge discovered scope policy into durable security state on demand."""
        from .security.defaults import converge_scope_registry
        from .security.scopes import ScopeRegistry

        return converge_scope_registry(
            ScopeRegistry(self.security_path),
            getattr(self, "_published_scopes", {}),
            retire_missing=retire_missing,
        )

    def _execute_operation_rollback(self, operation, result):
        """Resolve and execute the semantic inverse of one operation result."""
        forward = self.ops.resolve(operation)
        if forward is None:
            raise LookupError(f"Unable to resolve rollback source operation: {operation}")
        inverse = self.ops.rollback_operation(forward)
        if inverse is None:
            raise LookupError(f"No semantic rollback operation for {operation}")

        values = dict(result) if isinstance(result, dict) else {}
        signature = inspect.signature(inverse)
        kwargs = {
            name: values[name]
            for name, parameter in signature.parameters.items()
            if name in values
            and parameter.kind
            in (
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                inspect.Parameter.KEYWORD_ONLY,
            )
        }
        missing = [
            name
            for name, parameter in signature.parameters.items()
            if parameter.default is inspect.Parameter.empty
            and parameter.kind
            in (
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                inspect.Parameter.KEYWORD_ONLY,
            )
            and name not in kwargs
        ]
        if missing:
            names = ", ".join(missing)
            raise TypeError(
                f"Rollback result for {operation} cannot satisfy inverse "
                f"{self.ops.canonical_name(inverse, inverse.__name__)}: {names}"
            )
        return inverse(**kwargs)

    @property
    def request_state(self):
        """Return the state container selected for this logical request."""
        return self._request_state_var.get() or self._root_state

    @property
    def in_request(self):
        """Return whether an explicit request-local state is active."""
        return self._request_state_var.get() is not None

    @property
    def context(self):
        """Return semantic context for the active request."""
        return self.request_state.context

    @property
    def results(self):
        """Return semantic results for the active request."""
        return self.request_state.results

    @property
    def execution(self):
        return self.request_state.execution

    @execution.setter
    def execution(self, value):
        self.request_state.execution = value

    @property
    def previous_execution(self):
        return self.request_state.previous_execution

    @previous_execution.setter
    def previous_execution(self, value):
        self.request_state.previous_execution = value

    @property
    def _execution_depth(self):
        return self.request_state.execution_depth

    @_execution_depth.setter
    def _execution_depth(self, value):
        self.request_state.execution_depth = value

    @property
    def _execution_suspension(self):
        return self.request_state.execution_suspension

    @_execution_suspension.setter
    def _execution_suspension(self, value):
        self.request_state.execution_suspension = value

    @property
    def journal(self):
        """Return the rollback journal manager owned by the active request."""
        return self.request_state.journal

    @journal.setter
    def journal(self, value):
        """Replace the rollback journal manager for the active request."""
        self.request_state.journal = value

    @property
    def _authorization_stack_var(self):
        return self.request_state.authorization_stack

    @property
    def _capability_depth_var(self):
        return self.request_state.capability_depth

    @property
    def _mutation_policy_var(self):
        return self.request_state.mutation_policy

    @property
    def _semantic_topics_var(self):
        return self.request_state.semantic_topics

    @contextmanager
    def request_scope(self, *, context=None):
        """Select state for one logical request, reusing nested request scopes."""
        if self.in_request:
            if context:
                self.context.update(context)
            yield self.request_state
            return

        from .journal import JournalManager

        state = RequestState(
            journal=JournalManager(
                self.cache.root / "rollback",
                rollback_executor=self._execute_operation_rollback,
            ),
        )
        state.context["verbose"] = self.verbose
        state.context["silent"] = self.silent
        if context:
            state.context.update(context)
        token = self._request_state_var.set(state)
        try:
            yield state
        finally:
            self._request_state_var.reset(token)

    def _evaluate_expression(self, expression):
        """Delegate unresolved sigil expressions to the normal Gway dispatcher."""
        if not self._sigil_dispatch_enabled:
            from .sigil.resolution import UnresolvedSigilError

            raise UnresolvedSigilError(expression)

        from .dispatch import OperationLookupError, dispatch, resolve_operation
        from .sigil.resolution import UnresolvedSigilError
        from .tokens import tokenize

        tokens = tokenize(expression)
        try:
            resolve_operation(self, tokens)
        except OperationLookupError as exc:
            raise UnresolvedSigilError(expression) from exc
        return dispatch(self, tokens)

    def _resolve_target(self, value: str, *command, mutate=False):
        """Resolve a semantic value or command target without executing the command.

        A single argument uses ordinary sigil/value resolution. Two or more
        positional tokens inspect normal command dispatch and report the selected
        operation or sampler recipe without invoking it.
        """
        del mutate
        if not command:
            return value

        from .dispatch import resolve_target

        return resolve_target(self, (value, *command))

    def _default_context(self, **values):
        """Publish explicit semantic values into the containing context."""
        from .publication import SKIP_PUBLICATION

        self.context.update(values)
        return SKIP_PUBLICATION

    def _pipe_context(self, *, mutate=False, **values):
        """Return selected semantic context as a result-only mapping.

        Bare flags reuse an existing contextual value when one is available;
        otherwise they contribute True. Explicit flag values always win.
        With no flags, return a detached snapshot of the current context.
        """
        from .publication import ResultOnlyMapping
        from .semantic import resolve_mapping_key

        if not values:
            return ResultOnlyMapping(self.context)

        selected = {}
        for name, value in values.items():
            if value is True:
                try:
                    key = resolve_mapping_key(self.context, name)
                except KeyError:
                    pass
                else:
                    value = self.context[key]
            selected[name] = value
        return ResultOnlyMapping(selected)

    def data_root(self, *, system=False):
        """Resolve Gway's durable data root through semantic configuration."""
        from .install.paths import data_root

        scope = "system" if system else "user"
        with self.topics(scope):
            configured = self.resolve("[data_dir]", default=None)
        return data_root(system=system, data_dir=configured)

    def bin_root(self, *, system=False):
        """Resolve Gway's launcher directory through semantic configuration."""
        from .install.paths import bin_root

        scope = "system" if system else "user"
        with self.topics(scope):
            configured = self.resolve("[bin_dir]", default=None)
        return bin_root(system=system, bin_dir=configured)

    def install_paths(self, *, system=False, root=None):
        """Return durable install paths from semantic roots plus platform defaults."""
        from .install.paths import install_paths

        with self.trusted_capability():
            data_dir = None if root is not None else self.data_root(system=system)
            bin_dir = self.bin_root(system=system)

        return install_paths(
            system=system,
            root=root,
            data_dir=data_dir,
            bin_dir=bin_dir,
        )

    def _install(self, source, *, ref=None, upgrade=True, force=False, stash=False, system=False):
        """Converge one local or Git artifact installation toward requested state.

        Args:
            source: Local product or extension path, Git source, GitHub shorthand, or known installation identity.
            ref: Branch, tag, or commit requested for Git sources.
            upgrade: Replace an existing installation when the requested source state changes.
            force: Discard drift in a dirty managed installation before reconciliation.
            stash: Preserve a dirty managed installation before reconciliation.
            system: Use system-wide data and launcher locations instead of user locations.
        """
        from .cache import Cache
        from .install.ops import install as install_operation

        if self._cache_explicit:
            cache = self.cache
        else:
            with self.topics("cache"):
                configured_cache = self.resolve("[cache_dir]", default=None)
            cache = self.cache if configured_cache is None else Cache(configured_cache)
        return install_operation(
            source,
            ref=ref,
            upgrade=upgrade,
            force=force,
            stash=stash,
            system=system,
            cache=cache,
            paths=self.install_paths(system=system),
        )

    def _installed_by_kind(self, kind):
        """Return installed artifacts of one lifecycle kind across both scopes."""
        from .config import discover_installations

        records = []
        for system in (False, True):
            try:
                records.extend(
                    record
                    for record in discover_installations(self, system=system)
                    if record.kind == kind
                )
            except (OSError, PermissionError):
                continue
        return [
            {
                "name": record.name,
                "kind": record.kind,
                "scope": record.scope,
                "source": record.source,
                "install_path": str(record.install_path),
                "requested_ref": record.requested_ref,
                "resolved_revision": record.resolved_revision,
                "installed_at": record.installed_at,
            }
            for record in sorted(records, key=lambda item: (item.name, item.scope))
        ]

    def _check_recipes(self, target=None, *, mutate=False):
        """Statically validate one recipe file/tree or the maintained sampler."""
        del mutate
        from .recipe.validation import validate_recipes

        return validate_recipes(self, target)

    def _products(self, mutate=False):
        """List installed products without inspecting GWAY extensions."""
        del mutate
        return self._installed_by_kind("product")

    def _extensions(self, mutate=False):
        """List installed GWAY extensions without mixing in products."""
        del mutate
        return self._installed_by_kind("extension")

    def _uninstall(self, project, *, system=False):
        """Converge one managed installation toward absence."""
        from .install.ops import uninstall as uninstall_operation

        return uninstall_operation(
            project,
            system=system,
            paths=self.install_paths(system=system),
        )

    def bind(self, semantic_key, *bindings, replace=True):
        """Register ordered physical bindings for one exact semantic key."""
        return self.bindings.register(
            semantic_key,
            *bindings,
            replace=replace,
        )

    @property
    def semantic_topics(self):
        """Return execution-local semantic topics from broadest to most-local."""
        return self._semantic_topics_var.get()

    @contextmanager
    def topics(self, *topics):
        """Temporarily extend the semantic topics used to resolve subjects."""
        normalized = tuple(str(topic).strip() for topic in topics)
        if not normalized or any(not topic for topic in normalized):
            raise ValueError("semantic topics must be non-empty")
        token = self._semantic_topics_var.set((*self.semantic_topics, *normalized))
        try:
            yield self.semantic_topics
        finally:
            self._semantic_topics_var.reset(token)

    @property
    def execution_depth(self):
        """Return the current nested GWay execution depth."""
        return self._execution_depth

    @contextmanager
    def execution_scope(self):
        """Own one nested execution scope and finalize only at the outer boundary."""
        outermost = self._execution_depth == 0
        if outermost:
            self._execution_suspension = None
        self._execution_depth += 1
        primary = None
        try:
            yield outermost
        except BaseException as exception:
            primary = exception
            raise
        finally:
            self._execution_depth -= 1
            if outermost:
                suspension = self._execution_suspension
                self._execution_suspension = None
                from .reload import ReloadTransferred

                transferred = isinstance(primary, ReloadTransferred)
                if transferred and suspension is not None:
                    self.info(
                        "execution transferred to reload checkpoint %s with "
                        "rollback session %s",
                        suspension.checkpoint_id,
                        self.journal.session_id,
                    )
                elif primary is not None:
                    self._finalize_execution(primary)
                elif suspension is None:
                    self._finalize_execution(None)
                else:
                    self.info(
                        "execution suspended for reload checkpoint %s with "
                        "rollback session %s",
                        suspension.checkpoint_id,
                        self.journal.session_id,
                    )

    def suspend_execution(self, checkpoint):
        """Transfer this outer execution boundary to one persisted reload checkpoint."""
        from .reload import ReloadCheckpoint

        if self._execution_depth <= 0:
            raise RuntimeError("execution can only be suspended from an active scope")
        if not isinstance(checkpoint, ReloadCheckpoint):
            raise TypeError("execution suspension requires a ReloadCheckpoint")

        checkpoint.validated()
        open_journals = self.journal.open_names()
        from .reload import ReloadMode

        restarting_clean = (
            checkpoint.mode is ReloadMode.RESTART
            and checkpoint.journal_session_id is None
            and not checkpoint.open_journals
            and not open_journals
        )
        if (
            not restarting_clean
            and checkpoint.journal_session_id != self.journal.session_id
        ):
            raise ValueError(
                "reload checkpoint rollback session does not match current execution"
            )

        if tuple(checkpoint.open_journals) != open_journals:
            raise ValueError(
                "reload checkpoint open journals do not match current execution"
            )

        self._execution_suspension = checkpoint
        return checkpoint

    def _finalize_execution(self, primary=None):
        """Resolve open journals at the outermost execution boundary."""
        from .journal import (
            JournalError,
            RollbackRecoveryError,
            UncommittedJournalError,
            attach_rollback_error,
        )

        open_journals = self.journal.open_names()
        if not open_journals:
            return None

        cleanup_order = tuple(reversed(open_journals))

        if primary is not None:
            rollback_errors = []
            for name in cleanup_order:
                self.info(
                    "execution failed with open rollback journal %r; "
                    "rolling back automatically",
                    name,
                )
                try:
                    self.journal.rollback(name)
                except JournalError as exception:
                    rollback_errors.append(exception)

            if len(rollback_errors) == 1:
                attach_rollback_error(primary, rollback_errors[0])
            elif rollback_errors:
                attach_rollback_error(
                    primary,
                    RollbackRecoveryError(rollback_errors),
                )
            return None

        rollback_errors = []
        for name in cleanup_order:
            self.info(
                "uncommitted rollback journal %r detected at execution boundary",
                name,
            )
            try:
                self.journal.rollback(name)
            except Exception as exception:
                rollback_errors.append(exception)

        boundary_error = UncommittedJournalError(
            open_journals,
            rollback_errors=rollback_errors,
        )
        if rollback_errors:
            raise boundary_error from rollback_errors[0]
        raise boundary_error

    def _commit_journal(self, name):
        """Commit one named rollback journal and discard its rollback material."""
        self.journal.commit(name)
        return name

    def _rollback_journal(self, name):
        """Roll back one named journal and discard it after full success."""
        self.journal.rollback(name)
        return name

    def _clear_context(self, **values):
        """Clear accumulated semantic context.

        With no named values, clear the entire context. Bare keyword flags
        remove only the corresponding context keys while preserving operation
        registration and result history.

        Args:
            values: Context-key names to remove selectively.
        """
        if values:
            for name in values:
                self.context.pop(name, None)
        else:
            self.context.clear()
        return None

    def _active_recipe_frame(self):
        frames = getattr(self, "_recipe_frames", ()) or ()
        if not frames:
            raise RuntimeError("environment mutation is only available during recipe execution")
        return frames[-1]

    def _remember_environment_value(self, frame, name):
        if name not in frame.environment_restore:
            frame.environment_restore[name] = self.environment.get(name)

    def _set_environment(self, name, value):
        """Set one environment variable for the active recipe scope.

        The override is inherited by downstream operations and child recipes,
        then restored when the current recipe frame exits.

        Args:
            name: Environment variable name.
            value: Environment variable value.
        """
        frame = self._active_recipe_frame()
        name = str(name).strip()
        if not name or "=" in name or "\x00" in name:
            raise ValueError("environment variable name must be non-empty and contain no '='")
        value = str(value)
        if "\x00" in value:
            raise ValueError("environment variable value cannot contain NUL")
        self._remember_environment_value(frame, name)
        self.environment.set(name, value)
        return value

    def _clear_environment(self, name):
        """Clear one environment variable for the active recipe scope.

        The prior value, if any, is restored when the current recipe exits.

        Args:
            name: Environment variable name.
        """
        frame = self._active_recipe_frame()
        name = str(name).strip()
        if not name or "=" in name or "\x00" in name:
            raise ValueError("environment variable name must be non-empty and contain no '='")
        self._remember_environment_value(frame, name)
        self.environment.remove(name)
        return None

    def _require(self, *packages: str, python: bool = True):
        """Declare dependencies required by the currently executing recipe.

        Python requirements are the default today. The explicit --python flag
        is retained as a backend selector so other requirement types can be
        introduced later without changing the basic command shape.

        Args:
            packages: One or more package requirement specifiers.
            python: Select Python package requirements. Defaults to true.
        """
        frames = getattr(self, "_recipe_frames", ()) or ()
        if not frames:
            raise RuntimeError("require is only available during recipe execution")
        if not packages:
            raise TypeError("require needs at least one package")
        if python is not True:
            raise ValueError("require currently supports only Python requirements")

        normalized = []
        for package in packages:
            if not isinstance(package, str) or not package.strip():
                raise ValueError("require package names must be non-empty strings")
            normalized.append(package.strip())

        frame = frames[-1]
        preflight = frame.preflight_requirements.get("python", [])
        if preflight:
            undeclared = [package for package in normalized if package not in preflight]
            if undeclared:
                raise RuntimeError(
                    "require preflight mismatch for " + ", ".join(undeclared)
                )
        else:
            if frame.uv is None:
                from .recipe.uv import ensure_uv

                frame.uv = ensure_uv(
                    system=getattr(frame.environment, "scope", "user") == "system"
                )
            from .recipe.environment import sync_python_environment

            sync_python_environment(frame.environment, frame.uv, normalized)

        requirements = frame.requirements.setdefault("python", [])
        for package in normalized:
            if package not in requirements:
                requirements.append(package)

        if frame.companion_worker is not None and not frame.companion_registered:
            from .recipe.companion import register_worker_operations

            register_worker_operations(self, frame.companion_worker)
            frame.companion_registered = True
        return tuple(requirements)

    def _run_sampler_recipe(self, recipe_name, **context):
        """Run one maintained sampler recipe."""
        from .sampler import run

        return run(self, recipe_name, **context)

    def _reload(
        self,
        timeout: float = 30.0,
        when: str | None = None,
        fresh: bool = False,
        restart: bool = False,
    ):
        """Reload GWAY in a successor process and continue the active recipe.

        Args:
            timeout: Seconds to wait for the successor to adopt the checkpoint.
            when: Reload only when the managed GWAY runtime changed.
            fresh: Resume with fresh semantic context and result history.
            restart: Roll back the current run and restart the top-level recipe.
        """
        from .reload import perform_reload

        return perform_reload(
            self,
            timeout=timeout,
            when=when,
            fresh=fresh,
            restart=restart,
        )

    def namespace(self, *parts):
        """Return structured information about one command-group namespace."""
        from .documentation import describe

        name = " ".join(str(part) for part in parts).strip()
        if not name:
            raise TypeError("namespace requires a command group")

        children = []
        for child, operation in self.ops.children(name):
            command = f"{name} {child}"
            if operation is None:
                summary = "Command group."
                group = True
            else:
                summary = describe(operation).summary or ""
                group = self.ops.is_namespace(command)
            children.append(
                {"name": child, "command": command, "summary": summary, "group": group}
            )
        if not children:
            raise LookupError(f"Unknown command group: {name}")
        canonical = ".".join(
            part for part in name.replace(".", " ").split() if part
        )
        return {
            "group": name,
            "default": name if self.ops.resolve(canonical) is not None else None,
            "operations": children,
        }

    def _operation_visible(self, name):
        """Return whether one canonical operation is visible to the caller."""
        authority = self.authorization
        if authority is None or "__all__" in authority.operations:
            return True
        return name in authority.operations or name in {
            "security.whoami",
            "security.scope.current",
        }

    def _source_operation_visible(self, name):
        """Return whether one operation's source is visible to the caller."""
        authority = self.authorization
        if authority is None or "__all__" in authority.operations:
            return True
        return name in authority.operations

    def _operation_catalog(self):
        """Return visible discoverable operations in stable lexical order."""
        from .documentation import describe
        from .ingestion.base import expand_path

        roots = sorted(
            {
                path[:1]
                for record in self._ingested.values()
                for path in record.paths
                if len(path) == 1
            }
        )
        for root in roots:
            expand_path(self, root)

        items = []
        for record in sorted(self.ops.records(), key=lambda item: item.name):
            if not self._operation_visible(record.name):
                continue
            items.append((record.name, describe(record.callable).summary or ""))
        return items

    def _namespace_help(self, name):
        info = self.namespace(*str(name).split())
        visible = []
        for item in info["operations"]:
            command = item["command"].replace(" ", ".")
            if item["group"]:
                if not any(
                    operation == command or operation.startswith(f"{command}.")
                    for operation, _ in self._operation_catalog()
                ):
                    continue
            elif not self._operation_visible(command):
                continue
            visible.append(item)
        lines = [f"{info['group']} operations:", ""]
        if not visible:
            lines.append("  (no authorized operations)")
            return "\n".join(lines)
        width = max(len(item["name"]) for item in visible)
        for item in visible:
            suffix = " >" if item["group"] else ""
            lines.append(
                f"  {item['name']:<{width}}{suffix}  {item['summary']}".rstrip()
            )
        if info["default"] is not None and self._operation_visible(
            info["default"].replace(" ", ".")
        ):
            lines.extend(["", f"Bare '{info['group']}' runs its group default."])
        return "\n".join(lines)

    def _command_help(self, *tokens: str, verbose=False):
        """Return help for the callable prefix of one CLI command."""
        from .documentation import render
        from .dispatch import resolve_operation
        from .tokens import tokenize

        if not tokens:
            raise TypeError("command help requires an operation name")
        resolution = resolve_operation(self, tokenize(" ".join(tokens)))
        target, remaining, candidate = resolution
        if not remaining and self.ops.is_namespace(candidate):
            return self._namespace_help(candidate.replace(".", " "))
        return render(target, verbose=verbose)

    def _help(
        self,
        *operation: str,
        verbose=False,
        mutate=False,
        **help_topics,
    ):
        """Return documentation for one Gway operation, group, topic, or parameter.

        Args:
            operation: Operation name parts followed by an optional help topic.
            verbose: Include full documentation and merged parameter details.
        """
        del mutate
        from .documentation import render, render_topic
        from .dispatch import resolve_operation
        from .tokens import tokenize, token_value

        if not operation and not help_topics:
            catalog = self._operation_catalog()
            lines = ["Available operations:", ""]
            width = max((len(name) for name, _ in catalog), default=0)
            for name, summary in catalog:
                lines.append(f"  {name:<{width}}  {summary}".rstrip())
            return "\n".join(lines)

        values = list(operation)
        query_flags = [
            f"--{str(name).replace('_', '-')}"
            for name in help_topics
            if name not in {"verbose", "mutate"}
        ]
        name = " ".join(values)
        if name and self.ops.is_namespace(name) and not query_flags:
            return self._namespace_help(name)

        target, remaining, candidate = resolve_operation(self, tokenize(name))
        if self.ops.is_namespace(candidate) and not remaining and not query_flags:
            return self._namespace_help(candidate.replace(".", " "))
        canonical = self.ops.canonical_name(target, candidate)
        if not self._operation_visible(canonical):
            raise LookupError(f"Operation is not available to current scope: {name}")

        query = [token_value(item) for item in remaining]
        query.extend(query_flags)
        if query:
            rendered = render_topic(target, *query)
            if rendered:
                return rendered
            requested = " ".join(str(item) for item in query)
            raise LookupError(
                f"No help topic {requested!r} for operation {canonical!r}"
            )
        return render(target, verbose=verbose)

    def _guide(self, *task: str, mutate=False):
        """Return preferred explicit guidance for a task.

        Args:
            task: Natural-language task description to match against explicit guidance.
        """
        del mutate
        if not task:
            raise TypeError("guide requires a task")
        from .guide import guide
        from .sampler import recipes

        return guide(
            " ".join(task),
            self._guide_rules,
            role=self.find_value("role", include_environment=False),
            operations=self.ops.records(),
            recipes=recipes(),
            documents=self._guide_documents,
            authorization=self.authorization,
        )

    def _node(self, *parts: str, mutate=False):
        """Inspect or dispatch the active node role.

        Bare `node` reports the active role family and available role-owned
        operations. `node <verb> [args...]` dispatches to the canonical
        `node.<role>.<verb>` operation registered for the active role.

        Args:
            parts: Role-local operation verb followed by its arguments.
        """
        role = self.find_value("role", include_environment=False)
        if role is None:
            raise LookupError("node requires an active semantic role")

        role = str(role).strip()
        if not role:
            raise LookupError("node requires a non-empty semantic role")
        family = f"node.{role}"

        authority = self.authorization
        available = []
        for record in self.ops.records():
            prefix = f"{family}."
            if not record.name.startswith(prefix):
                continue
            if authority is not None and record.name not in authority.operations:
                continue
            available.append(record.name[len(prefix):].replace(".", " "))

        if not parts:
            from . import builtin
            from .publication import ResultOnlyMapping

            project = None
            project_path = getattr(self, "_project_path", None)
            if project_path is not None:
                try:
                    from .install.source import project_name

                    project = {
                        "name": project_name(project_path.parent),
                        "root": str(project_path.parent.resolve()),
                    }
                except (OSError, ValueError):
                    project = {
                        "name": None,
                        "root": str(project_path.parent.resolve()),
                    }

            identity = self.gway_identity
            runtime = {
                "version": builtin.version(),
                "managed": identity is not None,
                "source": getattr(identity, "source", None),
                "requested_ref": getattr(identity, "requested_ref", None),
                "resolved_revision": getattr(identity, "resolved_revision", None),
                "scope": getattr(identity, "scope", None),
            }

            return ResultOnlyMapping(
                {
                    "role": role,
                    "family": family.replace(".", "/"),
                    "project": project,
                    "runtime": runtime,
                    "operations": sorted(available),
                }
            )

        values = [str(part).strip() for part in parts]
        operation = None
        canonical = None
        arguments = ()
        for size in range(len(values), 0, -1):
            suffix = ".".join(
                value.replace(" ", ".")
                for value in values[:size]
                if value
            )
            candidate = f"{family}.{suffix}"
            resolved = self.ops.resolve(candidate)
            if resolved is None:
                continue
            canonical = candidate
            operation = resolved
            arguments = tuple(parts[size:])
            break

        if operation is None:
            requested = " ".join(values)
            authority = self.authorization
            if authority is not None and authority.kind is not None:
                from .authorization import AuthorizationError

                candidate = f"{family}." + ".".join(
                    value.replace(" ", ".") for value in values if value
                )
                raise AuthorizationError(
                    f"Operation is not authorized: {candidate}"
                )
            raise LookupError(
                f"Role {role!r} does not expose node operation {requested!r}"
            )

        self.authorize_operation(canonical, args=arguments)
        with self.invocation_authority(operation):
            return operation(*arguments)

    def add_operation_root(self, path):
        """Add one local, request-scoped operation root ahead of sampler fallback."""
        from pathlib import Path
        from .sampler import expand_root

        root = Path(path).expanduser().resolve()
        if not root.is_dir():
            raise ValueError(f"Operation root is not a directory: {root}")
        name = f"root:{root}"
        if any(route.name == name for route in self.operation_routes.routes):
            return root

        def expand(runtime, tokens, *, _root=root, _name=name):
            return expand_root(runtime, tokens, _root, route_name=_name)

        self.operation_routes.register(name, expand, before="sampler")
        return root

    @property
    def last(self):
        """Return the raw result of the most recently completed operation."""
        return self.results.last

    def next(self, subject=None, default=...):
        """Advance an iterator result without publishing a new operation result."""
        target = self.last if subject is None else self.results[subject]
        if default is ...:
            return next(target)
        return next(target, default)

    def __next__(self):
        """Advance the current iterator result."""
        return self.next()

    @property
    def _authorization_stack(self):
        """Return the execution-local external authorization stack."""
        return self._authorization_stack_var.get()

    @property
    def authorization(self):
        """Return the active external authorization context, if any."""
        stack = self._authorization_stack
        return stack[-1] if stack else None

    @contextmanager
    def authorized(
        self,
        *,
        operations=(),
        environment=None,
        context=None,
        kind=None,
        principal=None,
        client_id=None,
        scopes=(),
    ):
        """Constrain one external request using request-local semantic state."""
        from .authorization import Authorization

        authority = Authorization.create(
            operations=operations,
            environment=environment,
            kind=kind,
            principal=principal,
            client_id=client_id,
            scopes=scopes,
        )
        outermost = self.authorization is None
        scope = (
            self.request_scope(context=context)
            if outermost and not self.in_request
            else nullcontext()
        )
        with scope:
            stack = self._authorization_stack
            token = self._authorization_stack_var.set((*stack, authority))
            try:
                yield authority
            finally:
                self._authorization_stack_var.reset(token)

    @property
    def _capability_depth(self):
        """Return the execution-local trusted-capability nesting depth."""
        return self._capability_depth_var.get()

    @contextmanager
    def trusted_capability(self):
        """Temporarily execute trusted implementation details under recipe authority."""
        token = self._capability_depth_var.set(self._capability_depth + 1)
        try:
            yield
        finally:
            self._capability_depth_var.reset(token)

    @contextmanager
    def attenuated_scope(self, name):
        """Temporarily narrow the active authority to one visible named scope."""
        if name in (None, ""):
            yield self.authorization
            return

        from .authorization import AuthorizationError, attenuate
        from .security.scopes import ScopeRegistry

        current = self.authorization
        requested = str(name).strip()
        if not requested:
            raise ValueError("scope name must be a non-empty string")

        if current is not None:
            can_inspect_scopes = (
                "__all__" in current.operations
                or "security.scope.show" in current.operations
            )
            if requested not in current.scopes and not can_inspect_scopes:
                raise AuthorizationError(
                    f"Security scope is not available to current caller: {requested}"
                )

        scope = ScopeRegistry(self.security_path).require(requested, readonly=True)
        narrowed = attenuate(current, scope)
        stack = self._authorization_stack
        token = self._authorization_stack_var.set((*stack, narrowed))
        try:
            yield narrowed
        finally:
            self._authorization_stack_var.reset(token)

    @contextmanager
    def external_authority(self):
        """Re-enter the active caller authority from trusted implementation code."""
        from .authorization import AuthorizationError

        if self.authorization is None:
            raise AuthorizationError(
                "External Gateway execution requires an authorization context"
            )
        token = self._capability_depth_var.set(0)
        try:
            yield self.authorization
        finally:
            self._capability_depth_var.reset(token)

    def authorize_operation(self, operation, args=(), kwargs=None):
        """Authorize one canonical operation immediately before invocation."""
        authority = self.authorization
        if authority is None or self._capability_depth:
            return
        if operation in {"security.whoami", "security.scope.current"}:
            return
        authority.authorize_operation(operation)
        if operation in {"env", "set.env", "clear.env"}:
            kwargs = {} if kwargs is None else kwargs
            name = args[0] if args else kwargs.get("name")
            if name is not None:
                authority.authorize_environment(str(name))

    def authorize_recipe_path(self, path):
        """Reject direct recipe-path execution under external constrained authority."""
        if self.authorization is None or self._capability_depth:
            return
        from .authorization import AuthorizationError

        raise AuthorizationError(
            "Direct recipe paths are not authorized; invoke an authorized recipe operation"
        )

    @property
    def mutation_policy(self):
        """Return the active trusted mutation policy, or MUTATE_UNSET."""
        return self._mutation_policy_var.get()

    @property
    def mutation_allowed(self):
        """Return whether the active execution may intentionally mutate state."""
        return self.mutation_policy is not False

    @contextmanager
    def mutation_scope(self, *, mutate=MUTATE_UNSET):
        """Apply a trusted mutation policy to this execution and nested calls.

        An outer False policy is a monotonic ceiling: nested execution cannot
        re-enable mutation. Other values are propagated to compatible
        callables, while MUTATE_UNSET preserves the inherited/default policy.
        """
        current = self.mutation_policy
        if current is False:
            policy = False
        elif mutate is MUTATE_UNSET:
            policy = current
        else:
            policy = mutate
        token = self._mutation_policy_var.set(policy)
        try:
            yield policy
        finally:
            self._mutation_policy_var.reset(token)

    @contextmanager
    def observational_state_scope(self):
        """Restore Gway-owned runtime bookkeeping after observational execution."""
        context = dict(self.context)
        result_map = dict(self.results.maps[0])
        result_history = list(self.results.history)
        execution = self.execution
        previous_execution = self.previous_execution
        try:
            yield
        finally:
            self.context.clear()
            self.context.update(context)
            self.results.maps[0].clear()
            self.results.maps[0].update(result_map)
            self.results.history[:] = result_history
            self.execution = execution
            self.previous_execution = previous_execution

    @contextmanager
    def invocation_authority(self, operation):
        """Encapsulate internals of an already-authorized trusted recipe operation."""
        if (
            self.authorization is not None
            and not self._capability_depth
            and getattr(operation, "__gway_source_kind__", None) == "recipe"
        ):
            with self.trusted_capability():
                yield
            return
        yield

    def filter_operation_result(self, operation, result):
        """Filter sensitive operation results under constrained execution."""
        authority = self.authorization
        if authority is None or self._capability_depth:
            return result
        if operation == "envs":
            return authority.filter_environment(result)
        return result

    def _environment_value(self, name):
        """Resolve one environment value through the authorized env built-in."""
        name = str(name)
        self.authorize_operation("env", args=(name, None))
        operation = self.ops.resolve("env")
        if operation is None:
            raise KeyError(name)
        builtin = getattr(operation, "__wrapped__", operation)
        value = builtin(name, None)
        if value is None:
            raise KeyError(name)
        return value

    def _environment_names(self):
        """Return only environment names visible to the active authority."""
        authority = self.authorization
        if authority is None or self._capability_depth:
            return self.environment.names()
        allowed = authority.environment
        if allowed is None:
            return ()
        if "__all__" in allowed:
            return self.environment.names()
        return tuple(name for name in allowed if name in self.environment)

    def execute(self, command, *args, mutate=MUTATE_UNSET, **kwargs):
        """Execute a GWAY command under a trusted mutation policy."""
        from .dispatch import dispatch

        outermost = self.execution_depth == 0
        observational = self.mutation_policy is not False and mutate is False
        with self.mutation_scope(mutate=mutate):
            if observational:
                with self.observational_state_scope():
                    result = dispatch(self, command, *args, **kwargs)
                    execution = self.execution
            else:
                result = dispatch(self, command, *args, **kwargs)
                execution = self.execution
        if outermost and execution is not None:
            return execution.present(result)
        return result

    def execute_authenticated(
        self,
        bearer,
        command,
        *,
        resource=None,
        mutate=MUTATE_UNSET,
    ):
        """Authenticate one bearer and execute under its current authority."""
        from .security.authentication import authenticate_bearer

        self.converge_security_scopes()
        identity = authenticate_bearer(
            bearer,
            resource=resource,
            path=self.security_path,
        )
        with self.request_scope():
            with self.authorized(
                operations=identity.authority.operations,
                environment=identity.authority.environment,
                kind=identity.kind,
                principal=identity.principal,
                client_id=identity.client_id,
                scopes=identity.scopes,
            ):
                with self.external_authority():
                    return self.execute(command, mutate=mutate)

    def __call__(self, command, *args, **kwargs):
        """Execute a GWAY command while preserving inherited mutation policy."""
        from .dispatch import dispatch

        outermost = self.execution_depth == 0
        with self.mutation_scope():
            result = dispatch(self, command, *args, **kwargs)
        if outermost and self.execution is not None:
            return self.execution.present(result)
        return result

    def chain(self, command, *args, **kwargs):
        """Create a scoped manual pipeline rooted in an initial command."""
        from .chain import Chain

        return Chain(self, command, args=args, kwargs=kwargs)

    def ingest(self, source, **kwargs):
        """Ingest a Python source, qualified name, or filesystem source."""
        from .ingestion import ingest

        return ingest(self, source, **kwargs)

    def ingest_path(self, path, **kwargs):
        """Ingest a filesystem source through path-based routing."""
        from .ingestion import ingest_path

        return ingest_path(self, path, **kwargs)

    def wrap(self, func_name, func_obj, *, op=None, sub=None, receiver=None, resolver=None):
        """Normalize a Python callable to GWAY context and result conventions."""
        if not callable(func_obj):
            raise TypeError(f"{func_name!r} is not callable")

        subject = self.subject(func_name) if op is None else sub

        def wrapped(*args, **kwargs):
            current = resolver() if callable(resolver) else func_obj
            if not callable(current):
                raise TypeError(f"{func_name!r} resolved to a non-callable target")
            mutation_policy = self.mutation_policy
            supports_mutation_policy = supports_no_mutate(current)
            declared_non_mutating = getattr(wrapped, "__gway_mutates__", True) is False
            if (
                mutation_policy is False
                and not supports_mutation_policy
                and not declared_non_mutating
            ):
                raise MutationError(
                    f"{func_name!r} does not support non-mutating execution"
                )
            if mutation_policy is not MUTATE_UNSET and supports_mutation_policy:
                kwargs = dict(kwargs)
                kwargs["mutate"] = mutation_policy
            call = complete_arguments(
                self,
                subject,
                current,
                args=args,
                kwargs=kwargs,
                receiver=receiver,
            )
            result = invoke(
                self,
                func_name,
                current,
                args=call.args,
                kwargs=call.kwargs,
            )
            result = self.filter_operation_result(func_name, result)
            return publish(self, subject, result)

        wrapped.__name__ = getattr(func_obj, "__name__", func_name)
        wrapped.__doc__ = getattr(func_obj, "__doc__", None)
        wrapped.__wrapped__ = func_obj
        if callable(resolver):
            wrapped.__gway_callable_resolver__ = resolver
        signature = public_signature(func_obj, receiver=receiver is not None)
        if signature is not None:
            wrapped.__signature__ = signature
        wrapped.mutates = mutates(func_obj)
        wrapped.__gway_mutates__ = wrapped.mutates
        wrapped.__gway_supports_no_mutate__ = supports_no_mutate(func_obj)
        wrapped.__gway_operation__ = op or func_name
        wrapped.__gway_subject__ = subject
        wrapped.__gway_receiver__ = receiver
        self.ops.register(func_name, wrapped, op=op, sub=sub)
        self._register_local_node_alias(func_name, wrapped)
        self.launchables.operation(
            func_name,
            metadata={
                "operation": op or func_name,
                "subject": subject,
            },
        )
        return wrapped

    def __setattr__(self, name, value):
        object.__setattr__(self, name, value)
        if name.startswith("_") or name in {"ops", "subs"}:
            return
        ops = self.__dict__.get("ops")
        if (
            ops is not None
            and callable(value)
            and getattr(value, "__gway_operation__", None) is not None
        ):
            ops.register_alias(name, value)

    def _register_local_node_alias(self, canonical, operation):
        """Expose active-role node operations through semantic role spelling."""
        parts = tuple(
            part for part in str(canonical).replace(" ", ".").split(".") if part
        )
        if len(parts) < 3 or parts[0] != "node":
            return

        role = self.find_value("role", include_environment=False)
        if role is None:
            return
        role = str(role).strip()
        if not role or parts[1].casefold() != role.casefold():
            return

        alias = ".".join((role, *parts[2:]))
        existing = self.ops.resolve(alias)
        if existing is not None and existing is not operation:
            return
        self.ops.register_alias(alias, operation)

    @staticmethod
    def subject(func_name: str):
        """Return the semantic subject derived by the operation registry."""
        return split_operation(func_name)[1]


gw = Gateway()
