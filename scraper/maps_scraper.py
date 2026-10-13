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


async def search_google_maps(term: str, limit: int = 10, exclude_links: set[str] | None = None) -> list[dict[str, str]]:
    """Retorna leads com nome, categoria, link, telefone, endereço e site quando disponíveis."""
    term = _clean(term)
    if not term:
        raise ValueError("O termo de pesquisa não pode estar vazio.")
    if limit < 1:
        raise ValueError("O limite deve ser maior que zero.")

    results: list[dict[str, str]] = []
    excluded = {str(link).split("?")[0].rstrip("/") for link in (exclude_links or set()) if link}
    # Read extra cards so duplicates in the local history do not consume the requested result count.
    scan_limit = min(60, max(limit * 5, limit + 10, len(excluded) + limit))
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(locale="pt-BR", viewport={"width": 1365, "height": 900})
        page = await context.new_page()
        try:
            await page.goto(f"https://www.google.com/maps/search/{quote_plus(term)}",
                            wait_until="domcontentloaded", timeout=35000)
            feed = page.locator('div[role="feed"]')
            try:
                await feed.wait_for(timeout=9000)
            except PlaywrightTimeoutError:
                logger.warning("Lista indisponível; o Maps pode ter mudado ou limitado o acesso.")
                return []

            previous = -1
            for _ in range(min(30, max(6, scan_limit // 2))):
                count = await feed.locator('div[role="article"]').count()
                if count >= scan_limit or count == previous:
                    break
                previous = count
                await feed.evaluate("(el) => el.scrollBy(0, el.clientHeight)")
                await page.wait_for_timeout(800)

            cards = await feed.locator('div[role="article"]').all()
            candidates: list[dict[str, str]] = []
            seen: set[str] = set()
            for card in cards:
                if len(candidates) >= scan_limit:
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
                    normalized_link = link.split("?")[0].rstrip("/")
                    if normalized_link in seen or normalized_link in excluded:
                        continue
                    seen.add(normalized_link)
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

            # Visit detail pages only for genuinely new establishments, keeping search faster.
            async def read_public_field(selectors: list[str], prefixes: tuple[str, ...]) -> str:
                """Try several stable attributes and visible text for a Maps detail field."""
                for selector in selectors:
                    locator = page.locator(selector).first
                    try:
                        if not await locator.count():
                            continue
                        for attribute in ("aria-label", "data-tooltip", "title"):
                            value = _clean(await locator.get_attribute(attribute, timeout=1800))
                            if value:
                                value = re.sub(
                                    r"^(?:" + "|".join(re.escape(p) for p in prefixes) + r")\s*:?[\s]*",
                                    "", value, flags=re.IGNORECASE
                                ).strip()
                                if value and value.casefold() not in {"telefone", "phone", "endereço", "address"}:
                                    return value
                        value = _clean(await locator.inner_text(timeout=1800))
                        if value:
                            value = re.sub(
                                r"^(?:" + "|".join(re.escape(p) for p in prefixes) + r")\s*:?[\s]*",
                                "", value, flags=re.IGNORECASE
                            ).strip()
                            if value and value.casefold() not in {"telefone", "phone", "endereço", "address"}:
                                return value
                    except Exception:
                        continue
                return ""

            for lead in candidates[:limit]:
                try:
                    await page.goto(lead["link"], wait_until="domcontentloaded", timeout=22000)
                    try:
                        await page.locator("h1").first.wait_for(timeout=7000)
                    except PlaywrightTimeoutError:
                        logger.debug("Título do estabelecimento não carregou: %s", lead["name"])
                    # Maps has changed the DOM over time; use several selector and text fallbacks.
                    lead["phone"] = await read_public_field(
                        [
                            'button[data-item-id^="phone:tel:"]',
                            '[data-item-id^="phone:tel:"]',
                            'button[aria-label*="Telefone"]',
                            'button[aria-label*="Phone"]',
                            '[data-tooltip*="Telefone"]',
                            '[data-tooltip*="Phone"]',
                        ],
                        ("Telefone", "Phone", "Ligar", "Call"),
                    )
                    lead["address"] = await read_public_field(
                        [
                            'button[data-item-id="address"]',
                            '[data-item-id="address"]',
                            'button[aria-label*="Endereço"]',
                            'button[aria-label*="Address"]',
                            '[data-tooltip*="Endereço"]',
                            '[data-tooltip*="Address"]',
                        ],
                        ("Endereço", "Address", "Copiar endereço", "Copy address"),
                    )
                    website_link = page.locator('a[data-item-id="authority"]').first
                    if await website_link.count():
                        lead["website"] = _clean(await website_link.get_attribute("href"))
                    menu_link = page.locator(
                        'a[data-item-id*="menu"], a[aria-label*="Cardápio"], a[aria-label*="Menu"]'
                    ).first
                    if await menu_link.count():
                        lead["menu_url"] = _clean(await menu_link.get_attribute("href"))
                except Exception as exc:
                    logger.debug("Detalhes incompletos para %s: %s", lead["name"], exc)
                results.append(lead)
        finally:
            await context.close()
            await browser.close()
    return results[:limit]
