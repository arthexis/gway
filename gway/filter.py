"""Non-mutating structured pipeline filtering."""

from collections.abc import Mapping, Sequence
from .semantic import resolve_mapping_key


def filter(items, pattern=None, *, field=None, contains=None, gt=None, lt=None, mutate=False, **criteria):
    """Return matching records in their original order and structure.

    Args:
        pattern: Text to find in each item, or in the selected field.
        field: Mapping field selected for text or numeric comparisons.
        contains: Text to find in the selected field; requires field.
        gt: Exclusive numeric lower bound; requires field.
        lt: Exclusive numeric upper bound; requires field.
        criteria: Mapping fields to match by equality; all criteria must match.
    """
    if not isinstance(items, Sequence) or isinstance(items, (str, bytes, bytearray)):
        raise TypeError("filter requires a sequence of items")
    if any(value is not None for value in (contains, gt, lt)) and field is None:
        raise ValueError("contains, gt, and lt require --field")
    bounds = {name: float(value) for name, value in (("gt", gt), ("lt", lt)) if value is not None}

    def get(item, key):
        if not isinstance(item, Mapping):
            raise TypeError("Field filtering requires mapping records")
        return item[resolve_mapping_key(item, key)]

    result = []
    for item in items:
        # Validate every requested field even when another predicate does not match.
        values = [(get(item, key), expected) for key, expected in criteria.items()]
        value = get(item, field) if field is not None else item
        matches = all(actual == expected for actual, expected in values)
        for text in (pattern, contains):
            if text is not None:
                matches = matches and str(text) in str(value)
        if bounds:
            if isinstance(value, bool):
                raise TypeError("Numeric filtering requires numeric field values")
            number = float(value)
            matches = matches and ("gt" not in bounds or number > bounds["gt"])
            matches = matches and ("lt" not in bounds or number < bounds["lt"])
        if matches:
            result.append(item)
    return result

