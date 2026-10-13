"""Geração de mensagens comerciais personalizadas com Gemini."""
from __future__ import annotations

import os
from typing import Any

import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()


def generate_outreach_message(lead: dict[str, Any], offer: str | None = None) -> str:
    """Gera uma primeira abordagem curta para um lead.

    Requer GEMINI_API_KEY no ambiente ou no arquivo .env. A mensagem é apenas
    um rascunho para revisão humana; não presume fatos não presentes nos dados.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY não configurada. Copie .env.example para .env.")

    model_name = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(model_name)

    name = str(lead.get("name") or "sua empresa").strip()
    category = str(lead.get("category") or "empresa local").strip()
    link = str(lead.get("link") or "").strip()
    offer_text = offer.strip() if offer else (
        "apresentar brevemente nossos serviços e entender se existe alguma oportunidade de parceria"
    )

    prompt = f"""
Você é um assistente de prospecção B2B no Brasil.
Escreva uma primeira mensagem comercial em português brasileiro, natural,
respeitosa e personalizada com base somente nos dados abaixo.
Não invente informações, resultados, relacionamento prévio ou necessidades.
Não use pressão, promessas exageradas nem intimidade artificial.
Faça no máximo 80 palavras, com uma pergunta simples no final.
Identifique-se como representante da [NOME DA SUA EMPRESA], sem inventar esse nome.

Lead: {name}
Categoria identificada: {category}
Link público do local: {link or "não informado"}
Objetivo/oferta: {offer_text}

Retorne somente o texto da mensagem, sem aspas nem explicações.
"""
    response = model.generate_content(prompt)
    message = getattr(response, "text", None)
    if not message or not message.strip():
        raise RuntimeError("O Gemini não retornou uma mensagem utilizável.")
    return message.strip()
