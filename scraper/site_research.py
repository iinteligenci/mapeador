"""Pesquisa complementar em páginas públicas dos negócios encontrados."""
from __future__ import annotations

import re
from collections import OrderedDict
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

PRODUCT_TERMS = {
    "bacon": ("bacon",),
    "costela suína": ("costela suína", "costela de porco", "costelinha suína"),
    "linguiça": ("linguiça", "linguica"),
    "lombo suíno": ("lombo suíno", "lombo de porco"),
    "copa-lombo": ("copa-lombo", "copa lombo"),
    "joelho suíno": ("joelho de porco", "joelho suíno", "eisbein"),
    "frango defumado": ("frango defumado",),
    "pé suíno": ("pé de porco", "pé suíno", "pé salgado"),
    "orelha suína": ("orelha de porco", "orelha suína"),
    "rabo suíno": ("rabo de porco", "rabo suíno"),
    "carré suíno": ("carré suíno", "carre suíno", "bisteca suína"),
    "torresmo": ("torresmo",),
}
CHANNEL_PATTERNS = OrderedDict([
    ("Instagram", ("instagram.com/",)),
    ("Facebook", ("facebook.com/", "fb.com/")),
    ("TikTok", ("tiktok.com/",)),
    ("YouTube", ("youtube.com/", "youtu.be/")),
    ("iFood", ("ifood.com.br/",)),
    ("WhatsApp", ("wa.me/", "api.whatsapp.com/", "whatsapp.com/")),
    ("Cardápio digital", ("cardapiodigital.io/", "menu.dish.co/", "anota.ai/", "saipos.com/")),
])


def _text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def research_public_site(lead: dict[str, Any], max_pages: int = 5) -> dict[str, Any]:
    """Inspeciona homepage e poucas páginas públicas; não faz login nem contorna bloqueios."""
    result: dict[str, Any] = {
        "address": str(lead.get("address") or ""),
        "instagram": str(lead.get("instagram") or ""),
        "channels": [],
        "menu_url": "",
        "catalog_url": "",
        "menu_products": [],
        "research_notes": [],
    }
    base = str(lead.get("website") or "").strip()
    if not base.startswith(("http://", "https://")):
        result["research_notes"].append("Site próprio não encontrado; pesquisa complementar limitada.")
        return result

    try:
        response = requests.get(
            base, timeout=12, headers={"User-Agent": "Mozilla/5.0 (compatible; MapeadorResearch/1.0)"}
        )
        response.raise_for_status()
        content_type = response.headers.get("content-type", "")
        if "text/html" not in content_type:
            result["research_notes"].append("O endereço do site não retornou uma página HTML pública.")
            return result
    except requests.RequestException as exc:
        result["research_notes"].append(f"Não foi possível consultar o site público ({type(exc).__name__}).")
        return result

    root = urlparse(response.url)
    root_host = root.netloc.lower().removeprefix("www.")
    to_visit: list[tuple[str, str]] = [(response.url, "home")]
    visited: set[str] = set()
    text_parts: list[str] = []
    found_channels: set[str] = set()
    menu_url = ""
    catalog_url = ""

    while to_visit and len(visited) < max_pages:
        url, kind = to_visit.pop(0)
        if url in visited:
            continue
        visited.add(url)
        try:
            page = requests.get(
                url, timeout=10,
                headers={"User-Agent": "Mozilla/5.0 (compatible; MapeadorResearch/1.0)"},
            )
            page.raise_for_status()
            if "text/html" not in page.headers.get("content-type", ""):
                continue
            soup = BeautifulSoup(page.text, "html.parser")
        except requests.RequestException:
            continue

        for node in soup(["script", "style", "noscript", "svg"]):
            node.decompose()
        page_text = _text(soup.get_text(" ", strip=True))
        if page_text:
            text_parts.append(page_text[:100000])

        for anchor in soup.find_all("a", href=True):
            href = urljoin(page.url, anchor.get("href", "").strip())
            parsed = urlparse(href)
            lowered = href.lower()
            label = _text(anchor.get_text(" ", strip=True)).lower()
            for channel, patterns in CHANNEL_PATTERNS.items():
                if any(pattern in lowered for pattern in patterns):
                    found_channels.add(channel)
                    if channel == "Instagram" and not result["instagram"]:
                        result["instagram"] = href
            if parsed.scheme in ("http", "https") and parsed.netloc.lower().removeprefix("www.") == root_host:
                if any(token in (lowered + " " + label) for token in ("cardap", "menu", "menu digital", "delivery")):
                    if not menu_url:
                        menu_url = href
                    if href not in visited and all(href != item[0] for item in to_visit):
                        to_visit.append((href, "menu"))
                if any(token in (lowered + " " + label) for token in ("catalog", "catálogo", "catalogo", "produto", "products")):
                    if not catalog_url:
                        catalog_url = href
                    if href not in visited and all(href != item[0] for item in to_visit):
                        to_visit.append((href, "catalog"))

        # Endereços às vezes estão publicados no rodapé/site.
        if not result["address"]:
            match = re.search(
                r"(?i)(?:endereço|endereco|localização|localizacao|av\.?|avenida|rua|rodovia|praça|praca)"
                r"[^.]{0,140}?\b\d{1,6}\b[^.]{0,100}",
                page_text,
            )
            if match:
                result["address"] = _text(match.group(0))[:220]

    combined_text = _text(" ".join(text_parts)).lower()
    detected: list[str] = []
    for product, phrases in PRODUCT_TERMS.items():
        if any(phrase in combined_text for phrase in phrases):
            detected.append(product)
    result["channels"] = sorted(found_channels)
    result["menu_url"] = menu_url
    result["catalog_url"] = catalog_url
    result["menu_products"] = detected
    if menu_url:
        result["research_notes"].append("Link de cardápio/menu localizado em página pública.")
    if catalog_url:
        result["research_notes"].append("Link de catálogo/produtos localizado em página pública.")
    if detected:
        result["research_notes"].append(
            "Produtos são indícios por palavras encontradas no texto público; confirmar no cardápio/catálogo original."
        )
    if not found_channels:
        result["research_notes"].append("Nenhum canal externo reconhecido nos links públicos do site.")
    return result
