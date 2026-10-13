"""Qualificação de leads e rascunho comercial usando Gemini."""
from __future__ import annotations

import json
import os
import re
from typing import Any

import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()


def analyze_lead(lead: dict[str, Any], offer: str | None = None) -> dict[str, Any]:
    """Retorna score 0-100, justificativa e mensagem sugerida.

    A avaliação é uma hipótese baseada somente nos dados fornecidos, não uma
    verificação independente da empresa. O texto deve ser revisado por uma pessoa.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key or api_key == "cole_sua_chave_aqui":
        raise RuntimeError("Configure GEMINI_API_KEY no arquivo .env antes de executar.")
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(os.getenv("GEMINI_MODEL", "gemini-2.0-flash"))

    safe_lead = {
        "name": str(lead.get("name", ""))[:200],
        "category": str(lead.get("category", ""))[:200],
        "phone": str(lead.get("phone", ""))[:80],
        "website": str(lead.get("website", ""))[:300],
        "link": str(lead.get("link", ""))[:500],
    }
    prompt = f"""
Você ajuda a preparar prospecção B2B ética para empresas no Brasil.
Analise os dados fornecidos, sem pesquisar nem inventar fatos. Não deduza problemas
de marketing como se fossem comprovados. Se houver poucos dados, diga isso.
Crie uma mensagem inicial curta, respeitosa, com no máximo 80 palavras, sem
pressão e terminando com uma pergunta simples. Não afirme que já analisou o site.
Use [NOME DA SUA EMPRESA] como marcador de identidade.

Oferta que quero apresentar: {offer or "serviços de presença digital"}
Dados do lead: {json.dumps(safe_lead, ensure_ascii=False)}

Responda SOMENTE com JSON válido neste formato:
{{"score": 0, "justificativa": "uma frase explicando a adequação e limitações dos dados",
"mensagem": "mensagem comercial em português brasileiro"}}
O score é uma estimativa de adequação da categoria à oferta, não uma avaliação da empresa.
"""
    response = model.generate_content(prompt)
    raw = (getattr(response, "text", "") or "").strip()
    raw = re.sub(r"^\s*```(?:json)?\s*|\s*```\s*$", "", raw, flags=re.I)
    try:
        data = json.loads(raw)
        score = max(0, min(100, int(data.get("score", 0))))
        message = str(data.get("mensagem", "")).strip()
        reason = str(data.get("justificativa", "")).strip()
        if not message:
            raise ValueError("Mensagem vazia")
        return {"score": score, "justificativa": reason, "mensagem": message}
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise RuntimeError(f"Resposta do Gemini inválida; tente novamente. Detalhe: {exc}") from exc


def generate_outreach_message(lead: dict[str, Any], offer: str | None = None) -> str:
    """Compatibilidade com a versão inicial do projeto."""
    return str(analyze_lead(lead, offer)["mensagem"])
