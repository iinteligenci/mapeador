"""Interface web local do Mapeador; não expõe o serviço na rede pública."""
from __future__ import annotations

import asyncio
import os
import threading
import webbrowser
import time
from datetime import datetime, timedelta
from urllib.parse import quote
from typing import Any

from dotenv import load_dotenv
from flask import Flask, redirect, render_template_string, request, url_for, abort

from ai_agent.analyzer import analyze_lead_profiles
from ai_agent.research_planner import plan_deep_searches
from ai_agent.deep_enrichment import enrich_business_with_ai
from database.db import (get_leads, init_db, save_lead, update_analysis, update_lead_status, update_public_contacts, update_business_identity, save_campaign, get_campaigns, queue_campaign, get_campaign_leads, update_campaign_event, get_automation_settings, set_automation_settings, save_proposal, get_proposals)
from scraper.maps_scraper import search_google_maps
from scraper.public_contacts import find_public_business_contacts
from scraper.site_research import research_public_site

load_dotenv()
app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 1 * 1024 * 1024

@app.before_request
def require_hosted_password():
    """Protege a aplicação publicada; local continua acessível sem login."""
    if request.path == "/health":
        return None
    if os.getenv("RENDER") != "true":
        return None
    expected = os.getenv("MAPEADOR_PASSWORD", "")
    if not expected:
        abort(503, "Configure MAPEADOR_PASSWORD nas variáveis de ambiente do serviço.")
    from secrets import compare_digest
    supplied = request.authorization
    if not supplied or not compare_digest(supplied.username or "", "mapeador") or not compare_digest(supplied.password or "", expected):
        return ("Autenticação necessária", 401, {"WWW-Authenticate": 'Basic realm="Mapeador"'})
    return None

@app.get("/health")
def health_check():
    return {"status": "ok"}

