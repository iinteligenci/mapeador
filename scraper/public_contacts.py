"""Encontra contatos comerciais explicitamente publicados em páginas públicas."""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; MapeadorResearch/1.0)"}
MAX_PAGES = 6
PHONE_RE = re.compile(r"(?:\+?55\s*)?(?:\(?\d{2}\)?\s*)?(?:9\s*)?\d{4}[-.\s]?\d{4}")
ROLE_RE = re.compile(
    r"(?i)\b(propriet[aá]ri[oa]|fundador[a]?|s[oó]ci[oa](?:-fundador[a]?)?|"
    r"gerente de compras|respons[aá]vel por compras|comprador[a]?|"
    r"respons[aá]vel por suprimentos|gerente|diretor[a]?)\b"
)
NAME_RE = re.compile(r"(?i)\b(?:propriet[aá]ri[oa]|fundador[a]?|s[oó]ci[oa]|comprador[a]?|gerente)\s*[:\-–]\s*([A-ZÀ-Ú][\wÀ-ÿ'’-]+(?:\s+[A-ZÀ-Ú][\wÀ-ÿ'’-]+){1,4})")


def _clean(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def find_public_business_contacts(lead: dict[str, Any], max_pages: int = MAX_PAGES) -> dict[str, Any]:
    """Inspeciona apenas páginas públicas da própria empresa; não infere nem adivinha contatos."""
    result: dict[str, Any] = {
        "contact_name": "",
        "contact_role": "",
        "contact_phone": "",
        "contact_whatsapp": "",
        "contact_source": "",
        "contact_confidence": "Não identificado",
        "contact_notes": [],
        "contact_sources": [],
    }
    base = str(lead.get("website") or "").strip()
    if not base.startswith(("https://", "http://")):
        # Preserve a publicly listed Maps business phone, but never label it as a person's direct number.
        maps_phone = _clean(str(lead.get("phone") or ""))
        if maps_phone:
            result["contact_phone"] = maps_phone
            result["contact_source"] = str(lead.get("link") or "")
            result["contact_confidence"] = "Telefone comercial listado no Google Maps"
        result["contact_notes"].append(
            "Site próprio não identificado. Nenhum contato direto de decisor foi atribuído; o telefone, se exibido, é apenas o contato comercial público do estabelecimento."
        )
        return result

    try:
        parsed_base = urlparse(base)
        root_host = parsed_base.netloc.lower().removeprefix("www.")
        first = requests.get(base, headers=HEADERS, timeout=8)
        first.raise_for_status()
        if "text/html" not in first.headers.get("content-type", "").lower():
            result["contact_notes"].append("O site não disponibilizou HTML público para consulta.")
            return result
    except requests.RequestException:
        result["contact_notes"].append("Não foi possível consultar o site público.")
        return result

    queue: list[str] = [first.url]
    visited: set[str] = set()
    phones: list[tuple[str, str]] = []
    whatsapps: list[tuple[str, str]] = []
    role_candidates: list[tuple[str, str, str]] = []

    while queue and len(visited) < max(1, min(max_pages, 8)):
        url = queue.pop(0)
        if url in visited:
            continue
        visited.add(url)
        try:
            response = requests.get(url, headers=HEADERS, timeout=7)
            response.raise_for_status()
            if "text/html" not in response.headers.get("content-type", "").lower():
                continue
            soup = BeautifulSoup(response.text, "html.parser")
        except requests.RequestException:
            continue

        result["contact_sources"].append(response.url)
        text = _clean(soup.get_text(" ", strip=True))
        for match in NAME_RE.finditer(text):
            name = _clean(match.group(1))
            start = max(0, match.start() - 100)
            context = text[start:match.end() + 60]
            role_match = ROLE_RE.search(context)
            if role_match:
                role_candidates.append((name, _clean(role_match.group(1)), response.url))

        for anchor in soup.find_all("a", href=True):
            href = _clean(anchor.get("href"))
            label = _clean(anchor.get_text(" ", strip=True))
            absolute = urljoin(response.url, href)
            low = absolute.lower()
            if low.startswith("tel:"):
                number = re.sub(r"^tel:", "", absolute, flags=re.I).strip()
                if number:
                    phones.append((number, response.url))
            if "wa.me/" in low or "api.whatsapp.com/send" in low or "whatsapp.com/send" in low:
                digits = re.search(r"(?:wa\.me/|phone=)(\+?\d{8,15})", absolute, re.I)
                if digits:
                    whatsapps.append((digits.group(1), response.url))
            if urlparse(absolute).netloc.lower().removeprefix("www.") == root_host:
                path = urlparse(absolute).path.lower()
                if any(word in (path + " " + label.lower()) for word in (
                    "contato", "contact", "equipe", "team", "sobre", "about", "empresa", "compras"
                )) and absolute.startswith(("https://", "http://")) and absolute not in visited and absolute not in queue:
                    queue.append(absolute)

        # Extract phone numbers from visible text only when presented on the company website.
        for match in PHONE_RE.finditer(text):
            number = _clean(match.group(0))
            digits = re.sub(r"\D", "", number)
            if len(digits) >= 10:
                phones.append((number, response.url))

    def unique(items: list[tuple[str, str]]) -> list[tuple[str, str]]:
        seen: set[str] = set()
        out: list[tuple[str, str]] = []
        for value, source in items:
            key = re.sub(r"\D", "", value)
            if key and key not in seen:
                seen.add(key)
                out.append((value, source))
        return out

    phones = unique(phones)
    whatsapps = unique(whatsapps)
    if role_candidates:
        result["contact_name"], result["contact_role"], source = role_candidates[0]
        result["contact_source"] = source
        result["contact_confidence"] = "Nome/cargo publicado"
    if whatsapps:
        result["contact_whatsapp"], source = whatsapps[0]
        result["contact_sources"].append(source)
    if phones:
        result["contact_phone"], source = phones[0]
        if not result["contact_source"]:
            result["contact_source"] = source
        if result["contact_confidence"] == "Não identificado":
            result["contact_confidence"] = "Telefone comercial publicado"
    if not result["contact_name"]:
        result["contact_notes"].append(
            "Nome e cargo do decisor não foram encontrados nas páginas examinadas. Os telefones encontrados são contatos publicados pela empresa e não foram atribuídos a uma pessoa."
        )
    if not result["contact_phone"] and not result["contact_whatsapp"]:
        result["contact_notes"].append("Nenhum telefone ou WhatsApp foi identificado nas páginas públicas examinadas.")
    result["contact_sources"] = list(dict.fromkeys(result["contact_sources"]))
    return result
