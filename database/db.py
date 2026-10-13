"""Persistência SQLite para leads e histórico da última análise."""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


def _db_path(path: str | None = None) -> Path:
    return Path(path or os.getenv("DATABASE_PATH", "data/mapeador.sqlite3")).expanduser()


def _connect(path: str | None = None) -> sqlite3.Connection:
    db_path = _db_path(path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def _connection(path: str | None = None) -> Iterator[sqlite3.Connection]:
    """Abre uma conexão, faz commit/rollback e fecha o recurso ao sair."""
    conn = _connect(path)
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def init_db(path: str | None = None) -> None:
    """Cria as tabelas caso ainda não existam."""
    with _connection(path) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS leads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT '',
                link TEXT NOT NULL UNIQUE,
                phone TEXT NOT NULL DEFAULT '',
                website TEXT NOT NULL DEFAULT '',
                score INTEGER,
                justification TEXT NOT NULL DEFAULT '',
                message TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'to_visit',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Novos campos opcionais: a migração preserva os bancos locais existentes.
        existing_columns = {row["name"] for row in conn.execute("PRAGMA table_info(leads)").fetchall()}
        for column in (
            "contact_name", "contact_role", "contact_phone", "contact_whatsapp",
            "contact_source", "contact_confidence", "contact_notes", "cnpj", "cnpj_source",
            "cnpj_checked_at", "contact_checked_at"
        ):
            if column not in existing_columns:
                conn.execute(f"ALTER TABLE leads ADD COLUMN {column} TEXT NOT NULL DEFAULT ''")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS campaigns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                profile TEXT NOT NULL,
                message TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS campaign_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                campaign_id INTEGER NOT NULL,
                lead_id INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                consent_confirmed INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(campaign_id, lead_id),
                FOREIGN KEY(campaign_id) REFERENCES campaigns(id) ON DELETE CASCADE,
                FOREIGN KEY(lead_id) REFERENCES leads(id) ON DELETE CASCADE
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_leads_name ON leads(name)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(status)")
        # Compatibilidade com registros criados pelas versões anteriores.
        conn.execute("UPDATE leads SET status = 'to_visit' WHERE status IN ('new', 'draft_ready') OR status IS NULL OR status = ''")


def save_lead(lead: dict[str, Any], path: str | None = None) -> tuple[int, bool]:
    """Insere ou atualiza lead pela URL única. Retorna (id, foi_inserido_agora)."""
    init_db(path)
    name = str(lead.get("name") or "").strip()
    link = str(lead.get("link") or "").strip()
    if not name:
        raise ValueError("O lead precisa ter um nome.")
    if not link:
        # Não usar nome como chave: empresas diferentes podem ter o mesmo nome.
        raise ValueError("O lead precisa ter o link do local para evitar duplicados com segurança.")

    with _connect(path) as conn:
        existing = conn.execute("SELECT id FROM leads WHERE link = ?", (link,)).fetchone()
        conn.execute("""
            INSERT INTO leads (name, category, link, phone, website)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(link) DO UPDATE SET
                name = excluded.name,
                category = CASE WHEN excluded.category <> '' THEN excluded.category ELSE leads.category END,
                phone = CASE WHEN excluded.phone <> '' THEN excluded.phone ELSE leads.phone END,
                website = CASE WHEN excluded.website <> '' THEN excluded.website ELSE leads.website END,
                updated_at = CURRENT_TIMESTAMP
        """, (
            name,
            str(lead.get("category") or "").strip(),
            link,
            str(lead.get("phone") or "").strip(),
            str(lead.get("website") or "").strip(),
        ))
        row = conn.execute("SELECT id FROM leads WHERE link = ?", (link,)).fetchone()
        return int(row["id"]), existing is None


def update_analysis(lead_id: int, analysis: dict[str, Any], path: str | None = None) -> None:
    """Guarda score, justificativa, mensagem e estado de revisão."""
    init_db(path)
    score = max(0, min(100, int(analysis.get("score", 0))))
    with _connect(path) as conn:
        conn.execute("""
            UPDATE leads
            SET score = ?, justification = ?, message = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (
            score,
            str(analysis.get("justificativa") or ""),
            str(analysis.get("mensagem") or ""),
            lead_id,
        ))


def update_public_contacts(lead_id: int, contacts: dict[str, Any], path: str | None = None) -> None:
    """Persiste somente contatos observados em fontes públicas."""
    init_db(path)
    fields = (
        "contact_name", "contact_role", "contact_phone", "contact_whatsapp",
        "contact_source", "contact_confidence"
    )
    values = [str(contacts.get(field) or "").strip() for field in fields]
    notes = " ".join(str(note).strip() for note in contacts.get("contact_notes", []) if str(note).strip())
    with _connect(path) as conn:
        conn.execute(
            """UPDATE leads SET contact_name=?, contact_role=?, contact_phone=?,
               contact_whatsapp=?, contact_source=?, contact_confidence=?,
               contact_notes=?, contact_checked_at=CURRENT_TIMESTAMP, updated_at=CURRENT_TIMESTAMP WHERE id=?""",
            (*values, notes, lead_id),
        )


def update_business_identity(lead_id: int, cnpj: str = "", cnpj_source: str = "", path: str | None = None) -> None:
    """Guarda CNPJ apenas quando encontrado explicitamente em fonte pública."""
    init_db(path)
    with _connect(path) as conn:
        conn.execute(
            """UPDATE leads SET
               cnpj=CASE WHEN ? <> '' THEN ? ELSE cnpj END,
               cnpj_source=CASE WHEN ? <> '' THEN ? ELSE cnpj_source END,
               cnpj_checked_at=CURRENT_TIMESTAMP, updated_at=CURRENT_TIMESTAMP
               WHERE id=?""",
            (cnpj, cnpj, cnpj_source, cnpj_source, lead_id),
        )


def save_campaign(name: str, profile: str, message: str, path: str | None = None) -> int:
    if profile not in {"4k", "digital"}:
        raise ValueError("Perfil de campanha inválido.")
    if not message.strip():
        raise ValueError("Escreva a mensagem antes de salvar a campanha.")
    init_db(path)
    with _connect(path) as conn:
        cursor = conn.execute(
            "INSERT INTO campaigns(name, profile, message) VALUES (?, ?, ?)",
            (name.strip() or ("Campanha 4K" if profile == "4k" else "Campanha Presença Digital"), profile, message.strip()),
        )
        return int(cursor.lastrowid)


def get_campaigns(path: str | None = None) -> list[dict[str, Any]]:
    init_db(path)
    with _connect(path) as conn:
        rows = conn.execute("""
            SELECT c.*, COUNT(e.id) AS queued_count
            FROM campaigns c LEFT JOIN campaign_events e ON e.campaign_id=c.id
            GROUP BY c.id ORDER BY c.id DESC
        """)
        return [dict(row) for row in rows]


def queue_campaign(campaign_id: int, lead_ids: list[int], path: str | None = None) -> None:
    init_db(path)
    with _connect(path) as conn:
        for lead_id in lead_ids:
            conn.execute(
                "INSERT OR IGNORE INTO campaign_events(campaign_id, lead_id) VALUES (?, ?)",
                (campaign_id, lead_id),
            )


def get_campaign_leads(campaign_id: int, path: str | None = None) -> list[dict[str, Any]]:
    init_db(path)
    with _connect(path) as conn:
        rows = conn.execute("""
            SELECT l.*, e.status AS campaign_status, e.consent_confirmed
            FROM campaign_events e JOIN leads l ON l.id=e.lead_id
            WHERE e.campaign_id=? ORDER BY l.name
        """, (campaign_id,))
        return [dict(row) for row in rows]


def update_campaign_event(campaign_id: int, lead_id: int, status: str, consent_confirmed: bool, path: str | None = None) -> None:
    if status not in {"pending", "opened", "sent", "replied", "opted_out"}:
        raise ValueError("Status de campanha inválido.")
    init_db(path)
    with _connect(path) as conn:
        conn.execute(
            """UPDATE campaign_events SET status=?, consent_confirmed=?, updated_at=CURRENT_TIMESTAMP
               WHERE campaign_id=? AND lead_id=?""",
            (status, int(consent_confirmed), campaign_id, lead_id),
        )


def get_leads(status: str | None = None, path: str | None = None) -> list[dict[str, Any]]:
    """Lista leads, opcionalmente filtrados por estado."""
    init_db(path)
    with _connect(path) as conn:
        if status:
            rows = conn.execute("SELECT * FROM leads WHERE status = ? ORDER BY updated_at DESC", (status,))
        else:
            rows = conn.execute("SELECT * FROM leads ORDER BY updated_at DESC")
        return [dict(row) for row in rows]



def update_lead_status(lead_id: int, status: str, path: str | None = None) -> None:
    """Atualiza o estágio comercial de um estabelecimento."""
    allowed = {"to_visit", "visited", "client"}
    if status not in allowed:
        raise ValueError("Status inválido.")
    init_db(path)
    with _connect(path) as conn:
        cursor = conn.execute(
            "UPDATE leads SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (status, lead_id),
        )
        if cursor.rowcount == 0:
            raise ValueError("Estabelecimento não encontrado.")
