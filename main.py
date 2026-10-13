"""Orquestrador do Mapeador."""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from ai_agent.analyzer import analyze_lead
from database.db import init_db, save_lead, update_analysis
from outreach.sender import simulate_send
from scraper.maps_scraper import search_google_maps
from scraper.site_research import research_public_site

load_dotenv()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Mapeador: pesquisa negócios alimentícios e gera relatório comercial.")
    parser.add_argument("--termo", default="restaurantes em Vitória ES", help="Negócio alimentício e localidade para pesquisar no Maps")
    parser.add_argument("--limite", type=int, default=5, help="Máximo de empresas a pesquisar")
    parser.add_argument("--oferta", default="serviços de presença digital", help="Oferta para qualificação comercial")
    parser.add_argument("--verbose", action="store_true", help="Exibe logs de diagnóstico")
    return parser.parse_args()


def _report_value(value: object) -> str:
    if isinstance(value, list):
        return ", ".join(str(item) for item in value) if value else "Não identificado publicamente"
    return str(value).strip() if value else "Não identificado publicamente"


def write_report(items: list[dict], output_dir: str = "reports") -> Path:
    """Gera um relatório Markdown simples com dados, fontes e limites da pesquisa."""
    folder = Path(output_dir)
    folder.mkdir(parents=True, exist_ok=True)
    now = datetime.now().astimezone()
    path = folder / f"relatorio_mapeador_{now.strftime('%Y%m%d_%H%M%S')}.md"
    lines = [
        "# Relatório de prospecção — negócios alimentícios",
        "",
        f"Gerado em: {now.strftime('%d/%m/%Y %H:%M %Z')}",
        f"Estabelecimentos pesquisados: {len(items)}",
        "",
        "> Os dados refletem apenas informações públicas acessíveis. Campo não encontrado não significa que o negócio não tenha o canal ou sistema.",
        "",
    ]
    for index, item in enumerate(items, start=1):
        lead = item.get("lead", {})
        research = item.get("research", {})
        analysis = item.get("analysis", {})
        lines.extend([
            f"## {index}. {lead.get('name', 'Nome não identificado')}",
            "",
            f"- **Categoria:** {_report_value(lead.get('category'))}",
            f"- **Telefone:** {_report_value(lead.get('phone'))}",
            f"- **Endereço:** {_report_value(lead.get('address') or research.get('address'))}",
            f"- **Site:** {_report_value(lead.get('website'))}",
            f"- **Instagram:** {_report_value(research.get('instagram'))}",
            f"- **Google Maps:** {_report_value(lead.get('link'))}",
            f"- **Outros canais encontrados:** {_report_value(research.get('channels'))}",
            f"- **Cardápio/catálogo:** {_report_value(research.get('menu_url'))}",
            f"- **Itens/produtos identificados nas páginas públicas:** {_report_value(research.get('menu_items'))}",
            f"- **Plataformas/ferramentas identificadas publicamente:** {_report_value(research.get('public_platforms'))}",
            f"- **Presença digital — avaliação preliminar:** {_report_value(analysis.get('justificativa'))}",
            f"- **Prioridade estimada para a oferta informada:** {analysis.get('score', 'Não avaliada')}/100",
        ])
        notes = research.get("research_notes") or []
        if notes:
            lines.append(f"- **Observações e limitações:** {'; '.join(notes)}")
        sources = research.get("sources") or []
        if sources:
            lines.append("- **Páginas consultadas:** " + ", ".join(sources))
        lines.append("")
    lines.extend([
        "## Como interpretar",
        "",
        "- Itens do cardápio são extraídos de texto público; sites com cardápio em imagem, PDF ou JavaScript podem não ser lidos.",
        "- A pesquisa não consegue confirmar sistemas internos de gestão de vendas quando não aparecem publicamente.",
        "- A avaliação por IA é uma hipótese para orientar a revisão humana, não uma afirmação factual sobre a empresa.",
        "- As mensagens comerciais são apenas rascunhos e não são enviadas automaticamente.",
        "",
    ])
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


async def run() -> int:
    args = parse_args()
    if args.limite < 1:
        print("O limite deve ser pelo menos 1.")
        return 2
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s: %(message)s")
    db_path = os.getenv("DATABASE_PATH", "data/mapeador.sqlite3")
    init_db(db_path)

    try:
        leads = await search_google_maps(args.termo, args.limite)
    except Exception:
        logging.exception("Falha durante a pesquisa.")
        return 1
    if not leads:
        logging.warning("Nenhum resultado coletado. Confira o termo e os avisos do navegador.")
        return 0

    report_items: list[dict] = []
    new_count = 0
    for lead in leads:
        lead_id, inserted = save_lead(lead, db_path)
        new_count += int(inserted)
        print(f"\nEmpresa: {lead['name']} | {lead.get('category', '')}")
        print("Registro: " + ("novo" if inserted else "já existia (dados atualizados)"))
        research = research_public_site(lead)
        for label, key in [
            ("Telefone", "phone"), ("Endereço", "address"), ("Site", "website"),
            ("Instagram", "instagram"), ("Canais", "channels"),
            ("Cardápio/catálogo", "menu_url"), ("Itens encontrados", "menu_items"),
            ("Plataformas públicas", "public_platforms"),
        ]:
            value = research.get(key) or lead.get(key)
            print(f"{label}: {_report_value(value)}")
        analysis: dict = {}
        try:
            analysis = analyze_lead(lead, args.oferta)
            update_analysis(lead_id, analysis, db_path)
            print(f"Presença digital — prioridade estimada: {analysis['score']}/100")
            print(f"Análise: {analysis['justificativa']}")
            simulate_send(lead, analysis["mensagem"])
        except Exception as exc:
            logging.error("Não foi possível analisar %s com IA: %s", lead["name"], exc)
        report_items.append({"lead": lead, "research": research, "analysis": analysis})

    try:
        report_path = write_report(report_items)
        print(f"\nRelatório salvo em: {report_path}")
    except OSError:
        logging.exception("Não foi possível salvar o relatório.")
    print(f"\nConcluído. Resultados: {len(leads)}; novos registros: {new_count}.")
    print("A pesquisa não confirma ferramentas internas que não estejam expostas publicamente.")
    print("Mensagens são rascunhos; nada foi enviado automaticamente.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
