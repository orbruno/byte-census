"""JSON renderer: the envelope as indented JSON, field order preserved."""

import json
from collections.abc import Mapping
from typing import Any


def render_json(payload: Mapping[str, Any]) -> str:
    """Indented JSON with a trailing newline; non-ASCII text kept as is."""
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
