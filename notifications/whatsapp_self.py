"""Notificações pelo WhatsApp Web para o grupo privado do proprietário."""
from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from threading import Lock
from urllib.parse import quote
import time

from playwright.sync_api import sync_playwright

_lock = Lock()
_last_failure_at = 0.0
_last_failure_message = ""
_playwright_instance = None
_context = None
_page = None


def _open_context(playwright):
    profile_dir = Path(os.getenv("WHATSAPP_PROFILE_DIR", "data/whatsapp_profile")).expanduser()
    profile_dir.mkdir(parents=True, exist_ok=True)
    return playwright.chromium.launch_persistent_context(
        user_data_dir=str(profile_dir.resolve()),
        headless=False,
        args=["--disable-notifications"],
        viewport={"width": 1280, "height": 900},
    )


def _get_whatsapp_page():
    """Abre o navegador uma vez e mantém o perfil/sessão vivos entre envios."""
    global _playwright_instance, _context, _page
    if _playwright_instance is None or _context is None or not _context.pages:
        if _playwright_instance is None:
            _playwright_instance = sync_playwright().start()
        _context = _open_context(_playwright_instance)
        _page = _context.pages[0] if _context.pages else _context.new_page()
    elif _page is None or _page.is_closed():
        _page = _context.pages[0] if _context.pages else _context.new_page()
    return _page


def send_to_group(message: str, group_name: str | None = None) -> tuple[bool, str]:
    """Envia UMA mensagem para o grupo configurado, mantendo a sessão do navegador aberta."""
    group = (group_name or os.getenv("WHATSAPP_GROUP_NAME", "Leads")).strip()
    if not message.strip():
        return False, "Mensagem vazia."
    if os.getenv("WHATSAPP_NOTIFICATIONS", "false").strip().lower() not in {"1", "true", "yes", "sim"}:
        return False, "Notificações WhatsApp desativadas."
    if not group:
        return False, "Configure WHATSAPP_GROUP_NAME no .env."

    global _last_failure_at, _last_failure_message
    if _last_failure_at and time.monotonic() - _last_failure_at < 60:
        return False, _last_failure_message or "WhatsApp indisponível; aguardando antes de tentar novamente."

    with _lock:
        try:
            page = _get_whatsapp_page()
            if not page.url.startswith("https://web.whatsapp.com"):
                page.goto("https://web.whatsapp.com/", wait_until="domcontentloaded", timeout=60000)

            # Aguarda pelo estado real da página: o WhatsApp muda seus seletores com frequência.
            # A busca pode ser um input ou um elemento contenteditable, conforme a versão da interface.
            try:
                page.locator("body").wait_for(state="visible", timeout=15000)
                page.wait_for_function(
                    """() => {
                        const text = (document.body?.innerText || '').toLowerCase();
                        return text.includes('pesquisar ou começar uma nova conversa')
                            || text.includes('search or start new chat')
                            || text.includes('escaneie o código qr')
                            || text.includes('scan the qr code')
                            || !!document.querySelector('canvas[aria-label*="QR"], [data-testid="qrcode"]');
                    }""",
                    timeout=45000
                )
            except Exception:
                try:
                    Path("data").mkdir(parents=True, exist_ok=True)
                    page.screenshot(path="data/whatsapp_load_error.png", full_page=True)
                except Exception:
                    pass
                _last_failure_at = time.monotonic()
                _last_failure_message = (
                    "WhatsApp Web abriu, mas não mostrou a lista de conversas nem a autenticação. "
                    "A janela foi mantida aberta; veja data/whatsapp_load_error.png."
                )
                return False, _last_failure_message

            body_text = (page.locator("body").inner_text(timeout=10000) or "").casefold()
            if ("qr code" in body_text or "código qr" in body_text) and (
                "pesquisar ou começar" not in body_text and "search or start new chat" not in body_text
            ):
                _last_failure_at = time.monotonic()
                _last_failure_message = (
                    "WhatsApp Web está pedindo autenticação. Escaneie o QR Code nesta janela; "
                    "a sessão será reutilizada nas próximas mensagens."
                )
                return False, _last_failure_message

            # Primeiro verifica se o grupo correto já está aberto; evita depender do seletor de busca.
            current_header = page.locator("header").inner_text(timeout=10000).casefold()
            if group.casefold() not in current_header:
                search_candidates = [
                    page.locator('div[contenteditable="true"][data-tab="3"]').first,
                    page.locator('div[contenteditable="true"][aria-label*="Pesquisar"]').first,
                    page.locator('div[contenteditable="true"][aria-label*="Search"]').first,
                    page.locator('button[aria-label*="Pesquisar"]').first,
                    page.locator('button[aria-label*="Search"]').first,
                ]
                search = None
                for candidate in search_candidates:
                    try:
                        if candidate.count() and candidate.is_visible():
                            search = candidate
                            break
                    except Exception:
                        continue
                if search is None:
                    _last_failure_at = time.monotonic()
                    _last_failure_message = "WhatsApp abriu, mas não encontrei o campo de pesquisa. Nenhuma mensagem foi enviada."
                    return False, _last_failure_message

                search.click(timeout=15000)
                try:
                    search.fill(group, timeout=10000)
                except Exception:
                    search.press("Control+A")
                    search.type(group, delay=80)
                page.wait_for_timeout(1800)

                exact_results = page.get_by_text(group, exact=True)
                if exact_results.count() == 0:
                    _last_failure_at = time.monotonic()
                    _last_failure_message = f"Não encontrei um chat com o nome exato '{group}'."
                    return False, _last_failure_message
                exact_results.last.click(timeout=15000)
                page.wait_for_timeout(1000)

                current_header = page.locator("header").inner_text(timeout=10000).casefold()
                if group.casefold() not in current_header:
                    _last_failure_at = time.monotonic()
                    _last_failure_message = f"Não consegui confirmar que o chat aberto é '{group}'. Nada foi enviado."
                    return False, _last_failure_message

            composer_candidates = [
                page.locator('footer div[contenteditable="true"]').last,
                page.locator('div[contenteditable="true"][aria-label*="Mensagem"]').last,
                page.locator('div[contenteditable="true"][aria-label*="Message"]').last,
            ]
            composer = None
            for candidate in composer_candidates:
                try:
                    if candidate.count() and candidate.is_visible():
                        composer = candidate
                        break
                except Exception:
                    continue
            if composer is None:
                _last_failure_at = time.monotonic()
                _last_failure_message = "O grupo foi aberto, mas não encontrei a caixa de mensagem. Nada foi enviado."
                return False, _last_failure_message
            composer.wait_for(timeout=15000)
            composer.fill(message[:10000])
            composer.press("Enter")
            page.wait_for_timeout(1000)
            _last_failure_at = 0.0
            _last_failure_message = ""
            return True, f"Mensagem enviada ao grupo '{group}'."
        except Exception as exc:
            logging.warning("Falha ao enviar notificação para grupo WhatsApp: %s", exc)
            _last_failure_at = time.monotonic()
            _last_failure_message = f"Falha no WhatsApp Web ({type(exc).__name__}); confira a sessão e o nome do grupo."
            return False, _last_failure_message


def send_to_self(message: str) -> tuple[bool, str]:
    """Compatibilidade com chamadas anteriores; as notificações vão ao grupo configurado."""
    return send_to_group(message)
