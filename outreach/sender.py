"""Simulador de envio: não envia mensagens para serviços externos."""
from __future__ import annotations

from datetime import datetime
from typing import Any


def simulate_send(lead: dict[str, Any], message: str) -> dict[str, str]:
    """Registra no console uma simulação de envio e retorna seu status."""
    lead_name = str(lead.get("name") or "Lead sem nome")
    timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
    print("\n" + "=" * 68)
    print(f"[SIMULAÇÃO — NÃO ENVIADO] {timestamp}")
    print(f"Empresa: {lead_name}")
    print(f"Link: {lead.get('link', '')}")
    print(f"Mensagem sugerida:\n{message}")
    print("=" * 68)
    return {"status": "simulated", "lead": lead_name, "timestamp": timestamp}
