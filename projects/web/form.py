# projects/web/forms.py

"""
GWAY web module to build HTML forms for GWAY commands dynamically.

Usage:
  Any view can call `gw.web.forms.build(gw.<project>.<command>, **form_attrs)`
to get an HTML form that submits to the command's CLI path.

The form fields:
- Use parameter default values as placeholders.
- Mark required fields.
- Support common HTML input types based on Python types.

Extra HTML form attributes can be passed as kwargs to `build`.
"""

import inspect
from gway import gw
from html import escape

def build(command, **form_attrs) -> str:
    """
    Build an HTML form for the given GWAY command function.

    Args:
        command: The function (from gw.<project>.<command>) to generate a form for.
        **form_attrs: Optional HTML form attributes like action, method, id, class, etc.

    Returns:
        HTML string of the generated form.
    """
    sig = inspect.signature(command)

    # Set default form action and method if not given
    form_action = form_attrs.pop('action', '#')
    form_method = form_attrs.pop('method', 'post').lower()

    # Start form tag
    attrs_str = ' '.join(f'{escape(str(k))}="{escape(str(v))}"' for k, v in form_attrs.items())
    form_html = [f'<form action="{escape(form_action)}" method="{escape(form_method)}" {attrs_str}>']

    # Generate inputs for each parameter
    for name, param in sig.parameters.items():
        # Determine if required or optional
        required = param.default is inspect.Parameter.empty

        # Determine input type by annotation if available, fallback to text
        input_type = "text"
        if param.annotation is not inspect.Parameter.empty:
            annotation = param.annotation
            # Map some common types to input types
            if annotation in {int, float}:
                input_type = "number"
            elif annotation is bool:
                input_type = "checkbox"
            elif annotation is str:
                input_type = "text"

        # Prepare placeholder
        placeholder = ''
        if param.default is not inspect.Parameter.empty and param.default is not None:
            placeholder = str(param.default)

        # Checkbox special case: for bool, checked if default True
        if input_type == "checkbox":
            checked = ''
            if param.default is True:
                checked = ' checked'
            form_html.append(
                f'<label for="{name}">{escape(name)}{" *" if required else ""}</label> '
                f'<input type="checkbox" id="{name}" name="{name}"{checked}>'
            )
        else:
            # Normal inputs
            form_html.append(
                f'<label for="{name}">{escape(name)}{" *" if required else ""}</label> '
                f'<input type="{input_type}" id="{name}" name="{name}" '
                f'placeholder="{escape(placeholder)}" {"required" if required else ""}>'
            )

        form_html.append('<br>')

    # Submit button
    form_html.append('<button type="submit">Submit</button>')
    form_html.append('</form>')

    return '\n'.join(form_html)