PAGE = r"""
<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Mapeador | Prospecção inteligente</title>
<style>
:root{color-scheme:dark;--bg:#0b1220;--panel:#121d30;--line:#26354d;--muted:#a6b4ca;--text:#edf4ff;--blue:#4da3ff;--green:#35d49a}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(ellipse at top left,#162b49 0,#0b1220 48%);font:15px/1.5 Inter,Segoe UI,Arial,sans-serif;color:var(--text)}
main{max-width:1180px;margin:auto;padding:36px 22px 64px}.brand{display:flex;align-items:center;gap:12px}.mark{width:46px;height:46px;border-radius:14px;background:linear-gradient(135deg,#58b7ff,#5b6cff);display:grid;place-items:center;font-size:24px;font-weight:800;color:white}
h1{font-size:28px;line-height:1.15;margin:0} .sub{color:var(--muted);margin:5px 0 26px}
.panel{background:rgba(18,29,48,.94);border:1px solid var(--line);border-radius:18px;padding:22px;margin:18px 0;box-shadow:0 16px 48px #0002}
h2{font-size:18px;margin:0 0 16px}.formgrid{display:grid;grid-template-columns:minmax(220px,2fr) minmax(140px,1fr) minmax(220px,1.5fr);gap:14px}
label{display:block;color:var(--muted);font-size:13px;margin-bottom:6px}input,select{width:100%;border:1px solid #354761;background:#0c1627;color:var(--text);border-radius:10px;padding:12px;font:inherit}
button{border:0;border-radius:10px;padding:12px 18px;background:var(--blue);color:#071321;font-weight:750;cursor:pointer;margin-top:16px}button:disabled{opacity:.6;cursor:wait}
.note{font-size:12px;color:var(--muted);margin-top:12px}.stats{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}.stat{background:#0d1829;border:1px solid var(--line);border-radius:12px;padding:14px}.stat strong{display:block;font-size:24px}.stat span{font-size:12px;color:var(--muted)}
.alert{border-radius:12px;padding:13px 15px;margin:14px 0;background:#392b14;border:1px solid #79551e;color:#ffdda0}.success{background:#102e2a;border-color:#236d5c;color:#a9f3d9}
.results{display:grid;gap:14px}.lead{border:1px solid var(--line);background:#0d1829;border-radius:14px;padding:18px}.leadhead{display:flex;justify-content:space-between;gap:16px;align-items:start}.lead h3{margin:0 0 4px;font-size:18px}.category{color:var(--muted);font-size:13px}.score{white-space:nowrap;border-radius:99px;padding:5px 10px;background:#123a35;color:#83f0ce;font-weight:700;font-size:13px}.score.unknown{background:#302a1d;color:#ffdb91}
.details{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin-top:15px}.detail{border-top:1px solid #26354d;padding-top:9px;min-width:0}.detail b{display:block;color:var(--muted);font-size:12px;font-weight:500}.detail a{color:#83c5ff;overflow-wrap:anywhere}.detail div{overflow-wrap:anywhere}
.analysis{margin-top:15px;padding:13px;border-radius:10px;background:#14243a}.analysis b{font-size:13px}.analysis p{margin:5px 0}.draft{margin-top:10px;padding:12px;border-left:3px solid var(--blue);background:#101e31;white-space:pre-wrap}
.statusform{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-top:14px;padding-top:12px;border-top:1px solid var(--line)}.statusform select{max-width:220px}.statusform button{margin:0;padding:10px 13px}.nav{display:flex;gap:10px;flex-wrap:wrap;margin:18px 0}.nav a{color:#b9dcff;text-decoration:none;border:1px solid #354761;background:#122039;padding:9px 13px;border-radius:10px}.nav a:hover{border-color:var(--blue)}.empty{color:var(--muted);padding:18px 0}.footer{font-size:12px;color:var(--muted);text-align:center;margin-top:24px}
@media(max-width:900px){.stats{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:720px){main{padding:22px 14px}.formgrid,.stats,.details{grid-template-columns:1fr}h1{font-size:24px}.leadhead{flex-direction:column}.score{align-self:start}}
</style>
</head>
<body><main>
<header>
 <div class="brand"><div class="mark">M</div><div><h1>Mapeador</h1><div class="category">Inteligência comercial para negócios alimentícios</div></div></div>
 <p class="sub">Encontre estabelecimentos, investigue sua presença digital e organize oportunidades para revisão humana.</p>
 <nav class="nav"><a href="/">＋ Nova prospecção</a><a href="/history">▤ Estabelecimentos encontrados</a><a href="/visits">📍 Visitas presenciais</a><a href="/removed">🚫 Removidos</a><a href="/campaigns">✉ Campanhas</a><a href="/automatic">⚙ Modo automático</a><a href="/proposals/4k">Propostas 4K</a><a href="/proposals/digital">Propostas presença digital</a></nav>
</header>
<section class="panel">
 <h2>Nova prospecção</h2>
 <form id="searchForm" method="post" action="/search">
  <div class="formgrid">
   <div><label for="term">Tipo de negócio e localidade</label><input id="term" name="term" value="{{ term }}" required placeholder="Ex.: bares em Vila Velha ES"></div>
   <div><label for="limit">Quantidade máxima</label><select id="limit" name="limit">{% for n in [3,5,10,15] %}<option value="{{n}}" {% if limit == n %}selected{% endif %}>{{n}} negócios</option>{% endfor %}</select></div>

  </div>
  <button id="submitButton" type="submit">⌕ Iniciar prospecção</button>
  <div class="note">Esta etapa só encontra e salva estabelecimentos. Para cada empresa, escolha 4K Food Service, presença digital ou ambas e gere uma proposta quando quiser.</div>
 </form>
</section>
{% if error %}<div class="alert">{{ error }}</div>{% endif %}
{% if results is not none %}
<section class="panel">
 <h2>Estabelecimentos encontrados</h2>
 <div class="stat" style="max-width:360px"><strong>{{ results|length }}</strong><span>Novos estabelecimentos adicionados ao histórico</span></div>
 {% if results|length == 0 %}<p class="empty">Não encontrei novos estabelecimentos nessa consulta. Os resultados anteriores são ignorados automaticamente; tente ampliar a região ou mudar o termo para encontrar outros negócios alimentícios.</p>{% else %}
 <div class="results" style="margin-top:16px">
 {% for item in results %}
  {% set lead = item.lead %}{% set research = item.research %}{% set analyses = item.analyses %}
  <article class="lead">
   <div class="leadhead"><div><h3>{{ lead.name }}</h3><div class="category">{{ lead.category or "Categoria não identificada" }}</div></div>
   {% if analyses %}<div class="score">{{ analyses|length }} proposta(s) gerada(s)</div>{% else %}<div class="score unknown">Proposta não gerada</div>{% endif %}</div>
   <div class="details">
    <div class="detail"><b>Telefone</b><div>{{ lead.phone or "Não identificado publicamente" }}</div></div>
    <div class="detail"><b>Endereço</b><div>{{ research.address or lead.address or "Não identificado publicamente" }}</div></div>
    <div class="detail"><b>Site</b><div>{% if lead.website %}<a href="{{lead.website}}" target="_blank" rel="noopener">{{lead.website}}</a>{% else %}Não identificado publicamente{% endif %}</div></div>
    <div class="detail"><b>Instagram</b><div>{% if research.instagram %}<a href="{{research.instagram}}" target="_blank" rel="noopener">Abrir perfil</a>{% else %}Não identificado publicamente{% endif %}</div></div>
    <div class="detail"><b>Canais digitais</b><div>{{ research.channels|join(", ") if research.channels else "Não identificado publicamente" }}</div></div>
    <div class="detail"><b>Cardápio / catálogo</b><div>{% if research.menu_url %}<a href="{{research.menu_url}}" target="_blank" rel="noopener">Abrir cardápio</a>{% else %}Não identificado publicamente{% endif %}</div></div>
    <div class="detail"><b>Itens em páginas públicas</b><div>{{ research.menu_items[:12]|join(", ") if research.menu_items else "Não identificado publicamente" }}</div></div>
    <div class="detail"><b>Plataformas encontradas publicamente</b><div>{{ research.public_platforms|join(", ") if research.public_platforms else "Não identificado publicamente" }}</div></div>
   </div>
   {% if item.analyses %}
   {% for profile_key, analysis in item.analyses.items() %}
   <div class="analysis"><b>{{ "4K Food Service" if profile_key == "4k" else "Presença digital" }} · prioridade {{ analysis.score }}/100</b><p>{{ analysis.justificativa }}</p>
    <div class="draft"><b>Proposta comercial gerada — não enviada</b>
{{ analysis.mensagem }}</div></div>
   {% endfor %}
   {% elif item.error %}
   <div class="alert" style="margin-top:14px">{{ item.error }}</div>
   {% endif %}
   {% if item.contacts %}
   <div class="analysis"><b>Contato comercial público</b>
    <p><strong>Responsável:</strong> {{ item.contacts.contact_name or "Não identificado publicamente" }}</p>
    <p><strong>Cargo:</strong> {{ item.contacts.contact_role or "Não identificado publicamente" }}</p>
    <p><strong>Telefone:</strong> {{ item.contacts.contact_phone or "Não identificado publicamente" }}</p>
    <p><strong>WhatsApp:</strong> {{ item.contacts.contact_whatsapp or "Não identificado publicamente" }}</p>
    <p><strong>Confirmação:</strong> {{ item.contacts.contact_confidence or "Não identificado" }}</p>
    {% if item.contacts.contact_source %}<p><strong>Fonte:</strong> <a href="{{ item.contacts.contact_source }}" target="_blank" rel="noopener">Ver página de origem</a></p>{% endif %}
    {% for note in item.contacts.contact_notes %}<p class="note">{{ note }}</p>{% endfor %}
   </div>
   {% endif %}
   <form class="statusform" method="post" action="/contacts">
    <input type="hidden" name="lead_id" value="{{ item.lead_id }}">
    <input type="hidden" name="term" value="{{ term }}">
    <input type="hidden" name="limit" value="{{ limit }}">
    <input type="hidden" name="source" value="search">
    <button type="submit">Encontrar responsável e contatos públicos</button>
   </form>
   <form class="statusform" method="post" action="/proposal">
    <input type="hidden" name="lead_id" value="{{ item.lead_id }}">
    <input type="hidden" name="term" value="{{ term }}">
    <input type="hidden" name="limit" value="{{ limit }}">
    <label for="proposal-profile-{{ item.lead_id }}" style="margin:0">Gerar proposta para</label>
    <select id="proposal-profile-{{ item.lead_id }}" name="proposal_profile">
      <option value="4k">4K Food Service</option>
      <option value="digital">Presença digital</option>
      <option value="both">Ambas as empresas</option>
    </select>
    <input name="proposal_offer" placeholder="Oferta personalizada (opcional)" style="max-width:280px">
    <button type="submit">Gerar proposta</button>
   </form>
   <form class="statusform" method="post" action="/status">
    <input type="hidden" name="lead_id" value="{{ item.lead_id }}">
    <label for="status-{{ item.lead_id }}" style="margin:0">Etapa comercial</label>
    <select id="status-{{ item.lead_id }}" name="status">
      <option value="to_visit" selected>Para visitar</option>
      <option value="visited">Visitado</option>
      <option value="client">Cliente</option>
      <option value="in_person">Visita presencial (fora das campanhas)</option>
      <option value="removed">Removido (não prospectar)</option>
    </select>
    <button type="submit">Salvar etapa</button>
   </form>
   {% if research.research_notes %}<div class="note">{{ research.research_notes|join(" ") }}</div>{% endif %}
   {% if lead.link %}<div class="note"><a href="{{lead.link}}" target="_blank" rel="noopener">Ver no Google Maps ↗</a></div>{% endif %}
  </article>
 {% endfor %}
 </div>{% endif %}
 <div class="note">Dados públicos podem estar incompletos. “Não identificado” não significa que a empresa não tenha o canal ou a ferramenta.</div>
</section>
{% endif %}
<div class="footer">Mapeador · Pesquisa pública · Revisão humana obrigatória · Sem envio automático de mensagens</div>
</main>
<script>
document.getElementById('searchForm').addEventListener('submit', function(){
 const b=document.getElementById('submitButton'); b.disabled=true; b.textContent='Pesquisando… aguarde';
});
</script>
</body></html>
"""


