"""Notificações pelo WhatsApp Web para o grupo privado do proprietário."""
from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from threading import Event, Lock, Thread
from queue import Queue

from playwright.sync_api import sync_playwright

_lock = Lock()
_last_failure_at = 0.0
_last_failure_message = ""
_playwright_instance = None
_context = None
_page = None
_send_queue: Queue = Queue()
_sender_thread = None
_sender_start_lock = Lock()


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


def _visible_first(candidates):
    for candidate in candidates:
        try:
            if candidate.count() and candidate.first.is_visible():
                return candidate.first
        except Exception:
            continue
    return None


def _read_current_chat_header(page) -> str:
    """Lê somente o cabeçalho do painel da conversa, tolerando mudanças no DOM."""
    selectors = [
        '[data-testid="conversation-header"]',
        '[data-testid="conversation-panel-wrapper"] header',
        '#main header',
        'header',
    ]
    for selector in selectors:
        try:
            nodes = page.locator(selector)
            for index in range(min(nodes.count(), 4)):
                value = nodes.nth(index).inner_text(timeout=1500).strip()
                if value:
                    return value.casefold()
        except Exception:
            continue
    return ""


def _save_diagnostic(page, exc) -> str:
    try:
        Path("data").mkdir(parents=True, exist_ok=True)
        page.screenshot(path="data/whatsapp_load_error.png", full_page=True)
        body = (page.locator("body").inner_text(timeout=2500) or "")[:700].replace("\n", " ")
        detail = (
            f"url={page.url}\ntitle={page.title()}\n"
            f"error={type(exc).__name__}: {exc}\nbody={body}"
        )
        Path("data/whatsapp_load_error.txt").write_text(detail, encoding="utf-8")
        return detail
    except Exception as diag_exc:
        return f"diagnóstico indisponível: {type(diag_exc).__name__}: {diag_exc}"


def _find_search_box(page):
    """Localiza a pesquisa lateral tanto na interface antiga quanto na nova do WhatsApp Web."""
    return _visible_first([
        page.locator('[data-testid="chat-list-search"]'),
        page.locator('[data-testid="chat-list-search-input"]'),
        page.locator('#side input[placeholder*="Pesquisar"]'),
        page.locator('#side input[placeholder*="Search"]'),
        page.locator('#side input[aria-label*="Pesquisar"]'),
        page.locator('#side input[aria-label*="Search"]'),
        page.locator('#side div[contenteditable="true"][role="textbox"]'),
        page.locator('#side div[contenteditable="true"]'),
        page.locator('[role="textbox"][contenteditable="true"][data-tab="3"]'),
        page.locator('div[contenteditable="true"][data-tab="3"]'),
        page.locator('div[contenteditable="true"][aria-label*="Pesquisar"]'),
        page.locator('div[contenteditable="true"][aria-label*="Search"]'),
        page.locator('input[placeholder*="Pesquisar"]'),
        page.locator('input[placeholder*="Search"]'),
        page.locator('input[aria-label*="Pesquisar"]'),
        page.locator('input[aria-label*="Search"]'),
    ])


def _activate_search(page):
    """Expande a pesquisa se a versão do WhatsApp mostrar somente o botão/lupa."""
    search = _find_search_box(page)
    if search is not None:
        try:
            tag = search.evaluate("(el) => el.tagName.toLowerCase()")
            if tag not in {"button", "svg"}:
                return search
        except Exception:
            return search

    button = _visible_first([
        page.locator('button[aria-label*="Pesquisar"]'),
        page.locator('button[aria-label*="Search"]'),
        page.locator('[data-testid="chat-list-search"] button'),
        page.locator('#side button[title*="Pesquisar"]'),
        page.locator('#side button[title*="Search"]'),
        page.locator('#side [role="button"][aria-label*="Pesquisar"]'),
        page.locator('#side [role="button"][aria-label*="Search"]'),
    ])
    if button is not None:
        try:
            button.click(timeout=4000)
            page.wait_for_timeout(500)
        except Exception:
            pass

    search = _find_search_box(page)
    if search is not None:
        return search

    # Atalho de pesquisa do WhatsApp Web; depois dele, reconsulta os campos.
    try:
        page.keyboard.press("Control+f")
        page.wait_for_timeout(500)
    except Exception:
        pass
    return _find_search_box(page)


