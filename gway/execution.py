"""Replayable semantic execution records for Gway dispatch."""

from dataclasses import dataclass, field


_UNSET = object()


@dataclass(frozen=True)
class PresentationResult:
    """One observable statement result at an invocation boundary."""

    subject: str | None
    result: object

    def as_record(self):
        return {"subject": self.subject, "result": self.result}


class PresentationResults(tuple):
    """Ordered, duplicate-preserving presentation results."""

    def getall(self, subject):
        return tuple(entry.result for entry in self if entry.subject == subject)

    def as_records(self):
        return [entry.as_record() for entry in self]


@dataclass
class Stage:
    """One completed semantic dispatch stage."""

    tokens: tuple
    operation: str
    arguments: tuple
    incoming: object
    outgoing: object
    statement: int
    subject: str | None = None
    published: bool = True
    has_incoming: bool = False
    kind: str = "operation"

    def replay(self, runtime, *, pipeline=_UNSET):
        """Re-dispatch this stage from its semantic tokens."""
        if self.kind == "recipe":
            from .recipe import execute_recipe, parse_recipe_context, recipe_path

            source = self.tokens[0]
            path = recipe_path(runtime, source, allow_bare=True)
            if path is None:
                raise LookupError(f"Unable to resolve recipe: {source}")
            context = parse_recipe_context(self.tokens[1:])
            incoming = self.incoming if pipeline is _UNSET else pipeline
            if pipeline is _UNSET and not self.has_incoming:
                _, result = execute_recipe(runtime, path, context=context)
            else:
                _, result = execute_recipe(
                    runtime,
                    path,
                    context=context,
                    pipeline=incoming,
                )
            return result

        from .dispatch import _MISSING, dispatch_stage

        incoming = self.incoming if pipeline is _UNSET else pipeline
        if pipeline is _UNSET and not self.has_incoming:
            return dispatch_stage(runtime, self.tokens)
        if incoming is _MISSING:
            return dispatch_stage(runtime, self.tokens)
        return dispatch_stage(runtime, self.tokens, pipeline=incoming)


@dataclass
class Statement:
    """An ordered set of pipeline-connected stages."""

    index: int
    stages: list[Stage] = field(default_factory=list)
    _presentation_subject: object = field(default=_UNSET, repr=False)
    _presentation_result: object = field(default=_UNSET, repr=False)

    def append(self, stage):
        self.stages.append(stage)
        self._presentation_subject = _UNSET
        self._presentation_result = _UNSET
        return stage

    def present_as(self, subject, result):
        """Override this statement's observable result for transparent controls."""
        self._presentation_subject = subject
        self._presentation_result = result
        return result

    @property
    def final(self):
        """Return the final recorded stage, if any."""
        return self.stages[-1] if self.stages else None

    @property
    def subject(self):
        """Return the resolved subject of the observable statement result."""
        if self._presentation_result is not _UNSET:
            return None if self._presentation_subject is _UNSET else self._presentation_subject
        final = self.final
        if final is None or not final.published:
            return None
        return final.subject

    @property
    def result(self):
        """Return the observable statement result without semantic reverse lookup."""
        if self._presentation_result is not _UNSET:
            return self._presentation_result
        final = self.final
        if final is None or not final.published:
            return None
        return final.outgoing

    @property
    def published(self):
        """Return whether the statement contributes an observable result."""
        if self._presentation_result is not _UNSET:
            return self._presentation_result is not None
        final = self.final
        return final is not None and final.published

    def replay(self, runtime, *, pipeline=_UNSET):
        """Replay this statement in stage order."""
        if not self.stages:
            return None

        current = pipeline
        result = None
        for index, stage in enumerate(self.stages):
            if index == 0 and current is _UNSET:
                result = stage.replay(runtime)
            else:
                result = stage.replay(runtime, pipeline=current)
            current = result
        return result


@dataclass
class Execution:
    """A replayable semantic record of one dispatched program."""

    statements: list[Statement] = field(default_factory=list)

    def statement(self):
        record = Statement(len(self.statements))
        self.statements.append(record)
        return record

    @property
    def stages(self):
        return [stage for statement in self.statements for stage in statement.stages]

    @property
    def last(self):
        stages = self.stages
        return stages[-1] if stages else None

    @property
    def outputs(self):
        """Return ordered completed statement records for presentation layers."""
        return tuple(statement for statement in self.statements if statement.published)

    @property
    def presentation_results(self):
        """Return ordered semantic results without collapsing duplicate subjects."""
        return PresentationResults(
            PresentationResult(statement.subject, statement.result)
            for statement in self.outputs
        )

    def present(self, fallback=None):
        """Return scalar compatibility output or a multi-result presentation envelope."""
        results = self.presentation_results
        if not results:
            return fallback
        if len(results) == 1:
            return results[0].result
        return {"results": results.as_records()}

    def replay(self, runtime):
        """Replay all statements without pipeline transfer between them."""
        result = None
        for statement in self.statements:
            result = statement.replay(runtime)
        return result