@app.get("/")
def index():
    return render_template_string(
        PAGE, term="restaurantes em Vila Velha ES", limit=3,
        offer="", profile="both", reanalyze=False, results=None, analyzed=0, failed=0, skipped=0, error=None
    )


@app.post("/search")
def search():
    term = (request.form.get("term") or "").strip()
    offer = ""
    profile = "both"
    reanalyze = False
    try:
        limit = max(1, min(15, int(request.form.get("limit", "3"))))
    except ValueError:
        limit = 3
    if not term:
        return render_template_string(
            PAGE, term=term, limit=limit, offer=offer, profile=profile, reanalyze=reanalyze, results=None,
            analyzed=0, failed=0, skipped=0, error="Informe o que pesquisar e a localidade."
        ), 400

    db_path = os.getenv("DATABASE_PATH", "data/mapeador.sqlite3")
    init_db(db_path)
    try:
        known_links = {str(item.get("link") or "").split("?")[0].rstrip("/") for item in get_leads(path=db_path)}
        leads = asyncio.run(search_google_maps(term, limit, exclude_links=known_links))
    except Exception as exc:
        return render_template_string(
            PAGE, term=term, limit=limit, offer=offer, profile=profile, reanalyze=reanalyze, results=[],
            analyzed=0, failed=0, skipped=0, error=f"Falha na pesquisa do Maps: {type(exc).__name__}: {exc}"
        ), 500

    results: list[dict[str, Any]] = []
    skipped = 0
    for lead in leads:
        try:
            lead_id, inserted = save_lead(lead, db_path)
        except Exception:
            lead_id, inserted = None, True
        if not inserted:
            # Fallback: never show an already-saved business in fresh results.
            skipped += 1
            continue
        # Search results are quick: no website crawl and no Gemini call here.
        research = {
            "address": lead.get("address", ""),
            "instagram": "",
            "channels": [],
            "menu_url": lead.get("menu_url", ""),
            "menu_items": [],
            "public_platforms": [],
            "research_notes": [],
            "sources": [],
        }
        results.append({
            "lead": lead,
            "lead_id": lead_id,
            "research": research,
            "analyses": None,
            "error": None,
        })

    return render_template_string(
        PAGE, term=term, limit=limit, offer=offer, profile=profile, reanalyze=reanalyze, results=results,
        analyzed=0, failed=0, skipped=skipped, error=None
    )


@app.post("/contacts")
def enrich_public_contacts():
    db_path = os.getenv("DATABASE_PATH", "data/mapeador.sqlite3")
    try:
        lead_id = int(request.form.get("lead_id", ""))
    except (ValueError, TypeError):
        return "Estabelecimento inválido.", 400
    saved = next((item for item in get_leads(path=db_path) if item.get("id") == lead_id), None)
    if not saved:
        return "Estabelecimento não encontrado no histórico.", 404

    contacts = find_public_business_contacts(saved)
    update_public_contacts(lead_id, contacts, db_path)
    source = (request.form.get("source") or "history").strip()
    if source == "history":
        return redirect(url_for("history"))

    lead = {
        "name": saved.get("name", ""),
        "category": saved.get("category", ""),
        "link": saved.get("link", ""),
        "phone": saved.get("phone", ""),
        "address": "",
        "website": saved.get("website", ""),
    }
    research = {
        "address": "", "instagram": "", "channels": [], "menu_url": "",
        "menu_items": [], "public_platforms": [], "research_notes": [], "sources": [],
    }
    item = {
        "lead": lead, "lead_id": lead_id, "research": research,
        "analyses": None, "error": None, "contacts": contacts,
    }
    try:
        page_limit = max(1, min(15, int(request.form.get("limit", "3") or "3")))
    except ValueError:
        page_limit = 3
    return render_template_string(
        PAGE, term=request.form.get("term", "restaurantes em Vila Velha ES"),
        limit=page_limit, offer="", profile="both", reanalyze=False, results=[item],
        analyzed=0, failed=0, skipped=0, error=None
    )


@app.get("/campaigns")
def campaigns():
    return render_template_string(CAMPAIGNS_PAGE, campaigns=get_campaigns())


@app.post("/campaigns/create")
def create_campaign():
    name = (request.form.get("name") or "").strip()
    profile = (request.form.get("profile") or "4k").strip()
    message = (request.form.get("message") or "").strip()
    if profile not in {"4k", "digital"} or not message:
        return "Escolha uma empresa e escreva a mensagem antes de salvar.", 400
    db_path = os.getenv("DATABASE_PATH", "data/mapeador.sqlite3")
    search_term = (request.form.get("search_term") or "").strip()
    campaign_id = save_campaign(name, profile, message, db_path, search_term)
    leads = get_leads(path=db_path)
    eligible = [
        int(lead["id"]) for lead in leads
        if lead.get("status") not in {"in_person", "removed"}
        and (lead.get("contact_whatsapp") or lead.get("contact_phone") or lead.get("phone"))
    ]
    queue_campaign(campaign_id, eligible, db_path)
    return redirect(url_for("campaign_detail", campaign_id=campaign_id))


@app.get("/campaigns/<int:campaign_id>")
def campaign_detail(campaign_id: int):
    db_path = os.getenv("DATABASE_PATH", "data/mapeador.sqlite3")
    campaign = next((c for c in get_campaigns(db_path) if c["id"] == campaign_id), None)
    if not campaign:
        return "Campanha não encontrada.", 404
    rows = get_campaign_leads(campaign_id, db_path)
    for lead in rows:
        raw = lead.get("contact_whatsapp") or lead.get("contact_phone") or lead.get("phone") or ""
        digits = "".join(ch for ch in raw if ch.isdigit())
        if len(digits) in {10, 11}:
            digits = "55" + digits
        lead["wa_url"] = f"https://wa.me/{digits}?text={quote(campaign['message'])}" if len(digits) >= 12 else ""
        lead["chosen_phone"] = raw
    return render_template_string(CAMPAIGN_DETAIL_PAGE, campaign=campaign, leads=rows)


@app.post("/campaigns/event")
def campaign_event():
    db_path = os.getenv("DATABASE_PATH", "data/mapeador.sqlite3")
    campaign_id = int(request.form.get("campaign_id", "0"))
    lead_id = int(request.form.get("lead_id", "0"))
    status = (request.form.get("status") or "pending").strip()
    consent = request.form.get("consent") == "yes"
    if status in {"opened", "sent", "replied"} and not consent:
        return "Confirme que existe autorização para contato antes de registrar envio.", 400
    update_campaign_event(campaign_id, lead_id, status, consent, db_path)
    return redirect(url_for("campaign_detail", campaign_id=campaign_id))


