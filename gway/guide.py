"""Task-oriented guidance derived from explicit project declarations."""

from dataclasses import dataclass


@dataclass(frozen=True)
class GuideMatch:
    """One explicit guide recommendation plus its deterministic match score."""

    score: float
    task: str
    command: str | None
    reason: str
    source: str | None
    roles: tuple[str, ...] = ()
    use: str = "gway"
    capability: str | None = None


def _words(value):
    return tuple(
        word.casefold()
        for word in str(value).replace("-", " ").replace("_", " ").split()
        if word
    )


def _score(query, candidate):
    query_words = _words(query)
    candidate_words = _words(candidate)
    if not query_words or not candidate_words:
        return 0.0
    if query_words == candidate_words:
        return 1.0

    query_set = set(query_words)
    candidate_set = set(candidate_words)
    if candidate_set <= query_set or query_set <= candidate_set:
        return 0.9

    overlap = len(query_set & candidate_set)
    union = len(query_set | candidate_set)
    return overlap / union if union else 0.0


def explicit_matches(task, rules, *, role=None, limit=5, cutoff=0.5):
    """Rank explicit project guidance against one requested task and node role."""
    matches = []
    active_role = str(role).strip().casefold() if role is not None else None
    for index, rule in enumerate(rules or ()):
        roles = tuple(rule.get("roles", ()))
        if roles:
            allowed = {value.casefold() for value in roles}
            if active_role is None or active_role not in allowed:
                continue
        best = None
        for declared_task in rule["tasks"]:
            score = _score(task, declared_task)
            if best is None or score > best[0]:
                best = (score, declared_task)
        if best is None or best[0] < cutoff:
            continue
        matches.append(
            (
                -best[0],
                0 if roles else 1,
                index,
                GuideMatch(
                    score=best[0],
                    task=best[1],
                    command=rule.get("command"),
                    reason=rule["reason"],
                    source=rule.get("source"),
                    roles=roles,
                    use=rule.get("use", "gway"),
                    capability=rule.get("capability"),
                ),
            )
        )

    matches.sort(key=lambda item: (item[0], item[1], item[2]))
    return tuple(item[3] for item in matches[:limit])


def operation_matches(task, records, *, authorization=None, limit=5, cutoff=0.34):
    """Rank live registered operation metadata below explicit project guidance."""
    from .documentation import describe

    matches = []
    allowed = None if authorization is None else authorization.operations
    for index, record in enumerate(records or ()):
        if allowed is not None and record.name not in allowed:
            continue

        command = record.name.replace(".", " ").replace("_", " ")
        documentation = describe(record.callable)
        summary = documentation.summary or ""
        score = max(
            _score(task, command),
            _score(task, f"{command} {summary}") if summary else 0.0,
        )
        if score < cutoff:
            continue
        matches.append(
            (
                -score,
                index,
                {
                    "kind": "gway",
                    "command": command,
                    "reason": summary or "Registered GWAY operation.",
                    "source": documentation.source_kind or "runtime",
                    "operation": record.name,
                    "mutates": bool(getattr(record.callable, "mutates", True)),
                },
            )
        )

    matches.sort(key=lambda item: (item[0], item[1]))
    return tuple(item[2] for item in matches[:limit])


def docstring_matches(
    task,
    records,
    *,
    authorization=None,
    exclude_operations=(),
    limit=3,
    cutoff=0.2,
):
    """Rank richer operation docstrings after operations and recipes."""
    from .documentation import describe

    excluded = set(exclude_operations or ())
    allowed = None if authorization is None else authorization.operations
    matches = []
    for index, record in enumerate(records or ()):
        if record.name in excluded:
            continue
        if allowed is not None and record.name not in allowed:
            continue

        documentation = describe(record.callable)
        docstring = documentation.docstring or ""
        if not docstring:
            continue
        score = _score(task, docstring)
        if score < cutoff:
            continue

        excerpt = " ".join(docstring.split())
        if len(excerpt) > 240:
            excerpt = excerpt[:237].rstrip() + "..."
        command = record.name.replace(".", " ").replace("_", " ")
        matches.append(
            (
                -score,
                index,
                {
                    "kind": "gway",
                    "command": command,
                    "reason": excerpt,
                    "source": "docstring",
                    "operation": record.name,
                    "mutates": bool(getattr(record.callable, "mutates", True)),
                },
            )
        )

    matches.sort(key=lambda item: (item[0], item[1]))
    return tuple(item[2] for item in matches[:limit])


