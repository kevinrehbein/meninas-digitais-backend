"""Traduz os updates do grafo em etapas compreensíveis para a interface."""

from typing import Any

INTENT_LABELS = {
    "qa": "pergunta direta",
    "sintese": "síntese",
    "plano": "plano de projeto",
    "fora_dominio": "fora do domínio",
}

COMPLEXITY_LABELS = {
    "simples": "simples",
    "complexa": "complexa",
}

VERDICT_LABELS = {
    "aprovado": "aprovado",
    "reescrever": "revisão do texto solicitada",
    "pesquisar_mais": "pesquisa adicional solicitada",
    "reclassificar": "reclassificação solicitada",
}

TOOL_LABELS = {
    "pesquisar_contexto_wit": "busca semântica na base do WIT",
    "buscar_projetos_semelhantes": "projetos semelhantes",
    "artigos_do_autor": "artigos por autoria",
    "autores_do_artigo": "autoria do artigo",
}

TOOL_QUERY_KEYS = {
    "pesquisar_contexto_wit": "pergunta",
    "buscar_projetos_semelhantes": "palavras_chave",
    "artigos_do_autor": "nome",
    "autores_do_artigo": "titulo",
}


def _truncate(value: str, limit: int = 220) -> str:
    value = " ".join(value.split())
    return value if len(value) <= limit else f"{value[: limit - 1]}…"


def _tool_calls(update: dict[str, Any]) -> list[dict[str, Any]]:
    messages = update.get("messages") or []
    calls: list[dict[str, Any]] = []
    for message in messages:
        for call in getattr(message, "tool_calls", None) or []:
            if not isinstance(call, dict):
                continue
            name = str(call.get("name") or "ferramenta")
            args = call.get("args") or {}
            query = ""
            if isinstance(args, dict):
                key = TOOL_QUERY_KEYS.get(name)
                raw = args.get(key) if key else None
                if raw is None:
                    raw = next(iter(args.values()), "")
                if isinstance(raw, list):
                    query = ", ".join(str(item) for item in raw)
                else:
                    query = str(raw)
            calls.append(
                {
                    "name": name,
                    "label": TOOL_LABELS.get(name, name),
                    "query": _truncate(query, 180),
                }
            )
    return calls


def describe_update(node: str, update: dict[str, Any]) -> dict[str, Any]:
    """Payload semântico de uma etapa concluída do grafo."""
    title = {
        "supervisor": "Supervisor",
        "decompositor": "Decompositor",
        "pesquisador": "Pesquisador",
        "pesquisador_tools": "Base de artigos",
        "redator": "Redator",
        "planejador": "Planejador",
        "verificador": "Verificador",
        "finalizar": "Resposta final",
        "fora_dominio": "Fora do domínio",
    }.get(node, node)

    data: dict[str, Any] = {}
    detail = ""

    if node == "supervisor":
        intent = str(update.get("intent") or "")
        complexity = str(update.get("complexity") or "")
        data = {"intent": intent, "complexity": complexity}
        detail = (
            f"Intenção: {INTENT_LABELS.get(intent, intent or 'não identificada')}"
            f" - complexidade: {COMPLEXITY_LABELS.get(complexity, complexity)}"
        )
    elif node == "decompositor":
        steps = [str(step) for step in update.get("plan_steps") or []]
        data = {"steps": steps}
        detail = f"{len(steps)} etapa(s) de pesquisa definida(s)"
    elif node == "pesquisador":
        calls = _tool_calls(update)
        data = {"tools": calls}
        if calls:
            detail = f"{len(calls)} consulta(s) a ser realizada(s)"
        else:
            detail = "Selecionando ferramentas de pesquisa"
    elif node == "pesquisador_tools":
        messages = update.get("messages") or []
        data = {"result_count": len(messages)}
        detail = (
            f"{len(messages)} resultado(s) de ferramenta recebido(s)"
            if messages
            else "Ferramentas executadas"
        )
    elif node == "verificador":
        verdict = str(update.get("verdict") or "")
        feedback = update.get("feedback")
        data = {"verdict": verdict}
        detail = f"Veredito: {VERDICT_LABELS.get(verdict, verdict or 'em análise')}"
        if feedback:
            data["feedback"] = _truncate(str(feedback), 500)
    elif node == "redator":
        detail = "Texto da resposta gerado"
    elif node == "planejador":
        detail = "Plano de projeto estruturado"
    elif node == "finalizar":
        detail = "Resposta final compilada"
    elif node == "fora_dominio":
        detail = "Pergunta identificada fora do escopo do WIT"
    else:
        detail = "Etapa concluída"

    return {
        "node": node,
        "state": "done",
        "title": title,
        "detail": detail,
        "data": data,
    }
