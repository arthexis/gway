"""Structured documentation metadata for Python callables."""

import inspect
import re
from dataclasses import dataclass


_ARGS_HEADER = re.compile(r"^\s*(?:Args|Arguments|Parameters):\s*$")
_PARAMETER = re.compile(r"^\s{2,}([*]{0,2}[A-Za-z_]\w*)(?:\s*\([^)]*\))?\s*:\s*(.*)$")


@dataclass(frozen=True)
class ParameterDocumentation:
    """Mechanical and descriptive information for one callable parameter."""

    name: str
    kind: inspect._ParameterKind
    required: bool
    default: object
    annotation: object
    description: str | None = None


@dataclass(frozen=True)
class CallableDocumentation:
    """Structured documentation extracted from a raw or Gway-bound callable."""

    callable: object
    target: object
    summary: str
    docstring: str
    signature: inspect.Signature | None
    parameters: tuple[ParameterDocumentation, ...]
    source: object = None
    source_kind: str | None = None
    path: tuple[str, ...] | None = None
    metadata: object = None
    operation: str | None = None
    subject: str | None = None

    def parameter(self, name):
        """Return documentation for one parameter by name, if present."""
        return next(
            (parameter for parameter in self.parameters if parameter.name == name),
            None,
        )


def _parameter_descriptions(docstring):
    """Parse optional Args/Arguments/Parameters entries from a docstring."""
    if not docstring:
        return {}

    lines = docstring.splitlines()
    descriptions = {}
    index = 0

    while index < len(lines):
        if not _ARGS_HEADER.match(lines[index]):
            index += 1
            continue

        index += 1
        current = None
        pieces = []
        while index < len(lines):
            line = lines[index]
            match = _PARAMETER.match(line)
            if match:
                if current is not None:
                    descriptions[current] = " ".join(pieces).strip()
                current = match.group(1).lstrip("*")
                pieces = [match.group(2).strip()] if match.group(2).strip() else []
                index += 1
                continue

            if current is not None and (not line.strip() or line[:1].isspace()):
                if line.strip():
                    pieces.append(line.strip())
                index += 1
                continue
            break

        if current is not None:
            descriptions[current] = " ".join(pieces).strip()
        if descriptions:
            break

    return descriptions


def _narrative_docstring(docstring):
    """Return docstring prose without structured parameter sections."""
    if not docstring:
        return ""

    lines = docstring.splitlines()
    kept = []
    index = 0
    while index < len(lines):
        if not _ARGS_HEADER.match(lines[index]):
            kept.append(lines[index])
            index += 1
            continue

        index += 1
        while index < len(lines):
            line = lines[index]
            if line.strip() and not line[:1].isspace():
                break
            index += 1

    return "\n".join(kept).strip()


def _signature(callable_obj):
    """Return an inspect signature when the callable exposes one."""
    try:
        return inspect.signature(callable_obj)
    except (TypeError, ValueError):
        return None


def describe(callable_obj):
    """Return structured help metadata for a Python callable.

    The function signature is authoritative for parameter mechanics. Optional
    parameter prose is read from conventional Args, Arguments, or Parameters
    docstring sections when present.
    """
    if not callable(callable_obj):
        raise TypeError("documentation target must be callable")

    target = getattr(callable_obj, "__wrapped__", callable_obj)
    docstring = inspect.getdoc(target) or inspect.getdoc(callable_obj) or ""
    summary = docstring.splitlines()[0].strip() if docstring else ""
    descriptions = _parameter_descriptions(docstring)
    signature = _signature(callable_obj)

    parameters = ()
    if signature is not None:
        parameters = tuple(
            ParameterDocumentation(
                name=parameter.name,
                kind=parameter.kind,
                required=(
                    parameter.default is inspect.Parameter.empty
                    and parameter.kind
                    not in (
                        inspect.Parameter.VAR_POSITIONAL,
                        inspect.Parameter.VAR_KEYWORD,
                    )
                ),
                default=parameter.default,
                annotation=parameter.annotation,
                description=descriptions.get(parameter.name) or None,
            )
            for parameter in signature.parameters.values()
        )

    path = getattr(callable_obj, "__gway_path__", None)
    if path is not None:
        path = tuple(path)

    return CallableDocumentation(
        callable=callable_obj,
        target=target,
        summary=summary,
        docstring=docstring,
        signature=signature,
        parameters=parameters,
        source=getattr(callable_obj, "__gway_source__", None),
        source_kind=getattr(callable_obj, "__gway_source_kind__", None),
        path=path,
        metadata=getattr(callable_obj, "__gway_metadata__", None),
        operation=getattr(callable_obj, "__gway_operation__", None),
        subject=getattr(callable_obj, "__gway_subject__", None),
    )


def _display_name(documentation):
    """Return the best human-facing operation name for documentation."""
    if documentation.path:
        return " ".join(documentation.path)
    operation = documentation.operation
    subject = documentation.subject
    if operation and subject:
        return f"{operation} {subject}"
    if operation:
        return operation
    return getattr(
        documentation.target, "__name__", type(documentation.target).__name__
    )


def _annotation_name(annotation):
    """Return a compact readable annotation name."""
    if annotation is inspect.Parameter.empty:
        return None
    if isinstance(annotation, type):
        return annotation.__name__
    return str(annotation).replace("typing.", "")


def _default_text(value):
    """Return a compact representation for one parameter default."""
    if value is inspect.Parameter.empty:
        return None
    return repr(value)


def render(callable_obj, *, verbose=False):
    """Render compact or verbose human-facing help for one callable."""
    documentation = describe(callable_obj)
    name = _display_name(documentation)
    signature = (
        str(documentation.signature) if documentation.signature is not None else ""
    )
    header = f"{name}{signature}"

    if not verbose:
        if documentation.summary:
            return f"{header}\n{documentation.summary}"
        return header

    lines = [header]
    narrative = _narrative_docstring(documentation.docstring)
    if narrative:
        lines.extend(["", narrative])

    if documentation.parameters:
        lines.extend(["", "Parameters:"])
        for parameter in documentation.parameters:
            lines.append(f"  {parameter.name}")
            if parameter.description:
                lines.append(f"    {parameter.description}")

            annotation = _annotation_name(parameter.annotation)
            if annotation:
                lines.append(f"    Type: {annotation}")

            if parameter.required:
                lines.append("    Required")
            else:
                default = _default_text(parameter.default)
                if default is not None:
                    lines.append(f"    Default: {default}")

    return "\n".join(lines)


def render_parameter(callable_obj, name):
    """Render verbose help for one parameter of a callable."""
    documentation = describe(callable_obj)
    parameter = documentation.parameter(name)
    if parameter is None:
        return ""

    lines = [parameter.name]
    if parameter.description:
        lines.append(f"  {parameter.description}")

    annotation = _annotation_name(parameter.annotation)
    if annotation:
        lines.append(f"  Type: {annotation}")

    if parameter.required:
        lines.append("  Required")
    else:
        default = _default_text(parameter.default)
        if default is not None:
            lines.append(f"  Default: {default}")

    return "\n".join(lines)
