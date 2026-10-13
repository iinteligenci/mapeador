"""Coleta experimental de informações comerciais públicas do Google Maps.

Os seletores podem mudar. Não contorna CAPTCHA, login, bloqueios ou controles
de acesso. Para uso comercial contínuo, avalie a Google Maps Platform Places API
e respeite os termos aplicáveis.
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
    """Retorna leads com nome, categoria, link, telefone, endereço e site quando disponíveis."""
    term = _clean(term)
    if not term:
        raise ValueError("O termo de pesquisa não pode estar vazio.")
    if limit < 1:
        raise ValueError("O limite deve ser maior que zero.")

    results: list[dict[str, str]] = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(locale="pt-BR", viewport={"width": 1365, "height": 900})
        page = await context.new_page()
        try:
            await page.goto(f"https://www.google.com/maps/search/{quote_plus(term)}",
                            wait_until="domcontentloaded", timeout=60000)
            feed = page.locator('div[role="feed"]')
            try:
                await feed.wait_for(timeout=15000)
            except PlaywrightTimeoutError:
                logger.warning("Lista indisponível; o Maps pode ter mudado ou limitado o acesso.")
                return []

            previous = -1
            for _ in range(min(20, max(4, limit * 2))):
                count = await feed.locator('div[role="article"]').count()
                if count >= limit or count == previous:
                    break
                previous = count
                await feed.evaluate("(el) => el.scrollBy(0, el.clientHeight)")
                await page.wait_for_timeout(800)

            cards = await feed.locator('div[role="article"]').all()
            candidates: list[dict[str, str]] = []
            seen: set[str] = set()
            for card in cards:
                if len(candidates) >= limit:
                    break
                try:
                    anchor = card.locator('a[href*="/maps/place/"]').first
                    link = _clean(await anchor.get_attribute("href", timeout=2500))
                    name = _clean(await anchor.get_attribute("aria-label", timeout=2500))
                    lines = [_clean(x) for x in (await card.inner_text(timeout=2500)).splitlines() if _clean(x)]
                    if not name and lines:
                        name = lines[0]
                    if not name or not link:
                        continue
                    if link.startswith("/"):
                        link = "https://www.google.com" + link
                    if link in seen:
                        continue
                    seen.add(link)
                    category = ""
                    for line in lines[1:]:
                        low = line.lower()
                        if len(line) <= 90 and not any(token in low for token in (
                            "★", "estrelas", "avaliaç", "aberto", "fechado", " km", "min",
                            " r$", "·", "visualizações"
                        )):
                            category = line
                            break
                    candidates.append({
                        "name": name, "category": category or "Não identificada",
                        "link": link, "phone": "", "address": "", "website": "",
                    })
                except Exception as exc:
                    logger.debug("Cartão ignorado: %s", exc)

            for lead in candidates:
                try:
                    await page.goto(lead["link"], wait_until="domcontentloaded", timeout=30000)
                    for selector, field in [
                        ('button[data-item-id^="phone:tel:"]', "phone"),
                        ('button[data-item-id="address"]', "address"),
                    ]:
                        element = page.locator(selector).first
                        if await element.count():
                            label = _clean(await element.get_attribute("aria-label"))
                            if field == "phone":
                                lead[field] = label.replace("Telefone:", "").replace("Phone:", "").strip()
                            else:
                                lead[field] = label.replace("Endereço:", "").replace("Address:", "").strip()
                    website_link = page.locator('a[data-item-id="authority"]').first
                    if await website_link.count():
                        lead["website"] = _clean(await website_link.get_attribute("href"))
                except Exception as exc:
                    logger.debug("Detalhes incompletos para %s: %s", lead["name"], exc)
                results.append(lead)
        finally:
            await context.close()
            await browser.close()
    return results[:limit]
