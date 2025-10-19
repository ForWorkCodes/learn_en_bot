from __future__ import annotations

MARKDOWN_V2_SPECIAL_CHARS = set("_[]()~`>#+-=|{}.!*<")
MARKDOWN_V2_SPECIAL_CHARS.add("\\")


def escape(text: str) -> str:
    """Escape Telegram MarkdownV2 special characters."""
    if not text:
        return ""
    return "".join(f"\\{ch}" if ch in MARKDOWN_V2_SPECIAL_CHARS else ch for ch in text)


def bold(text: str) -> str:
    return f"*{escape(text)}*"


def italic(text: str) -> str:
    return f"_{escape(text)}_"


def monospace(text: str) -> str:
    return f"`{escape(text)}`"

