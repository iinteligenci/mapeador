"""Orquestrador do Mapeador."""
from __future__ import annotations

import argparse
import asyncio
import logging

from ai_agent.analyzer import generate_outreach_message
from outreach.sender import simulate_send
from scraper.maps_scraper import search_google_maps


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Pesquisa empresas no Google Maps e prepara abordagens comerciais."
    )
    parser.add_argument("--termo", default="restaurantes em Vitória ES", help="Termo de pesquisa")
    parser.add_argument("--limite", type=int, default=5, help="Número máximo de empresas")
    parser.add_argument("--oferta", default=None, help="Descrição curta da oferta comercial")
    parser.add_argument("--verbose", action="store_true", help="Ativa logs detalhados")
    return parser.parse_args()


async def run() -> int:
    args = parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)
    try:
        leads = await search_google_maps(args.termo, args.limite)
    except Exception as exc:
        logging.error("Falha ao pesquisar no Google Maps: %s", exc)
        return 1

    if not leads:
        logging.warning("Nenhum lead coletado. Verifique o termo, a conexão e as restrições do Maps.")
        return 0

    print(f"\nEncontrados {len(leads)} lead(s). Gerando abordagens...\n")
    for index, lead in enumerate(leads, start=1):
        print(f"[{index}/{len(leads)}] {lead['name']} — {lead['category']}")
        try:
            message = generate_outreach_message(lead, args.oferta)
            simulate_send(lead, message)
        except Exception as exc:
            logging.error("Falha ao analisar %s: %s", lead.get("name", "lead"), exc)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
