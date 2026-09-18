# file projects/cast.py

import re
import html
import json
import collections
from typing import Sequence, Mapping

def to_list(obj, flat=False):
    """
    Convert, and optionally flatten, any object into a list with a set of intuitive rules.
    - If `obj` is a string with spaces, commas, colons, or semicolons, split it.
    - If `obj` is a dict or a view (e.g., bottle view dict), return ["key=value", ...].
    - If `obj` is a list or tuple, return it as a list.
    - If `obj` is an iterable, convert to list.
    - Otherwise, return [obj].
    """
    def _flatten(x):
        for item in x:
            if isinstance(item, str) or isinstance(item, bytes):
                yield item
            elif isinstance(item, collections.abc.Mapping):
                for k, v in item.items():
                    yield f"{k}={v}"
            elif isinstance(item, collections.abc.Iterable):
                yield from _flatten(item)
            else:
                yield item

    # Handle string splitting
    if isinstance(obj, str):
        if re.search(r"[ ,;:]", obj):
            result = re.split(r"[ ,;:]+", obj.strip())
            return list(_flatten(result)) if flat else result
        return [obj]

    # Handle mappings (e.g. dicts, views)
    if isinstance(obj, collections.abc.Mapping):
        items = [f"{k}={v}" for k, v in obj.items()]
        return list(_flatten(items)) if flat else items

    # Handle other iterables
    if isinstance(obj, collections.abc.Iterable):
        result = list(obj)
        return list(_flatten(result)) if flat else result

    # Fallback
    return [obj]

def to_html(obj, **kwargs):
    """
    Convert an arbitrary Python object to structured HTML.
    
    Args:
        obj: The object to convert.
        **kwargs: Optional keyword arguments for customization:
            - class_prefix: Prefix for HTML class names.
            - max_depth: Maximum recursion depth.
            - skip_none: Skip None values.
            - pretty: Insert newlines/indentation.
    
    Returns:
        A string of HTML representing the object.
    """
    class_prefix = kwargs.get("class_prefix", "obj")
    max_depth = kwargs.get("max_depth", 10)
    skip_none = kwargs.get("skip_none", False)
    pretty = kwargs.get("pretty", False)

    def indent(level):
        return "  " * level if pretty else ""

    def _to_html(o, depth=0):
        if depth > max_depth:
            return f'{indent(depth)}<div class="{class_prefix}-max-depth">…</div>'

        if o is None:
            return "" if skip_none else f'{indent(depth)}<div class="{class_prefix}-none">None</div>'

        elif isinstance(o, bool):
            return f'{indent(depth)}<div class="{class_prefix}-bool">{o}</div>'

        elif isinstance(o, (int, float)):
            return f'{indent(depth)}<div class="{class_prefix}-number">{o}</div>'

        elif isinstance(o, str):
            safe = html.escape(o)
            return f'{indent(depth)}<div class="{class_prefix}-string">"{safe}"</div>'

        elif isinstance(o, Mapping):
            html_parts = [f'{indent(depth)}<table class="{class_prefix}-dict">']
            for k, v in o.items():
                if v is None and skip_none:
                    continue
                key_html = html.escape(str(k))
                value_html = _to_html(v, depth + 1)
                html_parts.append(f'{indent(depth+1)}<tr><th>{key_html}</th><td>{value_html}</td></tr>')
            html_parts.append(f'{indent(depth)}</table>')
            return "\n".join(html_parts)

        elif isinstance(o, Sequence) and not isinstance(o, (str, bytes)):
            html_parts = [f'{indent(depth)}<ul class="{class_prefix}-list">']
            for item in o:
                item_html = _to_html(item, depth + 1)
                html_parts.append(f'{indent(depth+1)}<li>{item_html}</li>')
            html_parts.append(f'{indent(depth)}</ul>')
            return "\n".join(html_parts)

        elif hasattr(o, "__dict__"):
            html_parts = [f'{indent(depth)}<div class="{class_prefix}-object">']
            html_parts.append(f'{indent(depth+1)}<div class="{class_prefix}-class-name">{o.__class__.__name__}</div>')
            for k, v in vars(o).items():
                if v is None and skip_none:
                    continue
                value_html = _to_html(v, depth + 2)
                html_parts.append(f'{indent(depth+1)}<div class="{class_prefix}-field"><strong>{html.escape(k)}:</strong> {value_html}</div>')
            html_parts.append(f'{indent(depth)}</div>')
            return "\n".join(html_parts)

        else:
            safe = html.escape(str(o))
            return f'{indent(depth)}<div class="{class_prefix}-other">{safe}</div>'

    return _to_html(obj)