@app.post("/proposal")
def generate_proposal():
    db_path = os.getenv("DATABASE_PATH", "data/mapeador.sqlite3")
    try:
        lead_id = int(request.form.get("lead_id", ""))
    except (ValueError, TypeError):
        return "Estabelecimento inválido.", 400

    records = get_leads(path=db_path)
    saved = next((item for item in records if item.get("id") == lead_id), None)
    if not saved:
        return "Estabelecimento não encontrado no histórico.", 404

    profile = (request.form.get("proposal_profile") or "4k").strip()
    if profile not in {"4k", "digital", "both"}:
        profile = "4k"
    selected_profiles = ["4k", "digital"] if profile == "both" else [profile]
    offer = (request.form.get("proposal_offer") or "").strip()
    lead = {
        "name": saved.get("name", ""),
        "category": saved.get("category", ""),
        "link": saved.get("link", ""),
        "phone": saved.get("phone", ""),
        "address": "",
        "website": saved.get("website", ""),
    }
    error = None
    analyses = None
    try:
        research = research_public_site(lead)
        analysis_lead = {
            **lead,
            "address": research.get("address") or lead.get("address", ""),
            "instagram": research.get("instagram", ""),
            "channels": research.get("channels", []),
            "menu_url": research.get("menu_url", ""),
            "menu_items": research.get("menu_items", []),
            "public_platforms": research.get("public_platforms", []),
            "research_notes": research.get("research_notes", []),
        }
        analyses = analyze_lead_profiles(analysis_lead, selected_profiles, offer)
        combined = {
            "score": max(item["score"] for item in analyses.values()),
            "justificativa": "\n".join(
                f"{'4K Food Service' if key == '4k' else 'Presença digital'}: {item['justificativa']}"
                for key, item in analyses.items()
            ),
            "mensagem": "\n\n".join(
                f"{'4K Food Service' if key == '4k' else 'Presença digital'} — proposta não enviada:\n{item['mensagem']}"
                for key, item in analyses.items()
            ),
        }
        update_analysis(lead_id, combined, db_path)
    except Exception as exc:
        research = locals().get("research", {
            "address": "", "instagram": "", "channels": [], "menu_url": "",
            "menu_items": [], "public_platforms": [], "research_notes": [], "sources": []
        })
        error = f"Não foi possível gerar a proposta ({type(exc).__name__}: {exc}). Os dados do estabelecimento continuam salvos."

    item = {"lead": lead, "lead_id": lead_id, "research": research, "analyses": analyses, "error": error}
    try:
        page_limit = max(1, min(15, int(request.form.get("limit", "3") or "3")))
    except ValueError:
        page_limit = 3
    return render_template_string(
        PAGE, term=request.form.get("term", "restaurantes em Vila Velha ES"),
        limit=page_limit, offer="", profile=profile, reanalyze=False, results=[item],
        analyzed=1 if analyses else 0, failed=0 if analyses else 1, skipped=0, error=None
    )


STATUS_LABELS = {
    "to_visit": "Para visitar",
    "visited": "Visitado",
    "client": "Cliente",
    "in_person": "Visita presencial",
    "removed": "Removido",
}


@app.get("/history")
def history():
    db_path = os.getenv("DATABASE_PATH", "data/mapeador.sqlite3")
    init_db(db_path)
    selected = (request.args.get("status") or "all").strip()
    if selected not in {"all", "to_visit", "visited", "client"}:
        selected = "all"
    leads = [lead for lead in get_leads(path=db_path) if lead.get("status") not in {"in_person", "removed"}]
    for lead in leads:
        if lead.get("status") not in STATUS_LABELS:
            lead["status"] = "to_visit"
        lead["status_label"] = STATUS_LABELS[lead["status"]]
    if selected != "all":
        leads = [lead for lead in leads if lead["status"] == selected]
    return render_template_string(HISTORY_PAGE, leads=leads, selected=selected, labels=STATUS_LABELS)


@app.get("/visits")
def visits():
    db_path = os.getenv("DATABASE_PATH", "data/mapeador.sqlite3")
    init_db(db_path)
    leads = [lead for lead in get_leads(path=db_path) if lead.get("status") == "in_person"]
    for lead in leads:
        lead["status_label"] = "Visita presencial"
    return render_template_string(VISITS_PAGE, leads=leads, selected="in_person", labels=STATUS_LABELS)


@app.get("/removed")
def removed():
    db_path = os.getenv("DATABASE_PATH", "data/mapeador.sqlite3")
    init_db(db_path)
    leads = [lead for lead in get_leads(path=db_path) if lead.get("status") == "removed"]
    for lead in leads:
        lead["status_label"] = "Removido"
    return render_template_string(REMOVED_PAGE, leads=leads, selected="removed", labels=STATUS_LABELS)


@app.post("/status")
def set_status():
    db_path = os.getenv("DATABASE_PATH", "data/mapeador.sqlite3")
    try:
        lead_id = int(request.form.get("lead_id", ""))
        status = request.form.get("status", "")
        update_lead_status(lead_id, status, db_path)
    except (ValueError, TypeError) as exc:
        return f"Não foi possível atualizar a etapa: {exc}", 400
    return redirect(url_for("visits" if status == "in_person" else "removed" if status == "removed" else "history"))


