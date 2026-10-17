"""Assistente de vendas para respostas comerciais com exemplos aprovados pelo usuário."""
from __future__ import annotations

import json
import os
from typing import Any

from dotenv import load_dotenv
from google import genai

from database.db import get_sales_examples

load_dotenv()


def draft_sales_reply(
    business: dict[str, Any],
    customer_message: str,
    offer_profile: str = "4k",
    offer_details: str = "",
    conversation_context: str = "",
    path: str | None = None,
) -> dict[str, str]:
    """Prepara uma resposta natural para revisão humana; nunca envia mensagens."""
    message = str(customer_message or "").strip()[:5000]
    if not message:
        raise ValueError("Cole a última mensagem do cliente.")
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key or api_key == "cole_sua_chave_aqui":
        raise RuntimeError("Configure GEMINI_API_KEY no arquivo .env para ativar o vendedor com IA.")

    examples = get_sales_examples(path=path, limit=10)
    curated_examples = [
        {
            "contexto": item.get("title", ""),
            "conversa_real": item.get("conversation", "")[:1800],
            "resposta_aprovada": item.get("preferred_reply", "")[:1000],
            "observacoes": item.get("notes", ""),
        }
        for item in examples
    ]
    profile_label = {
        "4k": "4K Food Service — distribuição e fornecimento de alimentos para negócios",
        "digital": "serviços de presença digital para empresas",
        "dornelas": "Charcutaria/Defumados Dornelas — produtos defumados e kits para consumidor final",
    }.get(offer_profile, "venda B2B")
    prompt = f"""
Você é o vendedor consultivo da empresa abaixo. Escreva como uma pessoa experiente em WhatsApp:
natural, breve, cordial, confiante e sem frases robóticas. Seu objetivo é entender a necessidade,
construir confiança, responder objeções com honestidade e avançar um passo concreto na negociação.

REGRAS:
- Não invente preço, estoque, prazo, desconto, condições de pagamento, entrega ou características.
- Se faltar dado essencial, faça uma pergunta ou marque claramente [CONFIRMAR ...].
- Não ofereça desconto nem aceite condições comerciais que não estejam autorizadas.
- Não pressione, não manipule e não finja ser o cliente ou outra pessoa.
- Use no máximo uma pergunta simples no final, quando fizer sentido.
- Preserve a linguagem e o estilo dos exemplos aprovados, sem copiar dados específicos de outros clientes.
- Considere a conversa completa e responda à última mensagem do cliente.
- Retorne apenas JSON válido com os campos "resposta", "objetivo_proximo_passo" e "dados_a_confirmar".
- A resposta será revisada por uma pessoa. Não envie nada por WhatsApp nem afirme que foi enviado.

Empresa/oferta: {profile_label}
Detalhes autorizados da oferta: {str(offer_details or "Não foram fornecidos detalhes comerciais específicos.")[:2500]}
Estabelecimento/cliente: {json.dumps({
    "nome": str(business.get("name", ""))[:200],
    "categoria": str(business.get("category", ""))[:160],
    "localidade": str(business.get("address", ""))[:250],
    "telefone": str(business.get("phone", ""))[:80],
}, ensure_ascii=False)}
Contexto anterior da conversa: {str(conversation_context or "Não informado.")[:5000]}
Última mensagem recebida do cliente: {message}
Exemplos de atendimentos reais aprovados pelo usuário (referência de estilo e abordagem, não de fatos):
{json.dumps(curated_examples, ensure_ascii=False)}
"""
    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=os.getenv("GEMINI_MODEL", "gemini-3.8-flash"),
        contents=prompt,
    )
    raw = (getattr(response, "text", "") or "").strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("A IA retornou uma resposta que não pude interpretar. Tente novamente.") from exc
    return {
        "resposta": str(parsed.get("resposta") or "").strip(),
        "objetivo_proximo_passo": str(parsed.get("objetivo_proximo_passo") or "").strip(),
        "dados_a_confirmar": str(parsed.get("dados_a_confirmar") or "").strip(),
    }
