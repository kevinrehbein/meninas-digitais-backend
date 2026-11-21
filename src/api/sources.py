import re

from agents.utils import message_text

FONTE_RE = re.compile(
    r"FONTE:\s*\[(?P<title>[^\]]+)\]\((?P<url>https?://[^)\s]+)\)"
)


def extract_sources(messages: list) -> dict[str, dict[str, str]]:
    """Extrai fontes estruturadas das ToolMessages, sem expor o texto bruto."""
    sources: dict[str, dict[str, str]] = {}
    if not messages:
        return sources

    for message in messages:
        try:
            text = message_text(message)
        except Exception:  # noqa: BLE001, S112 - mensagens heterogêneas
            continue
        for match in FONTE_RE.finditer(text):
            title = match.group("title").strip()
            url = match.group("url").strip()
            if not title or not url:
                continue
            sources.setdefault(url, {"title": title, "url": url})
    return sources