HISTORY_PAGE = r"""
<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Mapeador | Estabelecimentos encontrados</title>
<style>
:root{color-scheme:dark;--line:#26354d;--muted:#a6b4ca;--text:#edf4ff;--blue:#4da3ff}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(ellipse at top left,#162b49 0,#0b1220 48%);font:15px/1.5 Inter,Segoe UI,Arial,sans-serif;color:var(--text)}
main{max-width:1180px;margin:auto;padding:34px 22px 64px}.brand{display:flex;gap:12px;align-items:center}.mark{width:46px;height:46px;border-radius:14px;background:linear-gradient(135deg,#58b7ff,#5b6cff);display:grid;place-items:center;font-size:24px;font-weight:800}h1{font-size:27px;margin:0}.sub,.muted{color:var(--muted)}.panel{background:#121d30;border:1px solid var(--line);border-radius:16px;padding:20px;margin:18px 0}.nav{display:flex;gap:10px;flex-wrap:wrap;margin:18px 0}.nav a{color:#b9dcff;text-decoration:none;border:1px solid #354761;background:#122039;padding:9px 13px;border-radius:10px}.filters{display:flex;gap:8px;flex-wrap:wrap;margin:12px 0 20px}.filters a{padding:8px 12px;border:1px solid var(--line);border-radius:9px;text-decoration:none;color:var(--text)}.filters a.active{background:#1c4772;border-color:#4da3ff}.entry{background:#0d1829;border:1px solid var(--line);border-radius:13px;padding:16px;margin:12px 0}.top{display:flex;justify-content:space-between;gap:12px;align-items:start}.entry h3{margin:0}.pill{border-radius:99px;padding:4px 10px;background:#18344f;color:#b9dcff;font-size:12px}.meta{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;margin:12px 0}.meta div{overflow-wrap:anywhere}.meta b{display:block;font-size:12px;color:var(--muted);font-weight:500}a{color:#83c5ff}select,button{border:1px solid #354761;background:#0c1627;color:var(--text);padding:10px;border-radius:9px;font:inherit}.statusform{display:flex;gap:8px;flex-wrap:wrap;align-items:center;border-top:1px solid var(--line);padding-top:12px}.statusform button{background:var(--blue);color:#071321;font-weight:700;cursor:pointer}.empty{color:var(--muted);padding:22px 0}.hint{font-size:12px;color:var(--muted)}@media(max-width:650px){main{padding:20px 13px}.meta{grid-template-columns:1fr}.top{flex-direction:column}}
</style></head><body><main>
<header><div class="brand"><div class="mark">M</div><div><h1>Estabelecimentos encontrados</h1><div class="muted">Seu histórico comercial fica salvo no banco local.</div></div></div>
<nav class="nav"><a href="/">＋ Nova prospecção</a><a href="/history">▤ Estabelecimentos encontrados</a><a href="/visits">📍 Visitas presenciais</a><a href="/removed">🚫 Removidos</a><a href="/campaigns">✉ Campanhas</a></nav></header>
<section class="panel"><h2>{{ leads|length }} estabelecimento(s) nesta lista</h2>
<div class="filters">
<a href="/history" class="{{ 'active' if selected == 'all' else '' }}">Todos</a>
<a href="/history?status=to_visit" class="{{ 'active' if selected == 'to_visit' else '' }}">Para visitar</a>
<a href="/history?status=visited" class="{{ 'active' if selected == 'visited' else '' }}">Visitados</a>
<a href="/history?status=client" class="{{ 'active' if selected == 'client' else '' }}">Clientes</a>
</div>
{% if not leads %}<div class="empty">Nenhum estabelecimento nesta categoria ainda. Faça uma busca para adicionar negócios ao histórico.</div>{% endif %}
{% for lead in leads %}<article class="entry">
<div class="top"><div><h3>{{ lead.name }}</h3><div class="muted">{{ lead.category or "Categoria não identificada" }}</div></div><span class="pill">{{ lead.status_label }}</span></div>
<div class="meta">
<div><b>Telefone comercial</b>{{ lead.phone or "Não identificado publicamente" }}</div>
<div><b>Responsável público</b>{{ lead.contact_name or "Não identificado publicamente" }}{% if lead.contact_role %} · {{ lead.contact_role }}{% endif %}</div>
<div><b>Telefone do contato publicado</b>{{ lead.contact_phone or "Não identificado publicamente" }}</div>
<div><b>WhatsApp comercial</b>{{ lead.contact_whatsapp or "Não identificado publicamente" }}</div>
<div><b>Fonte do contato</b>{% if lead.contact_source %}<a href="{{lead.contact_source}}" target="_blank" rel="noopener">Ver página de origem</a>{% else %}Não identificado publicamente{% endif %}</div>
<div><b>Confiança da identificação</b>{{ lead.contact_confidence or "Não identificado" }}</div>
<div><b>Site</b>{% if lead.website %}<a href="{{lead.website}}" target="_blank" rel="noopener">{{lead.website}}</a>{% else %}Não identificado publicamente{% endif %}</div>
<div><b>Prioridade preliminar</b>{{ (lead.score|string + "/100") if lead.score is not none else "Ainda não avaliada" }}</div>
<div><b>Última atualização</b>{{ lead.updated_at }}</div>
<div><b>Análise</b>{{ lead.justification or "Análise não registrada" }}</div>
</div>
{% if lead.message %}<details><summary>Ver última proposta gerada (não enviada)</summary><p style="white-space:pre-wrap">{{ lead.message }}</p></details>{% endif %}
{% if lead.link %}<p><a href="{{lead.link}}" target="_blank" rel="noopener">Abrir no Google Maps ↗</a></p>{% endif %}
<form class="statusform" method="post" action="/contacts">
<input type="hidden" name="lead_id" value="{{lead.id}}"><input type="hidden" name="source" value="history">
<button type="submit">Encontrar responsável e contatos públicos</button></form>
<form class="statusform" method="post" action="/proposal">
<input type="hidden" name="lead_id" value="{{lead.id}}"><input type="hidden" name="term" value="Estabelecimento do histórico"><input type="hidden" name="limit" value="3">
<label for="history-proposal-{{lead.id}}" class="muted">Gerar proposta para:</label>
<select id="history-proposal-{{lead.id}}" name="proposal_profile"><option value="4k">4K Food Service</option><option value="digital">Presença digital</option><option value="both">Ambas as empresas</option></select>
<input name="proposal_offer" placeholder="Oferta personalizada (opcional)" style="max-width:260px">
<button type="submit">Gerar proposta</button></form>
<form class="statusform" method="post" action="/status"><input type="hidden" name="lead_id" value="{{lead.id}}">
<label for="history-status-{{lead.id}}" class="muted">Alterar etapa:</label>
<select id="history-status-{{lead.id}}" name="status">{% for value,label in labels.items() %}<option value="{{value}}" {% if lead.status == value %}selected{% endif %}>{{label}}</option>{% endfor %}</select>
<button type="submit">Salvar</button></form>
</article>{% endfor %}
<p class="hint">A busca ignora estabelecimentos já encontrados. Para criar uma mensagem, escolha a empresa e clique em “Gerar proposta”. O histórico fica neste computador, no banco SQLite local.</p>
</section></main></body></html>
"""

REMOVED_PAGE = HISTORY_PAGE.replace("Mapeador | Estabelecimentos encontrados", "Mapeador | Removidos").replace("<h1>Estabelecimentos encontrados</h1>", "<h1>Estabelecimentos removidos</h1>").replace("Seu histórico comercial fica salvo no banco local.", "Lista de locais que você já conhece ou não pode atender. Ficam excluídos da prospecção e das campanhas.").replace("{{ leads|length }} estabelecimento(s) nesta lista", "{{ leads|length }} estabelecimento(s) removido(s)").replace('<div class="filters">', '<div class="filters" style="display:none">')

VISITS_PAGE = HISTORY_PAGE.replace("Mapeador | Estabelecimentos encontrados", "Mapeador | Visitas presenciais").replace("<h1>Estabelecimentos encontrados</h1>", "<h1>Visitas presenciais</h1>").replace("Seu histórico comercial fica salvo no banco local.", "Lista separada de estabelecimentos reservados para abordagem presencial. Não entram nas campanhas nem na lista geral.").replace("{{ leads|length }} estabelecimento(s) nesta lista", "{{ leads|length }} estabelecimento(s) para visita presencial").replace('<div class="filters">', '<div class="filters" style="display:none">')

