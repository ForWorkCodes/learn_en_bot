from __future__ import annotations

from html import escape
from html.parser import HTMLParser


ALLOWED_TAGS: frozenset[str] = frozenset({
    "b",
    "i",
    "u",
    "s",
    "code",
    "pre",
    "a",
    "ul",
    "ol",
    "li",
    "br",
})

SELF_CLOSING_TAGS: frozenset[str] = frozenset({"br"})

ALLOWED_ATTRIBUTES: dict[str, frozenset[str]] = {
    "a": frozenset({"href"}),
}


class _TelegramHTMLSanitizer(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self._parts: list[str] = []
        self._open_tags: list[str] = []
        self._has_output = False
        self._last_chars = ""

    def handle_starttag(self, tag: str, attrs) -> None:  # type: ignore[override]
        tag = tag.lower()
        if tag == "p":
            # paragraph tags are not supported by Telegram — treat as a break
            return

        if tag not in ALLOWED_TAGS:
            return

        allowed = ALLOWED_ATTRIBUTES.get(tag, frozenset())
        filtered_attrs = []
        for name, value in attrs:
            if name in allowed and value is not None:
                filtered_attrs.append((name, escape(value, quote=True)))

        attr_text = "".join(f' {name}="{value}"' for name, value in filtered_attrs)
        self._append(f"<{tag}{attr_text}>")

        if tag not in SELF_CLOSING_TAGS:
            self._open_tags.append(tag)

    def handle_startendtag(self, tag: str, attrs) -> None:  # type: ignore[override]
        # Handle tags like <br/> explicitly
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:  # type: ignore[override]
        tag = tag.lower()
        if tag == "p":
            self._append_paragraph_break()
            return

        if tag not in ALLOWED_TAGS:
            return

        while self._open_tags:
            open_tag = self._open_tags.pop()
            self._append(f"</{open_tag}>")
            if open_tag == tag:
                break

    def handle_data(self, data: str) -> None:  # type: ignore[override]
        if not data:
            return
        self._append(escape(data))

    def handle_entityref(self, name: str) -> None:  # type: ignore[override]
        self._append(f"&{name};")

    def handle_charref(self, name: str) -> None:  # type: ignore[override]
        self._append(f"&#{name};")

    def get_output(self) -> str:
        # Close any still-open tags to keep the fragment valid
        while self._open_tags:
            tag = self._open_tags.pop()
            self._append(f"</{tag}>")
        return "".join(self._parts).strip()

    def _append(self, text: str) -> None:
        if not text:
            return
        self._parts.append(text)
        self._has_output = True
        tail = (self._last_chars + text)[-2:]
        self._last_chars = tail

    def _append_paragraph_break(self) -> None:
        if not self._has_output:
            return
        if self._last_chars.endswith("\n\n"):
            return
        if self._last_chars.endswith("\n"):
            self._append("\n")
        else:
            self._append("\n\n")


def sanitize_html_fragment(text: str) -> str:
    """Return text safe to send with Telegram HTML parse mode."""

    if not text:
        return ""

    parser = _TelegramHTMLSanitizer()
    parser.feed(text)
    parser.close()
    sanitized = parser.get_output()
    return sanitized or ""

