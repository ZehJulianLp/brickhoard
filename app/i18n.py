from __future__ import annotations

import re

from flask_babel import gettext


_PROTECTED_BLOCKS = re.compile(r"(<(?:script|style)\b.*?</(?:script|style)>)", re.I | re.S)
_TEXT_NODE = re.compile(r">([^<>]+)<")
_TRANSLATABLE_ATTRIBUTE = re.compile(
    r'\b(aria-label|alt|placeholder|title)=(?P<quote>["\'])(?P<value>.*?)(?P=quote)',
    re.I,
)


def _translated(value: str) -> str:
    leading = value[: len(value) - len(value.lstrip())]
    trailing = value[len(value.rstrip()) :]
    message = value.strip()
    if not message or message.startswith(("{{", "{%")):
        return value
    return f"{leading}{gettext(message)}{trailing}"


def localize_html(markup: str) -> str:
    """Translate rendered HTML without touching markup, scripts, or styles."""
    blocks = _PROTECTED_BLOCKS.split(markup)
    for index in range(0, len(blocks), 2):
        block = _TEXT_NODE.sub(lambda match: f">{_translated(match.group(1))}<", blocks[index])

        def translate_attribute(match: re.Match[str]) -> str:
            value = match.group("value")
            if not value:
                return match.group(0)
            translated = gettext(value)
            return f'{match.group(1)}={match.group("quote")}{translated}{match.group("quote")}'

        blocks[index] = _TRANSLATABLE_ATTRIBUTE.sub(translate_attribute, block)
    return "".join(blocks)