CAMPAIGNS_PAGE = r"""
<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Mapeador | Campanhas</title><style>
body{margin:0;background:#0b1220;color:#edf4ff;font:15px/1.5 Segoe UI,Arial}main{max-width:1000px;margin:auto;padding:28px 16px}.panel,.entry{background:#121d30;border:1px solid #26354d;border-radius:14px;padding:18px;margin:14px 0}input,textarea,select{box-sizing:border-box;width:100%;background:#0c1627;color:#edf4ff;border:1px solid #354761;border-radius:9px;padding:11px;font:inherit;margin:5px 0 12px}button,.btn{display:inline-block;background:#4da3ff;color:#071321;border:0;border-radius:9px;padding:10px 14px;font-weight:700;text-decoration:none;cursor:pointer}a{color:#83c5ff}.nav{display:flex;gap:12px;margin:16px 0}.muted{color:#a6b4ca;font-size:13px}
</style></head><body><main><h1>Central de campanhas</h1><p class="muted">Você cria e revisa a mensagem. A abertura do WhatsApp é manual; nada é enviado automaticamente.</p><nav class="nav"><a href="/">Nova prospecção</a><a href="/history">Estabelecimentos encontrados</a><a href="/visits">Visitas presenciais</a><a href="/removed">Removidos</a></nav>
<section class="panel"><h2>Nova campanha</h2><form method="post" action="/campaigns/create">
<label>Nome da campanha</label><input name="name" placeholder="Ex.: Oferta de outubro">
<label>Empresa</label><select name="profile"><option value="4k">4K Food Service</option><option value="digital">Presença Digital</option></select>
<label>Termo para continuar prospectando (opcional)</label><input name="search_term" placeholder="Ex.: restaurantes em Vila Velha ES">
<label>Mensagem que será usada no WhatsApp</label><textarea name="message" rows="6" required placeholder="Escreva e revise a mensagem antes de criar a campanha."></textarea>
<button type="submit">Salvar mensagem e preparar lista</button></form><p class="muted">A lista inclui contatos públicos já cadastrados. Antes de contatar alguém, confirme que há base legal e autorização apropriada; respeite pedidos para não receber mensagens.</p></section>
<section class="panel"><h2>Campanhas salvas</h2>{% for c in campaigns %}<div class="entry"><strong>{{c.name}}</strong> · {{'4K Food Service' if c.profile == '4k' else 'Presença Digital'}}<p class="muted">{{c.created_at}} · {{c.queued_count}} contatos na fila{% if c.search_term %} · busca contínua: {{c.search_term}}{% endif %}</p><a class="btn" href="/campaigns/{{c.id}}">Abrir campanha</a></div>{% else %}<p class="muted">Nenhuma campanha criada ainda.</p>{% endfor %}</section></main></body></html>
"""

CAMPAIGN_DETAIL_PAGE = r"""
<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Campanha</title><style>
body{margin:0;background:#0b1220;color:#edf4ff;font:15px/1.5 Segoe UI,Arial}main{max-width:1000px;margin:auto;padding:28px 16px}.panel,.entry{background:#121d30;border:1px solid #26354d;border-radius:14px;padding:18px;margin:14px 0}a{color:#83c5ff}.btn,button{display:inline-block;background:#4da3ff;color:#071321;border:0;border-radius:9px;padding:10px 14px;font-weight:700;text-decoration:none;cursor:pointer}input,select{background:#0c1627;color:#edf4ff;border:1px solid #354761;border-radius:9px;padding:9px}label,.muted{color:#a6b4ca;font-size:13px}.draft{white-space:pre-wrap;background:#0c1627;padding:12px;border-radius:9px}.entry form{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-top:10px}
</style></head><body><main><p><a href="/campaigns">← Campanhas</a></p><h1>{{campaign.name}}</h1><p class="muted">{{'4K Food Service' if campaign.profile == '4k' else 'Presença Digital'}} · {{leads|length}} contatos</p><section class="panel"><h2>Mensagem aprovada por você</h2><div class="draft">{{campaign.message}}</div><p class="muted">Para abrir a conversa, marque a confirmação de autorização aplicável e clique em Abrir WhatsApp. Você ainda precisa conferir e enviar dentro do WhatsApp.</p></section>
{% for lead in leads %}<article class="entry"><h3>{{lead.name}}</h3><p>{{lead.category}} · {{lead.chosen_phone or 'Sem telefone público'}}</p><p class="muted">WhatsApp: {{lead.contact_whatsapp or 'não confirmado'}} · CNPJ: {{lead.cnpj or 'não identificado publicamente'}}</p>
{% if lead.wa_url %}<a class="btn" href="{{lead.wa_url}}" target="_blank" rel="noopener">Abrir mensagem no WhatsApp</a>{% else %}<p class="muted">Número ausente ou inválido para link do WhatsApp.</p>{% endif %}
<form method="post" action="/campaigns/event"><input type="hidden" name="campaign_id" value="{{campaign.id}}"><input type="hidden" name="lead_id" value="{{lead.id}}"><label><input type="checkbox" name="consent" value="yes" {% if lead.consent_confirmed %}checked{% endif %}> Confirmo que posso contatar este estabelecimento</label><select name="status"><option value="pending" {% if lead.campaign_status == 'pending' %}selected{% endif %}>Pendente</option><option value="opened" {% if lead.campaign_status == 'opened' %}selected{% endif %}>Conversa aberta</option><option value="sent" {% if lead.campaign_status == 'sent' %}selected{% endif %}>Mensagem enviada manualmente</option><option value="replied" {% if lead.campaign_status == 'replied' %}selected{% endif %}>Respondeu</option><option value="opted_out" {% if lead.campaign_status == 'opted_out' %}selected{% endif %}>Não deseja contato</option></select><button type="submit">Salvar status</button></form>
{% if lead.campaign_status == 'opted_out' %}<p class="muted">Este contato marcou que não deseja contato nesta campanha. Não o contate novamente.</p>{% endif %}</article>{% else %}<p>Nenhum contato na fila. Pesquise e cadastre estabelecimentos primeiro.</p>{% endfor %}</main></body></html>
"""



