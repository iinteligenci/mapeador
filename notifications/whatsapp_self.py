"""Envio de notificações para o próprio WhatsApp via WhatsApp Web.

Requer WHATSAPP_SELF_NUMBER (formato internacional, apenas dígitos).
Na primeira execução, faça login/escaneie o QR no navegador que abrir.
Uso restrito a notificações para o próprio usuário; não envia para leads.
"""
from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from threading import Lock
from urllib.parse import quote

from playwright.sync_api import sync_playwright

_lock = Lock()


def send_to_self(message: str) -> tuple[bool, str]:
    """Envia uma notificação para o próprio número; retorna status sem derrubar o Mapeador."""
    phone = re.sub(r"\D", "", os.getenv("WHATSAPP_SELF_NUMBER", ""))
    if not phone:
        return False, "Configure WHATSAPP_SELF_NUMBER no arquivo .env."
    if not message.strip():
        return False, "Mensagem vazia."
    if os.getenv("WHATSAPP_NOTIFICATIONS", "false").strip().lower() not in {"1", "true", "yes", "sim"}:
        return False, "Notificações WhatsApp desativadas; configure WHATSAPP_NOTIFICATIONS=true."
    if len(phone) < 12 or len(phone) > 15:
        return False, "WHATSAPP_SELF_NUMBER deve conter DDI + DDD + número, apenas dígitos."

    # Perfil separado e persistente: a sessão permanece conectada entre execuções.
    profile_dir = Path(os.getenv("WHATSAPP_PROFILE_DIR", "data/whatsapp_profile")).expanduser()
    profile_dir.mkdir(parents=True, exist_ok=True)
    url = f"https://web.whatsapp.com/send?phone={phone}&text={quote(message)}"

    with _lock:
        try:
            with sync_playwright() as playwright:
                context = playwright.chromium.launch_persistent_context(
                    user_data_dir=str(profile_dir.resolve()),
                    headless=False,
                    args=["--disable-notifications"],
                    viewport={"width": 1280, "height": 900},
                )
                try:
                    page = context.pages[0] if context.pages else context.new_page()
                    page.goto(url, wait_until="domcontentloaded", timeout=60000)
                    # A primeira execução pode exigir leitura do QR; dê tempo para login.
                    page.locator('div[contenteditable="true"]').first.wait_for(timeout=120000)
                    send_button = page.locator('button[aria-label="Enviar"], button[aria-label="Send"]')
                    if send_button.count():
                        send_button.last.click(timeout=15000)
                    else:
                        # Fallback para a caixa de mensagem do WhatsApp Web.
                        editable = page.locator('footer div[contenteditable="true"]').last
                        editable.press("Enter", timeout=15000)
                    page.wait_for_timeout(1200)
                    return True, "Notificação enviada para seu WhatsApp."
                finally:
                    context.close()
        except Exception as exc:
            logging.warning("Falha ao enviar notificação ao próprio WhatsApp: %s", exc)
            return False, f"Não foi possível enviar pelo WhatsApp Web ({type(exc).__name__}). Confira o login e tente novamente."
