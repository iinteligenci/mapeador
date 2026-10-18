"""Planeja buscas complementares com IA para encontrar empresas e dados públicos."""
from __future__ import annotations

import json
import os
import re
from typing import Any

from dotenv import load_dotenv
from google import genai

load_dotenv()


def _fallback_queries(term: str) -> list[str]:
    """Amplia a busca por categorias diferentes quando a IA não está disponível."""
    base = re.sub(r"\s+", " ", term).strip()
    if not base:
        return []

    # Para termos no formato "categoria em cidade", preserve a localidade e varie
    # o tipo de estabelecimento para não repetir quatro buscas quase idênticas.
    match = re.match(r"^(.+?)\\s+em\\s+(.+)$", base, flags=re.IGNORECASE)
    if match:
        location = match.group(2).strip()
        categories = [
            match.group(1).strip(),
            "bares",
            "petiscarias",
            "distribuidoras de alimentos",
            "açougues",
            "padarias",
            "restaurantes",
        ]
        queries = [f"{category} em {location}" for category in categories]
    else:
        queries = [
            base,
            f"bares e petiscarias {base}",
            f"distribuidoras de alimentos {base}",
            f"açougues e padarias {base}",
            f"restaurantes {base}",
        ]
    return list(dict.fromkeys(queries))




def plan_deep_searches(term: str, business: dict[str, Any] | None = None, limit: int = 4) -> list[str]:
    """Gera consultas de pesquisa variadas; retorna apenas consultas, nunca fatos inventados."""
    base = re.sub(r"\s+", " ", str(term or "")).strip()
    if not base:
        return []
    fallback = _fallback_queries(base)
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key or api_key == "cole_sua_chave_aqui":
        return fallback[:max(1, min(limit, 8))]

    safe_business = {}
    if business:
        safe_business = {
            key: str(business.get(key) or "")[:200]
            for key in ("name", "category", "address", "phone", "website")
        }
    prompt = f"""
Você é planejador de pesquisa comercial B2B no Brasil. Crie consultas de busca curtas e
concretas para encontrar estabelecimentos diferentes no Google Maps. Não responda com fatos,
não invente dados nem nomes de empresas. Mantenha a localidade e varie as categorias entre
restaurantes, bares/petiscarias, distribuidoras de alimentos, açougues e padarias quando fizer
sentido. Evite quatro consultas que sejam apenas a mesma frase com palavras como telefone/site.
Priorize negócios alimentícios novos, com nome e localidade verificáveis.
Use o negócio/localidade abaixo e, se houver, o estabelecimento específico.
Consulta original: {base}
Estabelecimento: {json.dumps(safe_business, ensure_ascii=False)}
Retorne somente JSON: {{"queries":["consulta 1","consulta 2"]}}
No máximo {max(1, min(limit, 8))} consultas, sem duplicatas e em português brasileiro.
"""
    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite"),
            contents=prompt,
        )
        raw = re.sub(r"^\s*```(?:json)?\s*|```\s*$", "", (getattr(response, "text", "") or "").strip(), flags=re.I)
        data = json.loads(raw)
        queries = data.get("queries", [])
        cleaned = []
        for query in queries if isinstance(queries, list) else []:
            value = re.sub(r"\s+", " ", str(query)).strip()[:180]
            if value and value.casefold() not in {q.casefold() for q in cleaned}:
                cleaned.append(value)
        return (cleaned or fallback)[:max(1, min(limit, 8))]
    except Exception:
        return fallback[:max(1, min(limit, 8))]