AUTO_PAGE = r"""
<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Mapeador | Modo automático</title>
<style>body{margin:0;background:#0b1220;color:#edf4ff;font:15px/1.5 Segoe UI,Arial}main{max-width:900px;margin:auto;padding:28px 16px}.panel{background:#121d30;border:1px solid #26354d;border-radius:14px;padding:20px;margin:16px 0}input,select{box-sizing:border-box;width:100%;background:#0c1627;color:#edf4ff;border:1px solid #354761;border-radius:9px;padding:12px;font:inherit;margin:6px 0 14px}button,.btn{display:inline-block;background:#4da3ff;color:#071321;border:0;border-radius:9px;padding:11px 15px;font-weight:700;text-decoration:none;cursor:pointer}a{color:#83c5ff}.muted{color:#a6b4ca}.nav{display:flex;gap:10px;flex-wrap:wrap;margin:16px 0}.nav a{border:1px solid #354761;padding:8px 11px;border-radius:8px;text-decoration:none}</style></head><body><main>
<h1>Modo automático</h1><p class="muted">O Mapeador pode pesquisar negócios, complementar dados públicos e criar rascunhos separados para cada canal de contato e para cada empresa. O computador e o Mapeador precisam permanecer ligados.</p>
<nav class="nav"><a href="/">Nova prospecção</a><a href="/history">Encontrados</a><a href="/proposals/4k">Propostas 4K</a><a href="/proposals/digital">Propostas presença digital</a><a href="/campaigns">Campanhas</a></nav>
<section class="panel"><h2>Controle da automação</h2><p><strong>Status:</strong> <span style="color:{{ '#35d49a' if settings.enabled else '#ffcc80' }};font-weight:800">{{ 'LIGADO' if settings.enabled else 'DESLIGADO' }}</span></p>
<form method="post" action="/automatic/toggle" style="display:flex;gap:10px;flex-wrap:wrap">
<button type="submit" name="enabled" value="yes" style="background:#35d49a">▶ Ligar automação</button>
<button type="submit" name="enabled" value="no" style="background:#ffcc80">Ⅱ Desligar automação</button>
</form>
<h2 style="margin-top:24px">Configuração da pesquisa</h2>
<form method="post" action="/automatic/save">
<label>O que pesquisar (tipo de negócio + localidade)</label><input name="search_term" required value="{{settings.search_term}}" placeholder="Ex.: restaurantes e bares em Vila Velha ES">
<label>Novos negócios por ciclo</label><select name="batch_size">{% for n in [1,2,3,5,10] %}<option value="{{n}}" {% if settings.batch_size == n %}selected{% endif %}>{{n}}</option>{% endfor %}</select>
<button type="submit">Salvar configuração</button></form>
<p class="muted">Quando ligada, a automação roda em ciclos de aproximadamente 5 minutos. Cada ciclo também leva tempo para executar as buscas. O computador e o programa precisam permanecer ligados. Limites de acesso, falhas de sites e limites da API podem atrasar a pesquisa; o sistema não contorna bloqueios.</p>
<p class="muted"><strong>Importante:</strong> propostas são apenas rascunhos para revisão humana. O Mapeador não envia mensagens automaticamente. Contatos só são usados quando encontrados em páginas públicas; dados não confirmados não são inventados.</p></section></main></body></html>
"""

PROPOSALS_PAGE = r"""
<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Propostas automáticas</title>
<style>body{margin:0;background:#0b1220;color:#edf4ff;font:15px/1.5 Segoe UI,Arial}main{max-width:1050px;margin:auto;padding:28px 16px}.panel,.entry{background:#121d30;border:1px solid #26354d;border-radius:14px;padding:18px;margin:14px 0}a{color:#83c5ff}.nav{display:flex;gap:10px;flex-wrap:wrap;margin:16px 0}.nav a{border:1px solid #354761;padding:8px 11px;border-radius:8px;text-decoration:none}.muted{color:#a6b4ca;font-size:13px}.draft{white-space:pre-wrap;background:#0c1627;padding:14px;border-radius:9px}.tabs{display:flex;gap:10px;flex-wrap:wrap}.tabs a{padding:10px 14px;border:1px solid #354761;border-radius:9px;text-decoration:none}.active{background:#1c4772}</style></head><body><main>
<h1>Propostas geradas automaticamente</h1><nav class="nav"><a href="/automatic">Modo automático</a><a href="/history">Estabelecimentos encontrados</a><a href="/campaigns">Campanhas</a></nav>
<div class="tabs"><a class="{{'active' if profile == '4k' else ''}}" href="/proposals/4k">4K Food Service ({{count4k}})</a><a class="{{'active' if profile == 'digital' else ''}}" href="/proposals/digital">Presença digital ({{countdigital}})</a></div>
<p class="muted">Cada cartão é um rascunho separado por empresa e canal público encontrado. Nenhuma mensagem foi enviada.</p>
{% for p in proposals %}<article class="entry"><h2>{{p.lead_name}}</h2><p class="muted">{{p.category}} · {{'4K Food Service' if p.profile == '4k' else 'Presença digital'}} · Prioridade preliminar {{p.score}}/100</p>
<p><strong>Canal:</strong> {{p.contact_type}} · {{p.contact_value or 'Contato comercial público'}}</p><p>{{p.justification}}</p><div class="draft">{{p.message}}</div>
{% if p.source_url %}<p><a href="{{p.source_url}}" target="_blank" rel="noopener">Ver fonte pública do contato</a></p>{% endif %}
<p class="muted">Rascunho salvo em {{p.created_at}}. Revise os dados, a adequação da oferta e a base legal antes de qualquer abordagem.</p></article>{% else %}<p class="muted">Ainda não há propostas para esta empresa. Ative o modo automático e aguarde a pesquisa e a coleta de contatos públicos.</p>{% endfor %}
</main></body></html>
"""


@app.get("/automatic")
def automatic_mode():
    settings = get_automation_settings(os.getenv("DATABASE_PATH", "data/mapeador.sqlite3"))
    return render_template_string(AUTO_PAGE, settings=settings)


@app.post("/automatic/toggle")
def automatic_toggle():
    enabled = request.form.get("enabled") == "yes"
    db_path = os.getenv("DATABASE_PATH", "data/mapeador.sqlite3")
    settings = get_automation_settings(db_path)
    set_automation_settings(enabled, settings.get("search_term") or "restaurantes em Vila Velha ES",
                            int(settings.get("batch_size") or 3), db_path)
    return redirect(url_for("automatic_mode"))


@app.post("/automatic/save")
def automatic_save():
    term = (request.form.get("search_term") or "").strip()
    db_path = os.getenv("DATABASE_PATH", "data/mapeador.sqlite3")
    try:
        size = int(request.form.get("batch_size", "3"))
        # Preserve the current on/off state when only changing search settings.
        current = get_automation_settings(db_path)
        set_automation_settings(bool(current.get("enabled")), term, size, db_path)
    except (ValueError, TypeError) as exc:
        return f"Configuração inválida: {exc}", 400
    return redirect(url_for("automatic_mode"))


@app.get("/proposals/<profile>")
def proposals_page(profile: str):
    if profile not in {"4k", "digital"}:
        return "Empresa inválida.", 404
    db_path = os.getenv("DATABASE_PATH", "data/mapeador.sqlite3")
    all_proposals = get_proposals(path=db_path)
    proposals = [p for p in all_proposals if p.get("profile") == profile]
    return render_template_string(PROPOSALS_PAGE, profile=profile, proposals=proposals,
        count4k=sum(1 for p in all_proposals if p.get("profile") == "4k"),
        countdigital=sum(1 for p in all_proposals if p.get("profile") == "digital"))


