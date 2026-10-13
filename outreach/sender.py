"""Registro/simulação de abordagens. Não envia mensagens externas."""
from __future__ import annotations

from datetime import datetime
from typing import Any


def simulate_send(lead: dict[str, Any], message: str) -> dict[str, str]:
    """Exibe um rascunho para revisão humana; não envia WhatsApp, e-mail ou SMS."""
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    print("\n" + "-" * 68)
    print(f"RASCUNHO — NÃO ENVIADO | {now}")
    print(f"Empresa: {lead.get('name', 'Lead sem nome')}")
    print(f"Telefone público: {lead.get('phone') or 'não encontrado'}")
    print(f"Site: {lead.get('website') or 'não encontrado'}")
    print(f"Mensagem sugerida:\n{message}")
    print("-" * 68)
    return {"status": "draft", "timestamp": now}
