"""Qualificação de leads e rascunho comercial usando o SDK atual do Gemini."""
from __future__ import annotations

import json
import os
import re
import time
from typing import Any

from google import genai
from dotenv import load_dotenv

load_dotenv()


def analyze_lead(lead: dict[str, Any], offer: str | None = None) -> dict[str, Any]:
    """Retorna score, justificativa e mensagem usando os dados públicos coletados."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key or api_key == "cole_sua_chave_aqui":
        raise RuntimeError("Configure GEMINI_API_KEY no arquivo .env antes de executar.")

    client = genai.Client(api_key=api_key)
    model_name = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")

    safe_lead = {
        "name": str(lead.get("name", ""))[:200],
        "category": str(lead.get("category", ""))[:200],
        "phone": str(lead.get("phone", ""))[:80],
        "address": str(lead.get("address", ""))[:300],
        "website": str(lead.get("website", ""))[:300],
        "instagram": str(lead.get("instagram", ""))[:300],
        "google_maps": str(lead.get("link", ""))[:500],
        "channels": [str(x)[:100] for x in (lead.get("channels") or [])][:20],
        "menu_url": str(lead.get("menu_url", ""))[:500],
        "menu_items": [str(x)[:120] for x in (lead.get("menu_items") or [])][:40],
        "public_platforms": [str(x)[:100] for x in (lead.get("public_platforms") or [])][:20],
        "research_notes": [str(x)[:250] for x in (lead.get("research_notes") or [])][:10],
    }
    prompt = f"""
Você ajuda a preparar prospecção B2B ética para negócios alimentícios no Brasil.
Analise somente os dados públicos fornecidos; não invente fatos nem diga que a empresa
usa uma ferramenta se isso não estiver indicado. Diferencie:
- fatos observados (ex.: telefone, Instagram, link de cardápio, canais encontrados);
- indícios (ex.: itens de menu que podem não representar todo o catálogo);
- informações não identificadas publicamente (ex.: sistema interno de gestão de vendas).
A ausência de evidência pública NÃO significa que a empresa não use um sistema.
Avalie se há uma oportunidade plausível para serviços de presença digital, considerando
presença digital e meios públicos de atendimento/venda. Se houver poucos dados, diga isso.
Não invente problemas de marketing. Crie mensagem inicial curta e respeitosa, com no máximo
80 palavras, sem pressão e terminando com uma pergunta simples. Não afirme que já analisou
o site em profundidade. Use [NOME DA SUA EMPRESA] como marcador de identidade.

Oferta que quero apresentar: {offer or "serviços de presença digital"}
Dados públicos coletados: {json.dumps(safe_lead, ensure_ascii=False)}

