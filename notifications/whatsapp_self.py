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


def _open_context(playwright):
    profile_dir = Path(os.getenv("WHATSAPP_PROFILE_DIR", "data/whatsapp_profile")).expanduser()
    profile_dir.mkdir(parents=True, exist_ok=True)
    return playwright.chromium.launch_persistent_context(
        user_data_dir=str(profile_dir.resolve()),
        headless=False,
        args=["--disable-notifications"],
        viewport={"width": 1280, "height": 900},
    )


def send_to_group(message: str, group_name: str | None = None) -> tuple[bool, str]:
    """Envia UMA mensagem para o grupo configurado, nunca para os leads."""
    group = (group_name or os.getenv("WHATSAPP_GROUP_NAME", "lembrar")).strip()
    if not message.strip():
        return False, "Mensagem vazia."
    if os.getenv("WHATSAPP_NOTIFICATIONS", "false").strip().lower() not in {"1", "true", "yes", "sim"}:
        return False, "Notificações WhatsApp desativadas."
    if not group:
        return False, "Configure WHATSAPP_GROUP_NAME no .env."

    global _last_failure_at, _last_failure_message
    if _last_failure_at and time.monotonic() - _last_failure_at < 300:
        return False, _last_failure_message or "WhatsApp indisponível; aguardando antes de tentar novamente."

    with _lock:
        try:
            with sync_playwright() as playwright:
                context = _open_context(playwright)
                try:
                    page = context.pages[0] if context.pages else context.new_page()
                    page.goto("https://web.whatsapp.com/", wait_until="domcontentloaded", timeout=60000)
                    # Aguarda o aplicativo carregar e identifica se a sessão pede QR/login.
                    try:
                        page.locator(
                            'div[contenteditable="true"], canvas[aria-label*="Scan"], '
                            'canvas[aria-label*="QR"], [data-testid="qrcode"], '
                            'text="Use o WhatsApp no seu celular para escanear o código QR"'
                        ).first.wait_for(timeout=45000)
                    except Exception:
                        page.screenshot(path="data/whatsapp_load_error.png", full_page=True)
                        _last_failure_at = time.monotonic()
                        _last_failure_message = (
                            "WhatsApp Web não carregou a tela de conversa nem o QR Code em 45 segundos. "
                            "Veja data/whatsapp_load_error.png e abra https://web.whatsapp.com/ no navegador."
                        )
                        return False, _last_failure_message

                    editable = page.locator('div[contenteditable="true"]')
                    if editable.count() == 0:
                        _last_failure_at = time.monotonic()
                        _last_failure_message = (
                            "WhatsApp Web está pedindo autenticação. Escaneie o QR Code na janela do navegador "
                            "que abriu para o Mapeador e tente novamente."
                        )
                        return False, _last_failure_message

                    search = page.locator(
                        'div[contenteditable="true"][data-tab="3"], '
                        'div[contenteditable="true"][aria-label*="Pesquisar"], '
                        'div[contenteditable="true"][aria-label*="Search"]'
                    ).first
                    search.click(timeout=15000)
                    search.fill(group)
                    page.wait_for_timeout(1200)

                    # Clique apenas no resultado com o nome exato do grupo.
                    exact_results = page.get_by_text(group, exact=True)
                    if exact_results.count() == 0:
                        _last_failure_at = time.monotonic()
                        _last_failure_message = f"Não encontrei um chat com o nome exato '{group}'."
                        return False, _last_failure_message
                    exact_results.last.click(timeout=15000)
                    page.wait_for_timeout(800)

                    # Confirma que o chat selecionado tem o título esperado, para não enviar ao chat errado.
                    title = page.locator('header span[title]').all()
                    title_values = []
                    for item in title:
                        try:
                            value = item.get_attribute("title")
                            if value:
                                title_values.append(value.strip())
                        except Exception:
                            pass
                    if group.casefold() not in {value.casefold() for value in title_values}:
                        _last_failure_at = time.monotonic()
                        _last_failure_message = f"Não consegui confirmar que o chat aberto é '{group}'. Nada foi enviado."
                        return False, _last_failure_message

                    composer = page.locator('footer div[contenteditable="true"]').last
                    composer.wait_for(timeout=15000)
                    composer.fill(message[:10000])
                    composer.press("Enter")
                    page.wait_for_timeout(1000)
                    _last_failure_at = 0.0
                    _last_failure_message = ""
                    return True, f"Mensagem enviada ao grupo '{group}'."
                finally:
                    context.close()
        except Exception as exc:
            logging.warning("Falha ao enviar notificação para grupo WhatsApp: %s", exc)
            _last_failure_at = time.monotonic()
            _last_failure_message = f"Falha no WhatsApp Web ({type(exc).__name__}); confira a sessão e o nome do grupo."
            return False, _last_failure_message


def send_to_self(message: str) -> tuple[bool, str]:
    """Compatibilidade com chamadas anteriores; as notificações vão ao grupo configurado."""
    return send_to_group(message)
