from types import SimpleNamespace

import pytest

from api.progress import _tool_calls, _truncate, describe_update


@pytest.mark.parametrize(
    ("node", "expected_title"),
    [
        ("supervisor", "Supervisor"),
        ("decompositor", "Decompositor"),
        ("pesquisador", "Pesquisador"),
        ("pesquisador_tools", "Base de artigos"),
        ("redator", "Redator"),
        ("planejador", "Planejador"),
        ("verificador", "Verificador"),
        ("finalizar", "Resposta final"),
        ("fora_dominio", "Fora do domínio"),
        ("novo_no", "novo_no"),
    ],
)
def test_describe_update_identifies_node(node, expected_title):
    result = describe_update(node, {})
    assert result["node"] == node
    assert result["state"] == "done"
    assert result["title"] == expected_title
    assert isinstance(result["detail"], str)
    assert isinstance(result["data"], dict)


def test_supervisor_translates_intent_and_complexity():
    result = describe_update(
        "supervisor", {"intent": "qa", "complexity": "complexa"}
    )
    assert result["data"] == {"intent": "qa", "complexity": "complexa"}
    assert "pergunta direta" in result["detail"]
    assert "complexa" in result["detail"]


def test_decompositor_reports_plan_steps():
    result = describe_update("decompositor", {"plan_steps": ["A", "B"]})
    assert result["data"]["steps"] == ["A", "B"]
    assert "2 etapa(s)" in result["detail"]


def test_verifier_includes_truncated_feedback():
    result = describe_update(
        "verificador", {"verdict": "reescrever", "feedback": "x" * 600}
    )
    assert result["data"]["verdict"] == "reescrever"
    assert len(result["data"]["feedback"]) == 500
    assert len(result["detail"]) < 250


def test_truncate_normalizes_whitespace_and_respects_limit():
    assert _truncate("  uma\n frase   aqui ") == "uma frase aqui"
    assert len(_truncate("x" * 300, 20)) == 20
    assert _truncate("curto", 20) == "curto"


def test_tool_calls_extracts_known_argument_and_label():
    message = SimpleNamespace(
        tool_calls=[
            {
                "name": "buscar_projetos_semelhantes",
                "args": {"palavras_chave": ["IA", "educação"]},
            }
        ]
    )
    calls = _tool_calls({"messages": [message]})
    assert calls == [{
        "name": "buscar_projetos_semelhantes",
        "label": "projetos semelhantes",
        "query": "IA, educação",
    }]


def test_tool_calls_handles_unknown_tools_and_missing_arguments():
    message = SimpleNamespace(
        tool_calls=[
            {"name": "ferramenta_nova", "args": {"termo": "busca"}},
            {"name": "sem_argumentos"},
            "inválida",
        ]
    )
    calls = _tool_calls({"messages": [message]})
    assert calls[0]["label"] == "ferramenta_nova"
    assert calls[0]["query"] == "busca"
    assert calls[1]["name"] == "sem_argumentos"
    assert calls[1]["query"] == ""
    assert len(calls) == 2


def test_researcher_without_tool_calls_has_fallback_detail():
    result = describe_update("pesquisador", {"messages": []})
    assert result["data"] == {"tools": []}
    assert "Selecionando ferramentas" in result["detail"]