Responda SOMENTE com JSON válido neste formato:
{{"score": 0, "justificativa": "uma frase com a oportunidade e limitações dos dados",
"mensagem": "mensagem comercial em português brasileiro"}}
O score de 0 a 100 é apenas uma prioridade preliminar para revisão humana, não uma
avaliação comprovada da qualidade ou da gestão do estabelecimento.
"""
    # Erros transitórios do serviço Gemini (ex.: 429/503) podem se resolver
    # após uma pausa curta. Limita as tentativas para não travar a prospecção.
    response = None
    for attempt in range(3):
        try:
            response = client.models.generate_content(model=model_name, contents=prompt)
            break
        except Exception as exc:
            code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
            error_text = str(exc).upper()
            transient = (
                code in (429, 500, 502, 503, 504)
                or any(token in error_text for token in (
                    "429", "500", "502", "503", "504",
                    "UNAVAILABLE", "RESOURCE_EXHAUSTED", "INTERNAL"
                ))
            )
            if not transient or attempt == 2:
                raise
            wait_seconds = 2 ** (attempt + 1)  # 2s e depois 4s
            print(
                f"Gemini temporariamente indisponível; nova tentativa "
                f"{attempt + 2}/3 em {wait_seconds}s..."
            )
            time.sleep(wait_seconds)

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



def analyze_lead_profiles(lead: dict[str, Any], profiles: list[str], custom_offer: str = "") -> dict[str, dict[str, Any]]:
    """Analisa uma empresa para um ou dois perfis comerciais em uma única chamada Gemini."""
    allowed = {"4k", "digital"}
    selected = [p for p in profiles if p in allowed]
    if not selected:
        raise ValueError("Selecione ao menos um perfil comercial.")

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key or api_key == "cole_sua_chave_aqui":
        raise RuntimeError("Configure GEMINI_API_KEY no arquivo .env antes de executar.")
    client = genai.Client(api_key=api_key)
    model_name = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")

    safe_lead = {
        "name": str(lead.get("name", ""))[:160],
        "category": str(lead.get("category", ""))[:160],
        "phone": str(lead.get("phone", ""))[:60],
        "address": str(lead.get("address", ""))[:220],
        "website": str(lead.get("website", ""))[:220],
        "instagram": str(lead.get("instagram", ""))[:220],
        "channels": [str(x)[:70] for x in (lead.get("channels") or [])][:12],
        "menu_url": str(lead.get("menu_url", ""))[:300],
        "menu_items": [str(x)[:90] for x in (lead.get("menu_items") or [])][:20],
        "public_platforms": [str(x)[:80] for x in (lead.get("public_platforms") or [])][:12],
        "research_notes": [str(x)[:160] for x in (lead.get("research_notes") or [])][:5],
    }
    profiles_text = []
    if "4k" in selected:
        profiles_text.append(
            '"4k": {"score": 0, "justificativa": "...", "mensagem": "..."} '
            '(fornecimento B2B da 4K Food Service: avalie apenas indícios públicos de aderência '
            'a distribuidor de alimentos; não invente volume de compra, fornecedores ou demanda)'
        )
    if "digital" in selected:
        profiles_text.append(
            '"digital": {"score": 0, "justificativa": "...", "mensagem": "..."} '
            '(serviços de presença digital: site, cardápio, pedidos online, redes sociais e atendimento)'
        )
    prompt = f"""
Você qualifica oportunidades B2B no Brasil usando apenas dados públicos. Não invente fatos.
Ausência de evidência pública não prova que a empresa não use uma ferramenta.
Mensagem respeitosa, curta (máximo 65 palavras), sem pressão, terminando em pergunta simples.
Use [NOME DA SUA EMPRESA] como marcador. Score de 0 a 100 é prioridade preliminar para revisão humana.
Oferta complementar informada pelo usuário: {custom_offer or "nenhuma"}
Empresa/dados públicos: {json.dumps(safe_lead, ensure_ascii=False)}
Retorne SOMENTE JSON válido, com estas chaves e nenhum texto fora do JSON:
{", ".join(profiles_text)}
"""
    response = None
    for attempt in range(3):
        try:
            response = client.models.generate_content(model=model_name, contents=prompt)
            break
        except Exception as exc:
            code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
            upper = str(exc).upper()
            transient = code in (429, 500, 502, 503, 504) or any(
                x in upper for x in ("429", "500", "502", "503", "504", "UNAVAILABLE", "RESOURCE_EXHAUSTED", "INTERNAL")
            )
            if not transient or attempt == 2:
                raise
            time.sleep((1, 2)[attempt] if attempt < 2 else 3)

    raw = (getattr(response, "text", "") or "").strip()
    raw = re.sub(r"^\s*```(?:json)?\s*|\s*```\s*$", "", raw, flags=re.I)
    try:
        data = json.loads(raw)
        result: dict[str, dict[str, Any]] = {}
        for profile in selected:
            item = data.get(profile)
            if not isinstance(item, dict) or not str(item.get("mensagem", "")).strip():
                raise ValueError(f"Resultado incompleto para o perfil {profile}")
            result[profile] = {
                "score": max(0, min(100, int(item.get("score", 0)))),
                "justificativa": str(item.get("justificativa", "")).strip(),
                "mensagem": str(item.get("mensagem", "")).strip(),
            }
        return result
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise RuntimeError(f"Resposta do Gemini inválida; tente novamente. Detalhe: {exc}") from exc
