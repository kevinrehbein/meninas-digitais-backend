import pytest

from api import service


class FakeGraph:
    def __init__(self, chunks):
        self.chunks = chunks
        self.call = None

    async def astream(self, state, *, config, stream_mode):
        self.call = (state, config, stream_mode)
        for chunk in self.chunks:
            yield chunk


def test_get_graph_validates_and_caches(monkeypatch):
    service.get_graph.cache_clear()
    calls = []
    graph = object()
    monkeypatch.setattr(service, "validate_config", lambda: calls.append("valid"))
    monkeypatch.setattr(service, "graph_builder", lambda: graph)
    try:
        assert service.get_graph() is graph
        assert service.get_graph() is graph
        assert calls == ["valid"]
    finally:
        service.get_graph.cache_clear()


def test_get_graph_does_not_build_when_config_is_invalid(monkeypatch):
    service.get_graph.cache_clear()
    def invalid_config():
        raise RuntimeError("config")
    monkeypatch.setattr(service, "validate_config", invalid_config)
    monkeypatch.setattr(
        service, "graph_builder", lambda: pytest.fail("grafo não deveria ser criado")
    )
    try:
        with pytest.raises(RuntimeError, match="config"):
            service.get_graph()
    finally:
        service.get_graph.cache_clear()


@pytest.mark.asyncio
async def test_run_graph_emits_status_and_final_payload(monkeypatch, sample_question):
    graph = FakeGraph([
        {"supervisor": {"intent": "qa", "complexity": "simples"}},
        {"pesquisador_tools": {"messages": ["mensagem de ferramenta"]}},
        {"redator": {"final_response": "Resposta final", "iteration_count": 2}},
    ])
    monkeypatch.setattr(service, "get_graph", lambda: graph)
    monkeypatch.setattr(service, "extract_sources", lambda messages: {
        "https://example.org": {"title": "Artigo", "url": "https://example.org"}
    })
    monkeypatch.setattr(
        service, "format_final_response", lambda response: f"MD: {response}"
    )
    monkeypatch.setattr(service, "MAX_SOURCES", 40)

    events = [event async for event in service.run_graph(sample_question)]
    assert [event["event"] for event in events] == [
        "status", "status", "status", "final"
    ]
    assert graph.call[0]["messages"][0].content == sample_question
    assert graph.call[1] == {"recursion_limit": service.GRAPH_RECURSION_LIMIT}
    assert graph.call[2] == "updates"

    final = events[-1]["data"]
    assert final["answer_markdown"] == "MD: Resposta final"
    assert final["response_type"] == "text"
    assert final["plan"] is None
    assert final["sources"] == [
        {"title": "Artigo", "url": "https://example.org"}
    ]
    assert final["meta"]["intent"] == "qa"
    assert final["meta"]["iterations"] == 2
    assert final["meta"]["elapsed_ms"] >= 0


@pytest.mark.asyncio
async def test_run_graph_deduplicates_sources_and_limits_them(monkeypatch):
    graph = FakeGraph([
        {"pesquisador_tools": {"messages": ["m1"]}},
        {"pesquisador_tools": {"messages": ["m2"]}},
        {"planejador": {"final_response": {"steps": ["A"]}}},
    ])
    monkeypatch.setattr(service, "get_graph", lambda: graph)
    monkeypatch.setattr(service, "extract_sources", lambda messages: (
        {"https://a": {"title": "A", "url": "https://a"}}
        if messages == ["m1"] else {
            "https://a": {"title": "duplicada", "url": "https://a"},
            "https://b": {"title": "B", "url": "https://b"},
        }
    ))
    monkeypatch.setattr(service, "MAX_SOURCES", 1)
    monkeypatch.setattr(service, "format_final_response", lambda response: "Plano")

    events = [event async for event in service.run_graph("pergunta")]
    final = events[-1]["data"]
    assert final["response_type"] == "plan"
    assert final["plan"] == {"steps": ["A"]}
    assert final["sources"] == [{"title": "A", "url": "https://a"}]


@pytest.mark.asyncio
async def test_run_graph_ignores_non_dict_updates(monkeypatch):
    graph = FakeGraph([{"node": None}, {"node": "texto"}])
    monkeypatch.setattr(service, "get_graph", lambda: graph)
    monkeypatch.setattr(service, "format_final_response", lambda response: "")
    events = [event async for event in service.run_graph("pergunta")]
    assert [event["event"] for event in events] == ["final"]
