"""Coleta experimental de informações comerciais públicas do Google Maps.

O Google pode alterar a página e os seletores. Não contorna CAPTCHA, login,
bloqueios ou controles de acesso. Para produção, avalie a Google Maps Platform
Places API e respeite os termos aplicáveis.
"""
from __future__ import annotations

import logging
import re
from urllib.parse import quote_plus

from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)


def _clean(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


async def search_google_maps(term: str, limit: int = 10) -> list[dict[str, str]]:
    """Pesquisa empresas e tenta extrair nome, categoria, telefone e site.

    A extração de telefone/site abre cada resultado para ler o painel de detalhes.
    Retorna dicionários com name, category, link, phone e website.
    """
    term = _clean(term)
    if not term:
        raise ValueError("O termo de pesquisa não pode estar vazio.")
    if limit < 1:
        raise ValueError("O limite deve ser maior que zero.")

    results: list[dict[str, str]] = []
    seen: set[str] = set()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(locale="pt-BR", viewport={"width": 1365, "height": 900})
        page = await context.new_page()
        try:
            await page.goto(
                f"https://www.google.com/maps/search/{quote_plus(term)}",
                wait_until="domcontentloaded",
                timeout=60000,
            )
            feed = page.locator('div[role="feed"]')
            try:
                await feed.wait_for(timeout=15000)
            except PlaywrightTimeoutError:
                logger.warning("Lista de resultados indisponível. O Maps pode ter mudado ou limitado o acesso.")
                return []

            previous = -1
            for _ in range(min(20, max(4, limit * 2))):
                cards = await feed.locator('div[role="article"]').count()
                if cards >= limit or cards == previous:
                    break
                previous = cards
                await feed.evaluate("(el) => el.scrollBy(0, el.clientHeight)")
                await page.wait_for_timeout(800)

            cards = await feed.locator('div[role="article"]').all()
            for card in cards:
                if len(results) >= limit:
                    break
                try:
                    anchor = card.locator('a[href*="/maps/place/"]').first
                    link = _clean(await anchor.get_attribute("href", timeout=2500))
                    name = _clean(await anchor.get_attribute("aria-label", timeout=2500))
                    lines = [ _clean(x) for x in (await card.inner_text(timeout=2500)).splitlines() if _clean(x) ]
                    if not name and lines:
                        name = lines[0]
                    if not link or not name:
                        continue
                    if link.startswith("/"):
                        link = "https://www.google.com" + link
                    if link in seen:
                        continue
                    seen.add(link)

                    category = ""
                    for line in lines[1:]:
                        low = line.lower()
                        if (len(line) <= 90 and not any(x in low for x in (
                            "★", "estrelas", "avaliaç", "aberto", "fechado", " km", "min",
                            " R$", "·", "visualizações"
                        ))):
                            category = line
                            break

                    lead = {"name": name, "category": category or "Não identificada",
                            "link": link, "phone": "", "website": ""}
                    # Abrir o cartão para tentar ler os campos do painel de detalhes.
                    await anchor.click(timeout=3000)
                    await page.wait_for_timeout(700)
                    try:
                        phone_button = page.locator('button[data-item-id^="phone:tel:"]').first
                        if await phone_button.count():
                            label = await phone_button.get_attribute("aria-label")
                            lead["phone"] = _clean(label).replace("Telefone:", "").replace("Phone:", "")
                    except Exception as exc:
                        logger.debug("Telefone não disponível para %s: %s", name, exc)
                    try:
                        website_link = page.locator('a[data-item-id="authority"]').first
                        if await website_link.count():
                            lead["website"] = _clean(await website_link.get_attribute("href"))
                    except Exception as exc:
                        logger.debug("Site não disponível para %s: %s", name, exc)

                    results.append(lead)
                    # Voltar à lista de resultados, quando possível.
                    try:
                        await page.go_back(wait_until="domcontentloaded", timeout=8000)
                        await feed.wait_for(timeout=5000)
                    except Exception:
                        # O próximo cartão ainda pode ser clicável; a estrutura varia conforme o Maps.
                        logger.debug("Não foi possível voltar à lista após %s", name)
                except Exception as exc:
                    logger.debug("Resultado ignorado: %s", exc)
                    continue
        finally:
            await context.close()
            await browser.close()

    return results[:limit]
