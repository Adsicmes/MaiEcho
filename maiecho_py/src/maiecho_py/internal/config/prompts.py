from __future__ import annotations

from typing import Any

from jinja2 import StrictUndefined, Template


def render_prompt(template: str, context: dict[str, Any]) -> str:
    return Template(template, undefined=StrictUndefined).render(**context)
