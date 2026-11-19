from types import SimpleNamespace

import pytest

from api import sources


class Message:
    def __init__(self, content):
        self.content = content


@pytest.fixture
def patch_message_text(monkeypatch):
    monkeypatch.setattr(sources, "message_text", lambda message: message.content)


def test_extracts_single_source(patch_message_text):
    result = sources.extract_sources(
        [Message("Trecho [FONTE: Artigo WIT | https://example.org/artigo]")]
    )
    assert result == {
        "https://example.org/artigo": {
            "title": "Artigo WIT",
            "url": "https://example.org/artigo",
        }
    }


def test_extracts_multiple_sources_and_deduplicates_by_url(patch_message_text):
    result = sources.extract_sources([
        Message(
            "[FONTE: Primeiro | https://example.org/a] "
            "[FONTE: Segundo | https://example.org/b]"
        ),
        Message("[FONTE: Título alternativo | https://example.org/a]"),
    ])
    assert list(result) == ["https://example.org/a", "https://example.org/b"]
    assert result["https://example.org/a"]["title"] == "Primeiro"


@pytest.mark.parametrize("messages", [None, [], ()])
def test_empty_messages_return_empty_dict(messages):
    assert sources.extract_sources(messages) == {}


def test_ignores_messages_that_cannot_be_converted(monkeypatch):
    def convert(message):
        if message == "quebra":
            raise TypeError("mensagem inesperada")
        return "[FONTE: Válida | https://example.org/ok]"
    monkeypatch.setattr(sources, "message_text", convert)
    assert list(sources.extract_sources(["quebra", "válida"])) == [
        "https://example.org/ok"
    ]