def to_bool(val):
    """Robustly convert any input to boolean, handling text representations."""
    falsey_strs = {
        '', '0', 'false', 'f', 'no', 'n', 'off', 'none', 'null', 'nil', 'undefined'
    }

    # Short-circuit for actual bools
    if isinstance(val, bool):
        return val

    # Handle None as False
    if val is None:
        return False

    # Handle numbers directly
    if isinstance(val, (int, float)):
        return bool(val)

    # Try string-like logic
    try:
        s = str(val).strip().lower()
        if s in falsey_strs:
            return False
        # Special case: a string of just spaces is considered False
        if not s:
            return False
        # If it's numeric, treat "0" as False, others as True
        if s.isdigit():
            return s != "0"
        return True
    except Exception:
        # Fallback: use regular bool conversion
        return bool(val)

def to_dict(obj, *, max_depth: int = 4):
    """
    Attempt to coerce ``obj`` into a sanitized ``dict``.

    The result is limited to ``max_depth`` levels. Any deeper structures are
    replaced with ``"..."`` to avoid runaway recursion.

    Supported inputs:
    - ``dict`` (returned as-is, but sanitized)
    - ``str`` or ``bytes`` containing JSON or HTML form data
    - objects with a ``__dict__`` attribute

    ``ValueError`` is raised if conversion is impossible.
    """

    def _sanitize(o, depth: int = 0):
        if depth >= max_depth:
            return "..."
        if isinstance(o, dict):
            return {k: _sanitize(v, depth + 1) for k, v in o.items()}
        if isinstance(o, (list, tuple, set)):
            return [_sanitize(v, depth + 1) for v in o]
        if hasattr(o, "__dict__"):
            return _sanitize(vars(o), depth + 1)
        return o

    # Idempotent: already dict
    if isinstance(obj, dict):
        return _sanitize(obj)

    # Accept bytes, decode to str
    if isinstance(obj, bytes):
        obj = obj.decode('utf-8', errors='replace')

    # Accept string: try JSON, then HTML
    if isinstance(obj, str):
        text = obj.strip()
        # Try JSON
        try:
            data = json.loads(text)
            if isinstance(data, dict):
                return _sanitize(data)
        except Exception:
            pass

        # Try HTML form
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(text, "html.parser")

            def extract_fields(scope):
                result = {}

                # Nested forms/fieldsets
                for form in scope.find_all(['form', 'fieldset'], recursive=False):
                    key = form.get('name') or form.get('id')
                    subfields = extract_fields(form)
                    if key:
                        result[key] = subfields
                    else:
                        result.update(subfields)

                # Inputs
                for inp in scope.find_all('input', recursive=False):
                    name = inp.get('name')
                    if not name:
                        continue
                    value = inp.get('value', '')
                    if inp.get('type') in ('checkbox', 'radio'):
                        if inp.has_attr('checked'):
                            result[name] = value or 'on'
                    else:
                        result[name] = value

                # Textareas
                for ta in scope.find_all('textarea', recursive=False):
                    name = ta.get('name')
                    if name:
                        result[name] = ta.text or ta.string or ''

                # Selects
                for sel in scope.find_all('select', recursive=False):
                    name = sel.get('name')
                    if not name:
                        continue
                    if sel.has_attr('multiple'):
                        selected = [opt.get('value', opt.text)
                                    for opt in sel.find_all('option', selected=True)]
                        result[name] = selected
                    else:
                        opt = sel.find('option', selected=True)
                        if not opt:
                            opt = sel.find('option')
                        result[name] = opt.get('value', opt.text) if opt else ''
                return result

            parsed = extract_fields(soup)
            if not parsed:
                raise ValueError("No form-like data found in HTML")
            return _sanitize(parsed)
        except Exception:
            pass

    if hasattr(obj, "__dict__"):
        return _sanitize(vars(obj))

    raise ValueError("Cannot convert input to dict")