def _open_target_group(page, group: str) -> tuple[bool, str]:
    current_header = _read_current_chat_header(page)
    if group.casefold() in current_header:
        return True, ""

    search = _activate_search(page)
    if search is None:
        diagnostic = _save_diagnostic(page, RuntimeError("campo de pesquisa não localizado"))
        logging.warning("Mapeador WhatsApp: pesquisa não localizada. %s", diagnostic[:700])
        return False, (
            "WhatsApp abriu, mas não encontrei a pesquisa de conversas. "
            "Salvei um diagnóstico em data/whatsapp_load_error.txt para identificar a interface aberta."
        )

    try:
        search.click(timeout=8000)
        try:
            search.fill(group, timeout=5000)
        except Exception:
            try:
                search.press("Control+A")
                search.type(group, delay=60)
            except Exception:
                # Alguns campos modernos só aceitam inserção via teclado após focar.
                page.keyboard.press("Control+A")
                page.keyboard.type(group, delay=60)
        page.wait_for_timeout(1800)

        # Prioriza o painel lateral para não clicar em texto de outra área da página.
        result_candidates = [
            page.locator('#pane-side').get_by_text(group, exact=True),
            page.locator('[data-testid="chat-list"]').get_by_text(group, exact=True),
            page.locator('[data-testid="chatlist"]').get_by_text(group, exact=True),
            page.get_by_text(group, exact=True),
        ]
        result = _visible_first(result_candidates)
        if result is None:
            return False, f"Não encontrei resultado visível para o grupo '{group}'. Confira o nome exato no WhatsApp."

        result.click(timeout=10000)
        page.wait_for_timeout(1200)
        current_header = _read_current_chat_header(page)
        if group.casefold() not in current_header:
            # Aguarda a atualização do painel e tenta ler o cabeçalho novamente.
            try:
                page.wait_for_function(
                    """(name) => {
                        const selectors = [
                          '[data-testid="conversation-header"]',
                          '[data-testid="conversation-panel-wrapper"] header',
                          '#main header'
                        ];
                        return selectors.some(s => [...document.querySelectorAll(s)]
                          .some(el => (el.innerText || '').toLocaleLowerCase().includes(name.toLocaleLowerCase())));
                    }""",
                    arg=group,
                    timeout=5000,
                )
            except Exception:
                pass
            current_header = _read_current_chat_header(page)
        if group.casefold() not in current_header:
            return False, (
                f"Cliquei no resultado, mas não consegui confirmar o grupo '{group}'. "
                "Por segurança, nenhuma mensagem foi enviada."
            )
        return True, ""
    except Exception as exc:
        return False, f"Erro ao abrir o grupo '{group}': {type(exc).__name__}: {exc}"


def _find_composer(page):
    return _visible_first([
        page.locator('#main footer div[contenteditable="true"]'),
        page.locator('footer [contenteditable="true"][role="textbox"]'),
        page.locator('footer div[contenteditable="true"]'),
        page.locator('div[contenteditable="true"][aria-label*="Mensagem"]'),
        page.locator('div[contenteditable="true"][aria-label*="Message"]'),
        page.locator('[data-testid="conversation-compose-box-input"]'),
    ])


