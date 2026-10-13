"""Orquestrador do Mapeador."""
from __future__ import annotations

import argparse
import asyncio
import logging
import os

from dotenv import load_dotenv

from ai_agent.analyzer import analyze_lead
from database.db import init_db, save_lead, update_analysis
from outreach.sender import simulate_send
from scraper.maps_scraper import search_google_maps

load_dotenv()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Mapeador: prospecção assistida por IA.")
    parser.add_argument("--termo", default="restaurantes em Vitória ES", help="Termo de pesquisa no Maps")
    parser.add_argument("--limite", type=int, default=5, help="Máximo de empresas a pesquisar")
    parser.add_argument("--oferta", default="serviços de presença digital", help="Oferta comercial")
    parser.add_argument("--verbose", action="store_true", help="Exibe logs de diagnóstico")
    return parser.parse_args()


async def run() -> int:
    args = parse_args()
    if args.limite < 1:
        print("O limite deve ser pelo menos 1.")
        return 2
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname)s: %(message)s")
    init_db(os.getenv("DATABASE_PATH", "data/mapeador.sqlite3"))

    try:
        leads = await search_google_maps(args.termo, args.limite)
    except Exception:
        logging.exception("Falha durante a pesquisa.")
        return 1

    if not leads:
        logging.warning("Nenhum lead coletado. Confira a pesquisa e os avisos do navegador.")
        return 0

    new_count = 0
    for lead in leads:
        lead_id, inserted = save_lead(lead, os.getenv("DATABASE_PATH", "data/mapeador.sqlite3"))
        new_count += int(inserted)
        print(f"\nLead: {lead['name']} | {lead.get('category', '')}")
        print("Registro: " + ("novo" if inserted else "já existia (dados atualizados)"))
        try:
            analysis = analyze_lead(lead, args.oferta)
            update_analysis(lead_id, analysis, os.getenv("DATABASE_PATH", "data/mapeador.sqlite3"))
            print(f"Qualificação estimada: {analysis['score']}/100 — {analysis['justificativa']}")
            simulate_send(lead, analysis["mensagem"])
        except Exception as exc:
            logging.error("Não foi possível analisar %s: %s", lead["name"], exc)

    print(f"\nConcluído. Resultados encontrados: {len(leads)}; novos registros: {new_count}.")
    print("As mensagens são apenas rascunhos; nada foi enviado automaticamente.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
