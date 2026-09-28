"""Static public contracts for first-class recipe operations."""

import ast
import inspect
from pathlib import Path


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
    """Return signature/doc/source for one recipe-backed first-class operation."""
    companion = recipe_companion(recipe)
    if companion is not None:
        contract = main_contract(companion)
        if contract is not None:
            signature, doc = contract
            return signature, doc, companion
    return generic_recipe_signature(), None, companion
