"""Replayable semantic execution records for Gway dispatch."""

from dataclasses import dataclass, field


_UNSET = object()


@dataclass
class Stage:
    """One completed semantic dispatch stage."""

    tokens: tuple
    operation: str
    arguments: tuple
    incoming: object
    outgoing: object
    statement: int
    has_incoming: bool = False
    kind: str = "operation"

    def replay(self, runtime, *, pipeline=_UNSET):
        """Re-dispatch this stage from its semantic tokens."""
        if self.kind == "recipe":
            from .recipes import execute_recipe, parse_recipe_context, recipe_path

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

    def append(self, stage):
        self.stages.append(stage)
        return stage

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

    def replay(self, runtime):
        """Replay all statements without pipeline transfer between them."""
        result = None
        for statement in self.statements:
            result = statement.replay(runtime)
        return result
