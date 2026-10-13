"""Coleta básica de resultados públicos do Google Maps usando Playwright.

Observação: seletores e estrutura do Google Maps mudam com frequência. Para uso
comercial em escala, prefira a Google Maps Platform Places API e respeite os
termos de uso, robots/restrições aplicáveis e limites de requisição.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any
from urllib.parse import quote_plus

from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)


async def search_google_maps(term: str, limit: int = 10) -> list[dict[str, str]]:
    """Pesquisa um termo no Maps e retorna até *limit* leads.

    Cada lead contém name, link e category. A função não tenta contornar CAPTCHA,
    login, bloqueios ou outras medidas de acesso.
    """
    if not term or not term.strip():
        raise ValueError("O termo de pesquisa não pode estar vazio.")
    if limit < 1:
        raise ValueError("O limite deve ser maior que zero.")

    results: list[dict[str, str]] = []
    seen_links: set[str] = set()
    url = f"https://www.google.com/maps/search/{quote_plus(term.strip())}"

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            locale="pt-BR",
            viewport={"width": 1365, "height": 900},
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
            ),
        )
        page = await context.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            try:
                await page.locator('div[role="feed"]').wait_for(timeout=15000)
            except PlaywrightTimeoutError:
                logger.warning("A lista de resultados não apareceu; o Maps pode ter bloqueado ou mudado.")
                return []

            feed = page.locator('div[role="feed"]')
            previous_count = -1
            # Rola a lista com limite de tentativas para não ficar presa em loop.
            for _ in range(min(limit * 2, 20)):
                cards = await feed.locator('div[role="article"]').all()
                if len(cards) >= limit or len(cards) == previous_count:
                    break
                previous_count = len(cards)
                await feed.evaluate("(el) => el.scrollBy(0, el.clientHeight)")
                await page.wait_for_timeout(900)

            cards = await feed.locator('div[role="article"]').all()
            for card in cards:
                if len(results) >= limit:
                    break
                try:
                    link_el = card.locator('a[href*="/maps/place/"]').first
                    link = await link_el.get_attribute("href", timeout=2000)
                    name = (await link_el.get_attribute("aria-label", timeout=2000) or "").strip()
                    if not name:
                        name = (await card.inner_text(timeout=2000)).splitlines()[0].strip()
                    if not link or not name:
                        continue
                    if link.startswith("/"):
                        link = "https://www.google.com" + link
                    if link in seen_links:
                        continue
                    seen_links.add(link)

                    lines = [line.strip() for line in (await card.inner_text(timeout=2000)).splitlines() if line.strip()]
                    category = ""
                    for line in lines[1:]:
                        # Heurística simples: primeira linha curta que não parece avaliação/horário/endereço.
                        lowered = line.lower()
                        if (
                            line != name
                            and len(line) <= 80
                            and not any(token in lowered for token in ("★", "estrelas", "aberto", "fechado", "km", " R$", "avaliaç"))
                        ):
                            category = line
                            break
                    results.append({"name": name, "link": link, "category": category or "Não identificada"})
                except (PlaywrightTimeoutError, Exception) as exc:
                    logger.debug("Resultado ignorado durante a extração: %s", exc)
                    continue
        finally:
            await context.close()
            await browser.close()

    return results[:limit]


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    found = asyncio.run(search_google_maps("restaurantes em Vitória ES", 5))
    for item in found:
        print(item)
