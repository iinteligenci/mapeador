"""Enriquecimento assistido por Gemini com pesquisa Google grounding, usando fontes públicas."""
from __future__ import annotations

import json
import os
import re
from typing import Any

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()


def enrich_business_with_ai(lead: dict[str, Any]) -> dict[str, Any]:
    """Busca dados públicos adicionais; devolve apenas campos acompanhados de fontes verificáveis."""
    result: dict[str, Any] = {
        "website": "", "emails": [], "phones": [], "whatsapps": [],
        "instagram": "", "menu_url": "", "sources": [], "notes": [],
    }
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key or api_key == "cole_sua_chave_aqui":
        result["notes"].append("Pesquisa aprofundada por IA indisponível: configure GEMINI_API_KEY.")
        return result

    name = str(lead.get("name") or "")[:200]
    category = str(lead.get("category") or "")[:120]
    address = str(lead.get("address") or "")[:250]
    phone = str(lead.get("phone") or "")[:80]
    website = str(lead.get("website") or "")[:300]
    prompt = f"""
Pesquise na web usando somente fontes públicas para identificar o estabelecimento comercial abaixo.
Nome: {name}
Categoria: {category}
Endereço: {address}
Telefone já conhecido: {phone}
Site já conhecido: {website}

Objetivo: enriquecer o cadastro com site oficial, e-mails comerciais publicados, telefones comerciais,
links de WhatsApp publicados, Instagram oficial, link público de cardápio/catálogo e fontes.
Não adivinhe nem gere contatos. Só inclua um dado se o resultado de busca o sustentar claramente.
Não confunda empresas homônimas: use endereço/localidade e nome para confirmar identidade.
Para cada dado, forneça a URL pública exata da fonte. Se não houver confirmação, deixe vazio.
Retorne somente JSON neste formato:
{{"website":{{"value":"","source":""}},"emails":[{{"value":"","source":""}}],
"phones":[{{"value":"","source":""}}],"whatsapps":[{{"value":"","source":""}}],
"instagram":{{"value":"","source":""}},"menu_url":{{"value":"","source":""}},
"notes":["fatos confirmados e limitações"],"sources":["URL pública"]}}
"""
    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=os.getenv("GEMINI_RESEARCH_MODEL", os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")),
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
                temperature=0.1,
            ),
        )
        raw = re.sub(r"^\s*```(?:json)?\s*|```\s*$", "", (getattr(response, "text", "") or "").strip(), flags=re.I)
        data = json.loads(raw)
        def one(key: str) -> str:
            obj = data.get(key) or {}
            value = str(obj.get("value") or "").strip() if isinstance(obj, dict) else ""
            source = str(obj.get("source") or "").strip() if isinstance(obj, dict) else ""
            if value and source.startswith(("https://", "http://")):
                result["sources"].append(source)
                return value
            return ""
        result["website"] = one("website")
        result["instagram"] = one("instagram")
        result["menu_url"] = one("menu_url")
        for key, dest in (("emails", "emails"), ("phones", "phones"), ("whatsapps", "whatsapps")):
            values = []
            for item in data.get(key, []) if isinstance(data.get(key), list) else []:
                if not isinstance(item, dict):
                    continue
                value = str(item.get("value") or "").strip()
                source = str(item.get("source") or "").strip()
                if value and source.startswith(("https://", "http://")) and value not in values:
                    values.append(value)
                    result["sources"].append(source)
            result[dest] = values[:10]
        result["sources"] = list(dict.fromkeys(
            [s for s in result["sources"] if s.startswith(("https://", "http://"))]
            + [str(s).strip() for s in data.get("sources", []) if str(s).strip().startswith(("https://", "http://"))]
        ))[:20]
        result["notes"] = [str(n)[:300] for n in data.get("notes", [])[:10]] if isinstance(data.get("notes"), list) else []
    except Exception as exc:
        result["notes"].append(f"Pesquisa assistida por IA não concluída ({type(exc).__name__}).")
    return result