def _background_research_loop() -> None:
    """Pesquisa continuamente quando ativada, enriquece dados públicos e gera rascunhos por perfil/contato."""
    while True:
        try:
            db_path = os.getenv("DATABASE_PATH", "data/mapeador.sqlite3")
            settings = get_automation_settings(db_path)
            if settings.get("enabled"):
                records = get_leads(path=db_path)
                known_links = {str(item.get("link") or "").split("?")[0].rstrip("/") for item in records}
                try:
                    base_term = settings.get("search_term") or "restaurantes em Vila Velha ES"
                    batch_size = int(settings.get("batch_size") or 3)
                    # Gemini plans several targeted search formulations; each result is still verified by Maps.
                    search_queries = plan_deep_searches(base_term, limit=4)
                    found_count = 0
                    for query in search_queries:
                        if found_count >= batch_size:
                            break
                        try:
                            found = asyncio.run(search_google_maps(
                                query, max(1, batch_size - found_count), exclude_links=known_links))
                            for new_lead in found:
                                lead_id, inserted = save_lead(new_lead, db_path)
                                normalized = str(new_lead.get("link") or "").split("?")[0].rstrip("/")
                                known_links.add(normalized)
                                if inserted:
                                    found_count += 1
                                if found_count >= batch_size:
                                    break
                        except Exception as query_exc:
                            print(f"Mapeador automático — consulta '{query}': {type(query_exc).__name__}: {query_exc}")
                except Exception as exc:
                    print(f"Mapeador automático — pesquisa aprofundada: {type(exc).__name__}: {exc}")

                # Refresh records after discovery; process a small batch each cycle to limit load.
                records = get_leads(path=db_path)
                processed = 0
                for saved in records:
                    if saved.get("status") in {"removed", "in_person"}:
                        continue
                    checked_text = saved.get("contact_checked_at") or ""
                    try:
                        checked_at = datetime.fromisoformat(checked_text) if checked_text else None
                    except (ValueError, TypeError):
                        checked_at = None
                    # Retry weekly while any useful channel remains missing; preserve prior public data.
                    contacts_incomplete = not (
                        (saved.get("contact_whatsapp") or saved.get("contact_whatsapps"))
                        and (saved.get("contact_emails"))
                    )
                    contacts_due = checked_at is None or (
                        contacts_incomplete and checked_at < datetime.now() - timedelta(days=7)
                    )
                    if not contacts_due:
                        continue
                    # Count attempts, not only successes, so repeated failures cannot monopolize
                    # the worker and block later establishments.
                    processed += 1
                    try:
                        # AI-assisted web research runs before the site scraper, helping discover
                        # official pages and public contact channels missed by Maps/site-only parsing.
                        ai_research = enrich_business_with_ai(saved)
                        lead_for_contacts = {
                            **saved,
                            "website": saved.get("website") or ai_research.get("website", ""),
                        }
                        contacts = find_public_business_contacts(lead_for_contacts)
                        # Merge only sourced, publicly discovered AI results; keep prior values.
                        contacts["contact_emails"] = list(dict.fromkeys(
                            list(contacts.get("contact_emails") or []) + list(ai_research.get("emails") or [])
                        ))
                        contacts["contact_phones"] = list(dict.fromkeys(
                            list(contacts.get("contact_phones") or []) + list(ai_research.get("phones") or [])
                        ))
                        contacts["contact_whatsapps"] = list(dict.fromkeys(
                            list(contacts.get("contact_whatsapps") or []) + list(ai_research.get("whatsapps") or [])
                        ))
                        if not contacts.get("contact_email") and contacts["contact_emails"]:
                            contacts["contact_email"] = contacts["contact_emails"][0]
                        if not contacts.get("contact_whatsapp") and contacts["contact_whatsapps"]:
                            contacts["contact_whatsapp"] = contacts["contact_whatsapps"][0]
                        if not contacts.get("contact_phone") and contacts["contact_phones"]:
                            contacts["contact_phone"] = contacts["contact_phones"][0]
                        contacts["contact_sources"] = list(dict.fromkeys(
                            list(contacts.get("contact_sources") or []) + list(ai_research.get("sources") or [])
                        ))
                        if ai_research.get("website") and not saved.get("website"):
                            saved["website"] = ai_research["website"]
                        update_public_contacts(int(saved["id"]), contacts, db_path)
                        update_business_identity(int(saved["id"]), contacts.get("cnpj", ""),
                                                 contacts.get("cnpj_source", ""), db_path)
                        research = research_public_site({
                            **saved,
                            "website": saved.get("website") or ai_research.get("website", ""),
                            "menu_url": ai_research.get("menu_url") or saved.get("menu_url", ""),
                        })
                        if ai_research.get("instagram") and not research.get("instagram"):
                            research["instagram"] = ai_research["instagram"]
                        if ai_research.get("menu_url") and not research.get("menu_url"):
                            research["menu_url"] = ai_research["menu_url"]
                        if ai_research.get("notes"):
                            research.setdefault("research_notes", []).extend(ai_research["notes"])
                        if ai_research.get("sources"):
                            research.setdefault("sources", []).extend(ai_research["sources"])
                        endpoints = []
                        for value in contacts.get("contact_whatsapps", []):
                            endpoints.append(("WhatsApp", value, next(iter(contacts.get("contact_sources", [])), contacts.get("contact_source", ""))))
                        for value in contacts.get("contact_phones", []):
                            endpoints.append(("Telefone", value, contacts.get("contact_source", "")))
                        for value in contacts.get("contact_emails", []):
                            endpoints.append(("E-mail", value, contacts.get("contact_source", "")))
                        # Fallback to the public business number from Maps if the site has no channels.
                        if not endpoints:
                            raw = contacts.get("contact_whatsapp") or contacts.get("contact_phone") or saved.get("phone") or ""
                            if raw:
                                endpoints.append(("Telefone comercial", raw, contacts.get("contact_source") or saved.get("link", "")))
                        if endpoints:
                            lead_for_ai = {
                                **saved,
                                "address": saved.get("address", ""),
                                "instagram": research.get("instagram", ""),
                                "channels": research.get("channels", []),
                                "menu_url": research.get("menu_url", ""),
                                "menu_items": research.get("menu_items", []),
                                "public_platforms": research.get("public_platforms", []),
                                "research_notes": research.get("research_notes", []),
                            }
                            analyses = analyze_lead_profiles(lead_for_ai, ["4k", "digital"])
                            for profile_key, analysis in analyses.items():
                                for contact_type, contact_value, source_url in endpoints:
                                    save_proposal(int(saved["id"]), profile_key, contact_type,
                                                  contact_value, source_url, analysis, db_path)
                            combined = {
                                "score": max(a["score"] for a in analyses.values()),
                                "justificativa": "\n".join(a["justificativa"] for a in analyses.values()),
                                "mensagem": "\n\n".join(
                                    ("4K Food Service" if key == "4k" else "Presença digital") + ":\n" + value["mensagem"]
                                    for key, value in analyses.items()),
                            }
                            update_analysis(int(saved["id"]), combined, db_path)
                    except Exception as exc:
                        print(f"Mapeador automático — {saved.get('name','estabelecimento')}: {type(exc).__name__}: {exc}")
                    if processed >= 2:
                        break
        except Exception as exc:
            print(f"Mapeador automático — erro do ciclo: {type(exc).__name__}: {exc}")
        time.sleep(300)


def _open_browser() -> None:
    webbrowser.open("http://127.0.0.1:5000")


if __name__ == "__main__":
    init_db()
    threading.Thread(target=_background_research_loop, daemon=True, name="mapeador-public-research").start()
    if os.getenv("RENDER") != "true":
        threading.Timer(1.0, _open_browser).start()
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=False)
