"""Request-local runtime state for Gateway execution."""

from collections.abc import Mapping
from contextvars import ContextVar
from dataclasses import dataclass, field

from .mutation import MUTATE_UNSET
from .structs import Results


@dataclass
class RequestState:
    """Semantic and execution state owned by one logical Gateway request."""

    context: dict = field(default_factory=dict)
    results: Results = field(default_factory=Results)
    execution: object = None
    previous_execution: object = None
    execution_depth: int = 0
    execution_suspension: object = None

    def __post_init__(self):
        suffix = id(self)
        self.authorization_stack = ContextVar(
            f"gway_authorization_stack_{suffix}",
            default=(),
        )
        self.capability_depth = ContextVar(
            f"gway_capability_depth_{suffix}",
            default=0,
        )
        self.mutation_policy = ContextVar(
            f"gway_mutation_policy_{suffix}",
            default=MUTATE_UNSET,
        )
        self.semantic_topics = ContextVar(
            f"gway_semantic_topics_{suffix}",
            default=(),
        )


class RequestMapping(Mapping):
    """Stable resolver view over a mapping selected by the active request."""

    def __init__(self, runtime, attribute):
        self.runtime = runtime
        self.attribute = attribute

    @property
    def target(self):
        return getattr(self.runtime, self.attribute)

    def __getitem__(self, key):
        return self.target[key]

    def __iter__(self):
        return iter(self.target)

    def __len__(self):
        return len(self.target)
