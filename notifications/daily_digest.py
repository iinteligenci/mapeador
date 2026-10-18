"""Rotina diária de notificações para o grupo WhatsApp privado 'lembrar'."""
from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from ai_agent.analyzer import analyze_lead_profiles
from database.db import get_leads, get_proposals, init_db, save_proposal, update_public_contacts
from scraper.public_contacts import find_public_business_contacts
from notifications.whatsapp_self import send_to_group


def _db_path() -> str:
    return os.getenv("DATABASE_PATH", "data/mapeador.sqlite3")


def _connect() -> sqlite3.Connection:
    path = Path(_db_path()).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=20)
    conn.row_factory = sqlite3.Row
    return conn


def _init_log() -> None:
    init_db(_db_path())
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS notification_log (
                event_key TEXT PRIMARY KEY,
                category TEXT NOT NULL,
                label TEXT NOT NULL DEFAULT '',
                sent_date TEXT NOT NULL,
                sent_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS notification_daily_runs (
                run_date TEXT PRIMARY KEY,
                completed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS notification_schedule_settings (
                id INTEGER PRIMARY KEY CHECK (id=1),
                enabled INTEGER NOT NULL DEFAULT 1,
                times_json TEXT NOT NULL DEFAULT '["09:00"]',
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("INSERT OR IGNORE INTO notification_schedule_settings(id, enabled, times_json) VALUES (1, 1, '[\"09:00\"]')")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS notification_schedule_runs (
                run_date TEXT NOT NULL,
                scheduled_time TEXT NOT NULL,
                completed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(run_date, scheduled_time)
            )
        """)



def get_notification_schedule() -> dict:
    _init_log()
    with _connect() as conn:
        row = conn.execute("SELECT enabled, times_json FROM notification_schedule_settings WHERE id=1").fetchone()
    try:
        times = json.loads(row["times_json"]) if row else ["09:00"]
    except (TypeError, json.JSONDecodeError):
        times = ["09:00"]
    return {"enabled": bool(row["enabled"]) if row else True, "times": times}


def set_notification_schedule(enabled: bool, times_text: str) -> list[str]:
    """Salva horários HH:MM separados por vírgula."""
    values = []
    for item in str(times_text or "").replace(";", ",").split(","):
        item = item.strip()
        if not item:
            continue
        if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", item):
            raise ValueError(f"Horário inválido: {item}. Use HH:MM, por exemplo 09:00.")
        if item not in values:
            values.append(item)
    if not values:
        raise ValueError("Digite pelo menos um horário, por exemplo 09:00.")
    values.sort()
    _init_log()
    with _connect() as conn:
        conn.execute("UPDATE notification_schedule_settings SET enabled=?, times_json=?, updated_at=CURRENT_TIMESTAMP WHERE id=1",
                     (int(enabled), json.dumps(values)))
    return values


def _schedule_run_done(today: str, scheduled_time: str) -> bool:
    with _connect() as conn:
        return conn.execute("SELECT 1 FROM notification_schedule_runs WHERE run_date=? AND scheduled_time=?",
                            (today, scheduled_time)).fetchone() is not None


def _mark_schedule_run(today: str, scheduled_time: str) -> None:
    with _connect() as conn:
        conn.execute("INSERT OR IGNORE INTO notification_schedule_runs(run_date, scheduled_time) VALUES (?, ?)",
                     (today, scheduled_time))


def run_scheduled_notifications() -> tuple[bool, str]:
    """Verifica itens novos em cada horário configurado, sem repetir os já enviados."""
    _init_log()
    today = datetime.now().astimezone().date().isoformat()
    ok_routes = _send_routes(today)
    _ensure_proposals(limit=15)
    count_4k, ok_4k = _send_proposals("4k", today, 5)
    count_digital, ok_digital = _send_proposals("digital", today, 5)
    return (ok_routes and ok_4k and ok_digital,
            f"{count_4k} propostas 4K e {count_digital} propostas de presença digital enviadas; rotas elegíveis verificadas.")


def _was_sent(event_key: str) -> bool:
    with _connect() as conn:
        return conn.execute("SELECT 1 FROM notification_log WHERE event_key=?", (event_key,)).fetchone() is not None


def _mark_sent(event_key: str, category: str, label: str, today: str) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO notification_log(event_key, category, label, sent_date) VALUES (?, ?, ?, ?)",
            (event_key, category, label, today),
        )


def _count_sent_today(category: str, today: str) -> int:
    with _connect() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM notification_log WHERE category=? AND sent_date=?",
            (category, today),
        ).fetchone()
        return int(row["n"] or 0)


def _daily_complete(today: str) -> bool:
    with _connect() as conn:
        return conn.execute("SELECT 1 FROM notification_daily_runs WHERE run_date=?", (today,)).fetchone() is not None


def _mark_daily_complete(today: str) -> None:
    with _connect() as conn:
        conn.execute("INSERT OR IGNORE INTO notification_daily_runs(run_date) VALUES (?)", (today,))


def _emails(value: object) -> list[str]:
    raw = str(value or "")
    return list(dict.fromkeys(
        item.strip() for item in re.split(r"[,;\s]+", raw)
        if "@" in item and "." in item.rsplit("@", 1)[-1]
    ))


def _whatsapp(lead: dict) -> str:
    raw = str(lead.get("contact_whatsapp") or lead.get("contact_whatsapps") or "").strip()
    # If multiple numbers were found, use the first one.
    raw = re.split(r"[,;\n]+", raw)[0].strip()
    digits = re.sub(r"\D", "", raw)
    if len(digits) in (10, 11):
        digits = "55" + digits
    return "+" + digits if 12 <= len(digits) <= 13 else ""


def _fold(value: str) -> str:
    """Normaliza texto para comparar cidades e bairros sem depender de acentos."""
    import unicodedata
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii").casefold()).strip()


def _city_from_address(address: str) -> str:
    """Reconhece municípios da Grande Vitória e cidades próximas em endereços do Maps."""
    cities = {
        "Vitória": ("vitoria",),
        "Vila Velha": ("vila velha",),
        "Cariacica": ("cariacica",),
        "Serra": ("serra",),
        "Viana": ("viana",),
        "Guarapari": ("guarapari",),
        "Fundão": ("fundao",),
        "Domingos Martins": ("domingos martins",),
        "Marechal Floriano": ("marechal floriano",),
        "Santa Leopoldina": ("santa leopoldina",),
        "Aracruz": ("aracruz",),
        "João Neiva": ("joao neiva",),
        "Anchieta": ("anchieta",),
        "Iconha": ("iconha",),
        "Piúma": ("piuma",),
    }
    folded = _fold(address)
    for canonical, variants in cities.items():
        if any(re.search(r"\b" + re.escape(variant) + r"\b", folded) for variant in variants):
            return canonical
    return ""


def _neighborhood(lead: dict) -> str:
    """Retorna bairro + município, evitando juntar bairros homônimos de cidades diferentes."""
    address = re.sub(r"\s+", " ", str(lead.get("address") or "")).strip()
    folded = _fold(address)
    city = _city_from_address(address)

    aliases = [
        ("Praia da Costa", ("praia da costa",)),
        ("Coqueiral de Itaparica", ("coqueiral de itaparica",)),
        ("Praia de Itaparica", ("praia de itaparica",)),
        ("Praia das Gaivotas", ("praia das gaivotas", "gaivotas")),
        ("Nossa Senhora da Penha", ("nossa sra. da penha", "nossa sra da penha", "nossa senhora da penha")),
        ("Divino Espirito Santo", ("divino espirito santo",)),
        ("Centro", ("centro de vila velha",)),
        ("Morada de Laranjeiras", ("morada de laranjeiras",)),
        ("Jardim da Penha", ("jardim da penha",)),
        ("Jardim Camburi", ("jardim camburi",)),
        ("Praia do Canto", ("praia do canto",)),
        ("Mata da Praia", ("mata da praia",)),
        ("Bento Ferreira", ("bento ferreira",)),
        ("Enseada do Sua", ("enseada do sua",)),
        ("Campo Grande", ("campo grande",)),
        ("Jardim América", ("jardim america",)),
        ("Marcílio de Noronha", ("marcilio de noronha",)),
        ("Praia do Morro", ("praia do morro",)),
        ("Praia Grande", ("praia grande",)),
        ("Itapuã", ("itapua",)),
        ("Ataíde", ("ataide",)),
        ("Glória", ("gloria",)),
        ("Soteco", ("soteco",)),
        ("Goiabeiras", ("goiabeiras",)),
        ("Maruípe", ("maruipe",)),
        ("Itararé", ("itarare",)),
        ("Jacaraípe", ("jacaraipe",)),
        ("Laranjeiras", ("laranjeiras",)),
        ("Feu Rosa", ("feu rosa",)),
        ("Barcelona", ("barcelona",)),
        ("Carapina", ("carapina",)),
        ("Itacibá", ("itaciba",)),
        ("Alto Lage", ("alto lage",)),
        ("Muquicaba", ("muquicaba",)),
        ("Meaípe", ("meaipe",)),
        ("Marcilio de Noronha", ("marcilio de noronha",)),
        ("Centro", ("centro",)),
        ("Feu Rosa", ("feu rosa",)),
        ("Barcelona", ("barcelona",)),
        ("Carapina", ("carapina",)),
        ("Campo Grande", ("campo grande",)),
        ("Itaciba", ("itaciba",)),
        ("Jardim America", ("jardim america",)),
        ("Alto Lage", ("alto lage",)),
        ("Praia do Morro", ("praia do morro",)),
        ("Muquicaba", ("muquicaba",)),
        ("Meaipe", ("meaipe",)),
        ("Marcilio de Noronha", ("marcilio de noronha",)),
        ("Praia Grande", ("praia grande",)),
    ]
    neighborhood = ""
    for canonical, needles in aliases:
        if any(re.search(r"\b" + re.escape(_fold(needle)) + r"\b", folded) for needle in needles):
            neighborhood = canonical
            break

    parts = [part.strip() for part in address.split(",") if part.strip()]
    if not neighborhood:
        # Endereços do Maps variam: "Rua X - Bairro, Cidade - ES" ou
        # "Rua X, Bairro, Cidade, CEP, Brasil". Prioriza o segmento anterior à cidade.
        city_index = next((i for i, part in enumerate(parts) if city and re.search(r"\b" + re.escape(_fold(city)) + r"\b", _fold(part))), -1)
        candidates = []
        if city_index > 0:
            candidates.append(parts[city_index - 1])
            if city_index > 1:
                candidates.append(parts[city_index - 2])
        elif len(parts) >= 3:
            candidates.append(parts[-3])
        for candidate in candidates:
            candidate = re.sub(r"^(?:rua|r\.|avenida|av\.|rodovia|rod\.|estrada|travessa|tv\.)\s+", "", candidate, flags=re.I).strip()
            candidate = re.split(r"\s+[-–]\s+", candidate)[-1].strip()
            candidate = re.sub(r"^(?:(?:loja|lj|quiosque|box|sala)\s*)?\d+\s*[-–:]\s*", "", candidate, flags=re.I).strip()
            candidate_folded = _fold(candidate)
            if candidate and candidate_folded not in {
                "brasil", "brazil", "espirito santo", "es", "vila velha", "vitoria",
                "cariacica", "serra", "viana", "guarapari", "fundao", "domingos martins",
            } and not re.search(r"\b\d{5}-?\d{3}\b", candidate):
                neighborhood = candidate
                break

    if not neighborhood:
        return "Bairro não identificado" + (f" — {city}" if city else "")
    return f"{neighborhood} — {city}" if city else neighborhood

def _send_routes(today: str) -> bool:
    leads = [item for item in get_leads(path=_db_path()) if item.get("status") == "in_person"]
    groups: dict[str, list[dict]] = {}
    for lead in leads:
        name = _neighborhood(lead)
        groups.setdefault(name, []).append(lead)
    all_ok = True
    for neighborhood, places in sorted(groups.items(), key=lambda item: item[0].casefold()):
        if len(places) <= 10 or neighborhood.startswith("Bairro não identificado"):
            continue
        event_key = "route:" + neighborhood.casefold()
        legacy_key = "route:" + neighborhood.split(" — ", 1)[0].casefold()
        # Compatibilidade: não reenviar bairro já notificado antes da separação por cidade.
        if _was_sent(event_key) or (legacy_key != event_key and _was_sent(legacy_key)):
            continue
        lines = [
            f"🗺️ ROTA DE VISITAS — {neighborhood.upper()}",
            f"Visitas presenciais cadastradas neste bairro: {len(places)}",
            "Mensagem de rota do Mapeador; não é proposta comercial.",
            "",
        ]
        for place in sorted(places, key=lambda item: str(item.get("name") or "").casefold()):
            address = str(place.get("address") or "Endereço não identificado")
            maps_url = str(place.get("link") or (
                "https://www.google.com/maps/search/?api=1&query=" +
                quote(str(place.get("name") or "") + " " + address)
            ))
            lines.extend([f"• {place.get('name') or 'Estabelecimento'}", f"  Endereço: {address}", f"  Google Maps: {maps_url}", ""])
        ok, detail = send_to_group("\n".join(lines)[:10000])
        if ok:
            _mark_sent(event_key, "route", neighborhood, today)
        else:
            all_ok = False
            logging.warning("Rota do bairro %s não enviada: %s", neighborhood, detail)
    return all_ok


def _eligible_lead(lead: dict) -> bool:
    return bool(_emails(lead.get("contact_emails")) and _whatsapp(lead))


def _ensure_proposals(limit: int = 15) -> None:
    """Gera propostas separadas para leads que já têm e-mail e WhatsApp públicos."""
    leads = get_leads(path=_db_path())
    proposals = get_proposals(path=_db_path())
    existing = {(int(p.get("lead_id") or 0), str(p.get("profile") or "")) for p in proposals}
    processed = 0
    examined = 0
    for lead in leads:
        if processed >= limit or examined >= limit * 3:
            break
        if lead.get("status") in {"removed", "in_person"}:
            continue
        examined += 1
        # Try to discover only publicly published contacts on the business's own website.
        if not _eligible_lead(lead) and str(lead.get("website") or "").startswith(("https://", "http://")):
            try:
                contacts = find_public_business_contacts(lead)
                update_public_contacts(int(lead["id"]), contacts, _db_path())
                lead.update(contacts)
                refreshed = next((item for item in get_leads(path=_db_path()) if int(item.get("id") or 0) == int(lead["id"])), None)
                if refreshed:
                    lead = refreshed
            except Exception as contact_exc:
                logging.info("Contatos públicos indisponíveis para %s: %s", lead.get("name"), contact_exc)
        if not _eligible_lead(lead):
            continue
        missing = [profile for profile in ("4k", "digital") if (int(lead["id"]), profile) not in existing]
        if not missing:
            continue
        analysis_lead = {
            **lead,
            "address": lead.get("address", ""),
            "contact_whatsapp": _whatsapp(lead),
            "contact_emails": _emails(lead.get("contact_emails")),
        }
        try:
            analyses = analyze_lead_profiles(analysis_lead, missing)
            for profile in missing:
                if profile in analyses:
                    save_proposal(
                        int(lead["id"]), profile, "WhatsApp", _whatsapp(lead),
                        str(lead.get("contact_source") or lead.get("link") or ""),
                        analyses[profile], _db_path()
                    )
            processed += 1
        except Exception as exc:
            logging.warning("Não foi possível preparar proposta para %s: %s", lead.get("name"), exc)


def _send_proposals(profile: str, today: str, daily_limit: int = 5) -> tuple[int, bool]:
    label = "4K FOOD SERVICE" if profile == "4k" else "PRESENÇA DIGITAL"
    proposals = get_proposals(profile=profile, path=_db_path())
    # Only one proposal per establishment/profile; require a public email and a WhatsApp number.
    unique: dict[int, dict] = {}
    for proposal in proposals:
        lead_id = int(proposal.get("lead_id") or 0)
        if not lead_id or lead_id in unique:
            continue
        if _emails(proposal.get("contact_emails")) and _whatsapp(proposal):
            unique[lead_id] = proposal
    sent_today = _count_sent_today("proposal_" + profile, today)
    all_ok = True
    for lead_id, proposal in sorted(unique.items(), key=lambda item: (-int(item[1].get("score") or 0), item[0])):
        if sent_today >= daily_limit:
            break
        event_key = f"proposal:{profile}:{lead_id}"
        if _was_sent(event_key):
            continue
        email = _emails(proposal.get("contact_emails"))[0]
        whatsapp = _whatsapp(proposal)
        maps_url = str(proposal.get("maps_url") or "")
        if not maps_url:
            address = str(proposal.get("address") or "")
            maps_url = "https://www.google.com/maps/search/?api=1&query=" + quote(str(proposal.get("lead_name") or "") + " " + address)
        message = "\n".join([
            f"📨 PROPOSTA — {label}",
            f"Empresa: {proposal.get('lead_name') or 'Nome não identificado'}",
            f"Categoria: {proposal.get('category') or 'Não identificada'}",
            f"E-mail público: {email}",
            f"WhatsApp público: {whatsapp}",
            f"Endereço: {proposal.get('address') or 'Não identificado'}",
            f"Google Maps: {maps_url}",
            f"Prioridade preliminar: {proposal.get('score', 0)}/100",
            f"Justificativa: {proposal.get('justification') or 'Não informada'}",
            "",
            "MENSAGEM SUGERIDA (rascunho; não enviada à empresa):",
            str(proposal.get("message") or ""),
            "",
            "Esta é uma proposta de prospecção para revisão. Não é uma rota de visitas.",
        ])
        ok, detail = send_to_group(message[:3500])
        if ok:
            _mark_sent(event_key, "proposal_" + profile, str(proposal.get("lead_name") or lead_id), today)
            sent_today += 1
        else:
            all_ok = False
            logging.warning("Proposta %s para %s não enviada: %s", label, proposal.get("lead_name"), detail)
    return sent_today, all_ok


def send_eligible_routes_now() -> tuple[bool, str]:
    """Envia somente bairros elegíveis, um por mensagem, respeitando o registro antirrepetição."""
    _init_log()
    today = datetime.now().astimezone().date().isoformat()
    ok = _send_routes(today)
    return ok, "Rotas por bairro verificadas; somente bairros com mais de 10 visitas ainda não notificados são enviados."


def run_daily_notifications() -> tuple[bool, str]:
    """Executa rotas primeiro e depois 5 propostas de cada perfil, sempre em mensagens separadas."""
    _init_log()
    today = datetime.now().astimezone().date().isoformat()
    if _daily_complete(today):
        return True, "Rotina diária já concluída."
    ok = _send_routes(today)
    _ensure_proposals(limit=15)
    count_4k, ok_4k = _send_proposals("4k", today, 5)
    count_digital, ok_digital = _send_proposals("digital", today, 5)
    ok = ok and ok_4k and ok_digital
    # Mark the date complete only when every attempted send succeeded.
    # Successful individual messages are independently logged, so retries won't duplicate them.
    if ok:
        _mark_daily_complete(today)
    return ok, f"Rotina {today}: {count_4k}/5 propostas 4K e {count_digital}/5 propostas de presença digital enviadas. Rotas elegíveis verificadas."


def daily_notifications_loop() -> None:
    """Verifica horários configurados e executa cada horário no máximo uma vez por dia."""
    _init_log()
    while True:
        try:
            now = datetime.now().astimezone()
            today = now.date().isoformat()
            schedule = get_notification_schedule()
            current_time = now.strftime("%H:%M")
            if schedule["enabled"] and current_time in schedule["times"] and not _schedule_run_done(today, current_time):
                ok, detail = run_scheduled_notifications()
                logging.info("Mapeador — notificações WhatsApp (%s): %s", current_time, detail)
                if ok:
                    _mark_schedule_run(today, current_time)
                else:
                    logging.warning("Algumas notificações falharam; o horário será tentado novamente.")
        except Exception as exc:
            logging.warning("Erro na rotina de notificações: %s", exc)
        time.sleep(20)
