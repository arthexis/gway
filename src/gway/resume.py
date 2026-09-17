from __future__ import annotations

import sys

from .checkpoint import resume as _resume

sys.modules[__name__] = _resume