def recipe_matches(task, recipes, *, authorization=None, limit=5, cutoff=0.34):
    """Rank maintained sampler recipes behind explicit and operation guidance."""
    if authorization is not None and "recipe" not in authorization.operations:
        return ()

    matches = []
    for index, name in enumerate(recipes or ()):
        display = str(name).replace("/", " ").replace("-", " ").replace("_", " ")
        score = _score(task, display)
        if score < cutoff:
            continue
        matches.append(
            (
                -score,
                index,
                {
                    "kind": "recipe",
                    "command": f"recipe {name}",
                    "reason": f"Maintained sampler recipe: {name}.",
                    "source": "sampler",
                    "recipe": name,
                    "mutates": True,
                },
            )
        )

    matches.sort(key=lambda item: (item[0], item[1]))
    return tuple(item[2] for item in matches[:limit])


def document_matches(task, documents, *, limit=3, cutoff=0.2):
    """Rank explicitly selected documentation as the final bounded fallback."""
    matches = []
    for index, document in enumerate(documents or ()):
        heading = document.get("heading") or ""
        text = document.get("text") or ""
        candidate = f"{heading} {text}".strip()
        score = _score(task, candidate)
        if score < cutoff:
            continue
        excerpt = " ".join(text.split())
        if len(excerpt) > 240:
            excerpt = excerpt[:237].rstrip() + "..."
        matches.append(
            (
                -score,
                index,
                {
                    "kind": "documentation",
                    "source": document.get("source"),
                    "section": heading or None,
                    "reason": excerpt or heading or "Selected project documentation.",
                },
            )
        )
    matches.sort(key=lambda item: (item[0], item[1]))
    return tuple(item[2] for item in matches[:limit])


def guide(
    task,
    rules,
    *,
    role=None,
    operations=(),
    recipes=(),
    documents=(),
    authorization=None,
):
    """Return structured task guidance for the active Gateway."""
    task = str(task).strip()
    if not task:
        raise TypeError("guide requires a task")

    recommendations = []
    external = []
    for match in explicit_matches(task, rules, role=role):
        if match.use == "external":
            recommendation = {
                "capability": match.capability,
                "reason": match.reason,
                "source": match.source,
                "matched_task": match.task,
            }
            if match.roles:
                recommendation["roles"] = list(match.roles)
            external.append(recommendation)
            continue

        recommendation = {
            "kind": "gway",
            "command": match.command,
            "reason": match.reason,
            "source": match.source,
            "matched_task": match.task,
        }
        if match.roles:
            recommendation["roles"] = list(match.roles)
        recommendations.append(recommendation)

    explicit_commands = {item["command"] for item in recommendations}
    for recommendation in operation_matches(
        task,
        operations,
        authorization=authorization,
    ):
        if recommendation["command"] in explicit_commands:
            continue
        recommendations.append(recommendation)

    known_commands = {item["command"] for item in recommendations}
    for recommendation in recipe_matches(
        task,
        recipes,
        authorization=authorization,
    ):
        if recommendation["command"] in known_commands:
            continue
        recommendations.append(recommendation)

    seen_operations = {
        item.get("operation")
        for item in recommendations
        if item.get("operation") is not None
    }
    for recommendation in docstring_matches(
        task,
        operations,
        authorization=authorization,
        exclude_operations=seen_operations,
    ):
        recommendations.append(recommendation)

    for recommendation in document_matches(task, documents):
        recommendations.append(recommendation)

    from .publication import ResultOnlyMapping

    result = {
        "task": task,
        "recommendations": recommendations,
        "external": external,
    }
    if role is not None:
        result["role"] = role
    return ResultOnlyMapping(result)
