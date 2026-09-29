"""Static public contracts for first-class recipe operations."""

import ast
import inspect
from pathlib import Path


_HELP_FIELDS = frozenset({"summary", "description", "examples", "notes", "see_also"})


_EMPTY = inspect.Parameter.empty


def _literal(node, *, default=_EMPTY):
    if node is None:
        return default
    try:
        return ast.literal_eval(node)
    except (ValueError, TypeError):
        return None


def _annotation(node):
    if node is None:
        return _EMPTY
    try:
        return ast.unparse(node)
    except Exception:
        return _EMPTY


def _parameter(argument, kind, default=_EMPTY):
    return inspect.Parameter(
        argument.arg,
        kind=kind,
        default=default,
        annotation=_annotation(argument.annotation),
    )


def main_contract(companion):
    """Return the static __main__ signature/docstring from one companion source."""
    path = Path(companion).expanduser().resolve()
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    function = next(
        (
            node
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "__main__"
        ),
        None,
    )
    if function is None:
        return None

    args = function.args
    positional = [*args.posonlyargs, *args.args]
    defaults = [_EMPTY] * (len(positional) - len(args.defaults))
    defaults.extend(_literal(node) for node in args.defaults)

    parameters = []
    posonly_count = len(args.posonlyargs)
    for index, (argument, default) in enumerate(zip(positional, defaults)):
        kind = (
            inspect.Parameter.POSITIONAL_ONLY
            if index < posonly_count
            else inspect.Parameter.POSITIONAL_OR_KEYWORD
        )
        parameters.append(_parameter(argument, kind, default))

    if args.vararg is not None:
        parameters.append(
            _parameter(args.vararg, inspect.Parameter.VAR_POSITIONAL)
        )

    for argument, default_node in zip(args.kwonlyargs, args.kw_defaults):
        parameters.append(
            _parameter(
                argument,
                inspect.Parameter.KEYWORD_ONLY,
                _literal(default_node),
            )
        )

    if args.kwarg is not None:
        parameters.append(
            _parameter(args.kwarg, inspect.Parameter.VAR_KEYWORD)
        )

    signature = inspect.Signature(
        parameters,
        return_annotation=_annotation(function.returns),
    )
    return signature, ast.get_docstring(function)


def recipe_companion(recipe):
    """Return the sibling Python companion for one recipe, if present."""
    recipe = Path(recipe).expanduser().resolve()
    companion = recipe.with_suffix(".py")
    return companion if companion.is_file() else None


def generic_recipe_signature():
    """Return the conservative public contract for a recipe without __main__."""
    return inspect.Signature(
        [
            inspect.Parameter(
                "mutate",
                kind=inspect.Parameter.KEYWORD_ONLY,
                default=True,
            ),
            inspect.Parameter("context", kind=inspect.Parameter.VAR_KEYWORD),
        ]
    )


def recipe_contract(recipe):
    """Return signature/doc/source/help for one recipe-backed first-class operation."""
    companion = recipe_companion(recipe)
    signature = generic_recipe_signature()
    doc = None
    if companion is not None:
        contract = main_contract(companion)
        if contract is not None:
            signature, doc = contract
    help_meta = recipe_help(recipe, companion=companion, main_doc=doc)
    effective_doc = help_meta.get("description") or doc
    return signature, effective_doc, companion, help_meta


def recipe_comment_help(recipe):
    """Return the leading whole-line recipe comment block as documentation."""
    path = Path(recipe).expanduser().resolve()
    lines = []
    started = False
    for raw in path.read_text(encoding="utf-8").splitlines():
        stripped = raw.strip()
        if not stripped:
            if started:
                lines.append("")
            continue
        if not stripped.startswith("#"):
            break
        started = True
        value = stripped[1:]
        if value.startswith(" "):
            value = value[1:]
        lines.append(value.rstrip())
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines).strip()


def _help_function(tree):
    return next(
        (
            node
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "__help__"
        ),
        None,
    )


def _literal_help_return(function):
    if function is None:
        return None
    returns = [
        node.value
        for node in function.body
        if isinstance(node, ast.Return) and node.value is not None
    ]
    if len(returns) != 1:
        return None
    try:
        return ast.literal_eval(returns[0])
    except (ValueError, TypeError):
        return None


def help_contract(companion):
    """Return statically declared __help__ metadata without executing companion code."""
    if companion is None:
        return {}
    path = Path(companion).expanduser().resolve()
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    value = _literal_help_return(_help_function(tree))
    if value is None:
        return {}
    if isinstance(value, str):
        return {"description": value}
    if not isinstance(value, dict):
        raise TypeError("__help__ must return a literal string or mapping")

    general = {}
    topics = {}
    explicit_topics = value.get("topics")
    if explicit_topics is not None:
        if not isinstance(explicit_topics, dict):
            raise TypeError("__help__ topics must be a literal mapping")
        topics.update(explicit_topics)

    for key, item in value.items():
        if key == "topics":
            continue
        if key in _HELP_FIELDS:
            general[key] = item
            continue
        if key is None:
            if not isinstance(item, dict):
                raise TypeError("__help__ None entry must be a mapping")
            general.update(item)
            continue
        topics[str(key)] = item

    for name, item in list(topics.items()):
        if isinstance(item, str):
            topics[name] = {"description": item}
        elif not isinstance(item, dict):
            raise TypeError(f"__help__ topic {name!r} must be a string or mapping")

    return {**general, "topics": topics}


def recipe_help(recipe, *, companion=None, main_doc=None):
    """Merge native recipe comments, __main__ prose, and static __help__ metadata."""
    comments = recipe_comment_help(recipe)
    help_meta = help_contract(companion)
    result = {}
    if comments:
        result["description"] = comments
        result["summary"] = comments.splitlines()[0].strip()
    if main_doc:
        result["description"] = main_doc
        result["summary"] = main_doc.splitlines()[0].strip()
    for field in _HELP_FIELDS:
        if field in help_meta:
            result[field] = help_meta[field]
    result["topics"] = dict(help_meta.get("topics", {}))
    return result
