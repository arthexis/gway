"""Task-oriented guidance derived from explicit project declarations."""

from dataclasses import dataclass


@dataclass(frozen=True)
class GuideMatch:
    """One explicit guide recommendation plus its deterministic match score."""

    score: float
    task: str
    command: str
    reason: str
    source: str | None


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


def explicit_matches(task, rules, *, limit=5, cutoff=0.5):
    """Rank explicit project guidance against one requested task."""
    matches = []
    for index, rule in enumerate(rules or ()):
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
                index,
                GuideMatch(
                    score=best[0],
                    task=best[1],
                    command=rule["command"],
                    reason=rule["reason"],
                    source=rule.get("source"),
                ),
            )
        )

    matches.sort(key=lambda item: (item[0], item[1]))
    return tuple(item[2] for item in matches[:limit])


def guide(task, rules):
    """Return structured task guidance from explicit project declarations."""
    task = str(task).strip()
    if not task:
        raise TypeError("guide requires a task")

    recommendations = []
    for match in explicit_matches(task, rules):
        recommendations.append(
            {
                "kind": "gway",
                "command": match.command,
                "reason": match.reason,
                "source": match.source,
                "matched_task": match.task,
            }
        )
    return {
        "task": task,
        "recommendations": recommendations,
        "external": [],
    }
