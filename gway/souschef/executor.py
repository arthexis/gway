"""Bounded recipe execution for Sous Chef."""

from dataclasses import dataclass
import multiprocessing
import os
import signal
import traceback


@dataclass(frozen=True)
class RecipeFailure:
    """Serializable description of a recipe execution failure."""

    type: str
    message: str
    traceback: str


class RecipeExecutionError(RuntimeError):
    """Raised when a Sous Chef recipe fails in its isolated worker."""

    def __init__(self, failure):
        self.failure = failure
        super().__init__(f"{failure.type}: {failure.message}")


class RecipeTimeoutError(TimeoutError):
    """Raised when a Sous Chef recipe exceeds its configured timeout."""

    def __init__(self, job):
        self.job = job
        super().__init__(
            f"Sous Chef job {job.project!r}/{job.name!r} exceeded "
            f"its {job.timeout:g}s timeout"
        )


def _worker(connection, recipe, root):
    """Execute one recipe through the canonical Gway evaluator."""
    try:
        if os.name != "nt":
            os.setsid()
        os.chdir(root)

        from gway import Gateway
        from gway.recipes import execute_recipe

        runtime = Gateway()
        _, value = execute_recipe(runtime, recipe)
        try:
            connection.send(("ok", value))
        except Exception:
            connection.send(("ok_repr", repr(value)))
    except BaseException as exc:
        failure = RecipeFailure(
            type=type(exc).__name__,
            message=str(exc),
            traceback="".join(
                traceback.format_exception(type(exc), exc, exc.__traceback__)
            ),
        )
        try:
            connection.send(("error", failure))
        except Exception:
            pass
    finally:
        connection.close()


class RecipeExecutor:
    """Execute Sous Chef jobs in isolated, timeout-bounded processes."""

    def __init__(self, *, context=None):
        self.context = context or multiprocessing.get_context("spawn")

    @staticmethod
    def _terminate(process):
        if not process.is_alive():
            process.join()
            return

        if os.name != "nt":
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            process.join(timeout=1)
            if process.is_alive():
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
        else:
            process.terminate()

        process.join(timeout=1)
        if process.is_alive():
            process.kill()
            process.join(timeout=1)

    def __call__(self, job):
        """Execute one job through execute_recipe() within its timeout."""
        parent, child = self.context.Pipe(duplex=False)
        process = self.context.Process(
            target=_worker,
            args=(child, str(job.recipe), str(job.root)),
            name=f"sous-chef:{job.project}/{job.name}",
        )
        process.start()
        child.close()

        process.join(timeout=job.timeout)
        if process.is_alive():
            self._terminate(process)
            parent.close()
            raise RecipeTimeoutError(job)

        message = parent.recv() if parent.poll() else None
        parent.close()

        if message is None:
            raise RecipeExecutionError(
                RecipeFailure(
                    type="WorkerExit",
                    message=f"recipe worker exited with code {process.exitcode}",
                    traceback="",
                )
            )

        kind, value = message
        if kind == "error":
            raise RecipeExecutionError(value)
        return value