def _send_to_group_impl(message: str, group_name: str | None = None) -> tuple[bool, str]:
    """Envia UMA mensagem ao grupo; esta função roda somente na thread proprietária do Playwright."""
    group = (group_name or os.getenv("WHATSAPP_GROUP_NAME", "Leads")).strip()
    if not message.strip():
        return False, "Mensagem vazia."
    if os.getenv("WHATSAPP_NOTIFICATIONS", "false").strip().lower() not in {"1", "true", "yes", "sim"}:
        return False, "Notificações WhatsApp desativadas."
    if not group:
        return False, "Configure WHATSAPP_GROUP_NAME no .env."

    global _last_failure_at, _last_failure_message
    if _last_failure_at and time.monotonic() - _last_failure_at < 15:
        return False, _last_failure_message or "WhatsApp indisponível; aguardando antes de tentar novamente."

    with _lock:
        try:
            page = _get_whatsapp_page()
            if not page.url.startswith("https://web.whatsapp.com"):
                page.goto("https://web.whatsapp.com/", wait_until="domcontentloaded", timeout=60000)

            try:
                page.locator("body").wait_for(state="visible", timeout=20000)
                page.wait_for_function(
                    """() => {
                        const text = (document.body?.innerText || '').toLowerCase();
                        const loggedIn = !!(
                          document.querySelector('#pane-side') ||
                          document.querySelector('[data-testid="chat-list"]') ||
                          document.querySelector('[data-testid="chatlist"]') ||
                          document.querySelector('[data-testid="conversation-panel-wrapper"]')
                        );
                        const qr = !!(
                          document.querySelector('canvas[aria-label*="QR"]') ||
                          document.querySelector('[data-testid="qrcode"]') ||
                          document.querySelector('[data-ref] canvas') ||
                          text.includes('escaneie o código qr') ||
                          text.includes('scan the qr code') ||
                          text.includes('use whatsapp on your phone')
                        );
                        return loggedIn || qr;
                    }""",
                    timeout=45000,
                )
            except Exception as exc:
                diagnostic = _save_diagnostic(page, exc)
                _last_failure_at = time.monotonic()
                _last_failure_message = (
                    "O WhatsApp Web não carregou a lista de conversas nem mostrou um QR de login. "
                    f"Diagnóstico salvo em data/whatsapp_load_error.txt. {diagnostic[:350]}"
                )
                logging.warning("Mapeador WhatsApp: %s", _last_failure_message)
                return False, _last_failure_message

            body_text = (page.locator("body").inner_text(timeout=8000) or "").casefold()
            if any(term in body_text for term in ("escaneie o código qr", "scan the qr code", "use whatsapp on your phone")):
                _last_failure_at = time.monotonic()
                _last_failure_message = (
                    "WhatsApp Web está pedindo autenticação. Escaneie o QR Code na janela aberta; "
                    "o perfil persistente será reutilizado depois."
                )
                return False, _last_failure_message

            opened, detail = _open_target_group(page, group)
            if not opened:
                _last_failure_at = time.monotonic()
                _last_failure_message = detail
                logging.warning("Mapeador WhatsApp: %s", detail)
                return False, detail

            composer = _find_composer(page)
            if composer is None:
                _last_failure_at = time.monotonic()
                _last_failure_message = "O grupo foi confirmado, mas a caixa de mensagem não apareceu. Nada foi enviado."
                logging.warning("Mapeador WhatsApp: %s", _last_failure_message)
                return False, _last_failure_message

            composer.click(timeout=8000)
            composer.fill(message[:10000], timeout=10000)
            composer.press("Enter", timeout=8000)
            page.wait_for_timeout(1200)

            # Se o campo ainda contém texto, não declare sucesso falso.
            try:
                remaining = composer.inner_text(timeout=2000).strip()
            except Exception:
                remaining = ""
            if remaining:
                _last_failure_at = time.monotonic()
                _last_failure_message = (
                    "O WhatsApp não limpou o campo depois de pressionar Enter; "
                    "não consegui confirmar o envio. Confira a conversa antes de tentar novamente."
                )
                logging.warning("Mapeador WhatsApp: %s", _last_failure_message)
                return False, _last_failure_message

            _last_failure_at = 0.0
            _last_failure_message = ""
            return True, f"Mensagem enviada ao grupo '{group}' (campo de envio confirmado)."
        except Exception as exc:
            logging.exception("Falha ao enviar notificação para grupo WhatsApp")
            _last_failure_at = time.monotonic()
            _last_failure_message = f"Falha no WhatsApp Web ({type(exc).__name__}: {exc})."
            return False, _last_failure_message


def _sender_worker() -> None:
    """Mantém todo o Playwright em uma única thread, evitando erros de troca de thread."""
    while True:
        job = _send_queue.get()
        if job is None:
            _send_queue.task_done()
            break
        message, group_name, done, result = job
        try:
            result["value"] = _send_to_group_impl(message, group_name)
        except Exception as exc:
            logging.exception("Falha no trabalhador de envio WhatsApp")
            result["value"] = (False, f"Falha no trabalhador WhatsApp ({type(exc).__name__}: {exc}).")
        finally:
            done.set()
            _send_queue.task_done()


def send_to_group(message: str, group_name: str | None = None) -> tuple[bool, str]:
    """Enfileira o envio para que uma única thread controle o navegador do WhatsApp."""
    global _sender_thread
    with _sender_start_lock:
        if _sender_thread is None or not _sender_thread.is_alive():
            _sender_thread = Thread(
                target=_sender_worker,
                daemon=True,
                name="mapeador-whatsapp-sender",
            )
            _sender_thread.start()

    done = Event()
    result: dict = {}
    _send_queue.put((message, group_name, done, result))
    # O envio pode precisar aguardar a abertura do WhatsApp ou autenticação.
    if not done.wait(timeout=150):
        return False, "O envio ao WhatsApp excedeu 150 segundos. Verifique a janela do WhatsApp Web."
    return result.get("value", (False, "O trabalhador WhatsApp terminou sem retornar resultado."))


def send_to_self(message: str) -> tuple[bool, str]:
    """Compatibilidade com chamadas anteriores; as notificações vão ao grupo configurado."""
    return send_to_group(message)
