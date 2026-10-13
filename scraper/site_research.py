"""Pesquisa pública simples: canais digitais, cardápio e ferramentas visíveis."""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; MapeadorResearch/1.0)"}
CHANNELS = {
    "Instagram": ("instagram.com/",),
    "Facebook": ("facebook.com/", "fb.com/"),
    "TikTok": ("tiktok.com/",),
    "WhatsApp": ("wa.me/", "api.whatsapp.com/", "whatsapp.com/"),
    "iFood": ("ifood.com.br/",),
    "Delivery/ pedido online": ("anota.ai/", "goomer.app/", "cardapioweb.com/", "saipos.com/"),
    "Reservas online": ("reserva.chef/", "getinapp.com.br/", "tagme.com.br/"),
}
PLATFORMS = (
    "Saipos", "Consumer", "Goomer", "Anota AI", "GrandChef", "Kyte",
    "MarketUP", "Linx", "Omie", "Conta Azul", "Tagme", "Get In",
)
MENU_WORDS = ("cardápio", "cardapio", "menu", "delivery", "pedidos", "produtos", "catálogo", "catalogo")


def _clean(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _is_html(response: requests.Response) -> bool:
    return "text/html" in response.headers.get("content-type", "").lower()


def research_public_site(lead: dict[str, Any], max_pages: int = 5) -> dict[str, Any]:
    """Lê páginas públicas do site, sem login, sem contornar bloqueios e sem inventar dados."""
    result: dict[str, Any] = {
        "address": str(lead.get("address") or ""),
        "instagram": "",
        "channels": [],
        "menu_url": "",
        "menu_items": [],
        "public_platforms": [],
        "research_notes": [],
        "sources": [],
    }
    base = str(lead.get("website") or "").strip()
    if not base.startswith(("http://", "https://")):
        result["research_notes"].append("Site próprio não localizado; não foi possível analisar páginas do estabelecimento.")
        return result

    try:
        first = requests.get(base, timeout=12, headers=HEADERS)
        first.raise_for_status()
        if not _is_html(first):
            result["research_notes"].append("O site não disponibilizou uma página HTML pública para leitura.")
            return result
    except requests.RequestException as exc:
        result["research_notes"].append(f"Falha ao consultar o site público ({type(exc).__name__}).")
        return result

    root_host = urlparse(first.url).netloc.lower().removeprefix("www.")
    queue = [first.url]
    visited: set[str] = set()
    channel_set: set[str] = set()
    platforms: set[str] = set()
    menu_items: list[str] = []
    menu_url = ""
    all_text: list[str] = []

    while queue and len(visited) < max(1, min(max_pages, 8)):
        url = queue.pop(0)
        if url in visited:
            continue
        visited.add(url)
        try:
            response = requests.get(url, timeout=10, headers=HEADERS)
            response.raise_for_status()
            if not _is_html(response):
                continue
            soup = BeautifulSoup(response.text, "html.parser")
        except requests.RequestException:
            continue

        for node in soup(["script", "style", "noscript", "svg", "iframe"]):
            node.decompose()
        page_text = _clean(soup.get_text(" ", strip=True))
        if page_text:
            all_text.append(page_text[:80000])
        result["sources"].append(response.url)

        for anchor in soup.find_all("a", href=True):
            href = urljoin(response.url, anchor.get("href", "").strip())
            lowered = href.lower()
            label = _clean(anchor.get_text(" ", strip=True))
            for channel, patterns in CHANNELS.items():
                if any(pattern in lowered for pattern in patterns):
                    channel_set.add(channel)
                    if channel == "Instagram" and not result["instagram"]:
                        result["instagram"] = href
            if any(token in (lowered + " " + label.lower()) for token in MENU_WORDS):
                if not menu_url:
                    menu_url = href
                parsed = urlparse(href)
                if (parsed.scheme in ("http", "https")
                    and parsed.netloc.lower().removeprefix("www.") == root_host
                    and href not in visited and href not in queue):
                    queue.append(href)

        for node in soup.find_all(["h2", "h3", "h4", "li"]):
            label = _clean(node.get_text(" ", strip=True))
            if 2 <= len(label) <= 90 and not re.search(r"(?i)privacidade|cookies|política|contato|sobre nós|sobre nos|início|inicio", label):
                if label not in menu_items:
                    menu_items.append(label)

    combined = _clean(" ".join(all_text)).lower()
    for platform in PLATFORMS:
        if platform.lower() in combined:
            platforms.add(platform)

    result["channels"] = sorted(channel_set)
    result["menu_url"] = menu_url
    result["menu_items"] = menu_items[:40]
    result["public_platforms"] = sorted(platforms)
    if not menu_url:
        result["research_notes"].append("Não foi localizado um link claro de cardápio ou catálogo no site.")
    if not menu_items:
        result["research_notes"].append("Não foram extraídos itens legíveis de cardápio; o conteúdo pode ser imagem, PDF ou carregado por JavaScript.")
    else:
        result["research_notes"].append("Itens listados são textos encontrados em páginas públicas; confira a fonte antes de usar.")
    if not channel_set:
        result["research_notes"].append("Nenhum canal externo foi identificado nos links públicos examinados.")
    if not platforms:
        result["research_notes"].append("Nenhuma plataforma de gestão foi identificada publicamente. Isso não significa que a empresa não use uma.")
    return result
