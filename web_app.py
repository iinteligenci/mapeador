"""Interface web local do Mapeador; não expõe o serviço na rede pública."""
from __future__ import annotations

import asyncio
import os
import threading
import webbrowser
from datetime import datetime
from typing import Any

from dotenv import load_dotenv
from flask import Flask, redirect, render_template_string, request, url_for

from ai_agent.analyzer import analyze_lead_profiles
from database.db import get_leads, init_db, save_lead, update_analysis, update_lead_status
from scraper.maps_scraper import search_google_maps
from scraper.site_research import research_public_site

load_dotenv()
app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 1 * 1024 * 1024

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
 <nav class="nav"><a href="/">＋ Nova prospecção</a><a href="/history">▤ Restaurantes já pesquisados</a></nav>
</header>
<section class="panel">
 <h2>Nova prospecção</h2>
 <form id="searchForm" method="post" action="/search">
  <div class="formgrid">
   <div><label for="term">Tipo de negócio e localidade</label><input id="term" name="term" value="{{ term }}" required placeholder="Ex.: bares em Vila Velha ES"></div>
   <div><label for="limit">Quantidade máxima</label><select id="limit" name="limit">{% for n in [3,5,10,15] %}<option value="{{n}}" {% if limit == n %}selected{% endif %}>{{n}} negócios</option>{% endfor %}</select></div>
   <div><label for="profile">Qual empresa vai prospectar?</label><select id="profile" name="profile">
    <option value="4k" {% if profile == '4k' %}selected{% endif %}>4K Food Service</option>
    <option value="digital" {% if profile == 'digital' %}selected{% endif %}>Presença digital</option>
    <option value="both" {% if profile == 'both' %}selected{% endif %}>Ambas as empresas</option>
   </select></div>
   <div style="grid-column:1/-1"><label for="offer">Personalizar a proposta (opcional)</label><input id="offer" name="offer" value="{{ offer }}" placeholder="Ex.: fornecimento de bacon, linguiça e carnes defumadas"></div>
  </div>
  <button id="submitButton" type="submit">⌕ Iniciar prospecção</button>
  <div class="note">O Mapeador pula empresas já cadastradas. Na opção “Ambas”, a IA faz uma única chamada para avaliar os dois perfis. Mensagens são apenas rascunhos.</div>
 </form>
</section>
{% if error %}<div class="alert">{{ error }}</div>{% endif %}
{% if results is not none %}
<section class="panel">
 <h2>Resultado desta pesquisa</h2>
 <div class="stats">
  <div class="stat"><strong>{{ results|length }}</strong><span>Estabelecimentos encontrados</span></div>
  <div class="stat"><strong>{{ analyzed }}</strong><span>Análises de IA concluídas</span></div>
  <div class="stat"><strong>{{ failed }}</strong><span>Análises pendentes ou com erro</span></div>
  <div class="stat"><strong>{{ skipped }}</strong><span>Já pesquisados — ignorados</span></div>
 </div>
 {% if results|length == 0 %}<p class="empty">{% if skipped %}Todos os estabelecimentos encontrados já estavam cadastrados. Não repetimos a análise. Confira a aba “Restaurantes já pesquisados”.{% else %}Nenhum estabelecimento novo retornado. Tente outro termo ou localidade.{% endif %}</p>{% else %}
 <div class="results" style="margin-top:16px">
 {% for item in results %}
  {% set lead = item.lead %}{% set research = item.research %}{% set analysis = item.analysis %}
  <article class="lead">
   <div class="leadhead"><div><h3>{{ lead.name }}</h3><div class="category">{{ lead.category or "Categoria não identificada" }}</div></div>
   {% if analysis and analysis.score is defined %}<div class="score">{{ analysis.score }}/100 prioridade</div>{% else %}<div class="score unknown">IA pendente</div>{% endif %}</div>
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
    <div class="draft"><b>Rascunho de abordagem — não enviado</b>
{{ analysis.mensagem }}</div></div>
   {% endfor %}
   {% else %}
   <div class="alert" style="margin-top:14px">{{ item.error or "Análise de IA não concluída. Os dados públicos coletados continuam disponíveis." }}</div>
   {% endif %}
   <form class="statusform" method="post" action="/status">
    <input type="hidden" name="lead_id" value="{{ item.lead_id }}">
    <label for="status-{{ item.lead_id }}" style="margin:0">Etapa comercial</label>
    <select id="status-{{ item.lead_id }}" name="status">
      <option value="to_visit" selected>Para visitar</option>
      <option value="visited">Visitado</option>
      <option value="client">Cliente</option>
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
        offer="", profile="both", results=None, analyzed=0, failed=0, skipped=0, error=None
    )


@app.post("/search")
def search():
    term = (request.form.get("term") or "").strip()
    offer = (request.form.get("offer") or "").strip()
    profile = (request.form.get("profile") or "both").strip()
    if profile not in {"4k", "digital", "both"}:
        profile = "both"
    selected_profiles = ["4k", "digital"] if profile == "both" else [profile]
    try:
        limit = max(1, min(15, int(request.form.get("limit", "3"))))
    except ValueError:
        limit = 3
    if not term:
        return render_template_string(
            PAGE, term=term, limit=limit, offer=offer, profile=profile, results=None,
            analyzed=0, failed=0, skipped=0, error="Informe o que pesquisar e a localidade."
        ), 400

    db_path = os.getenv("DATABASE_PATH", "data/mapeador.sqlite3")
    init_db(db_path)
    try:
        leads = asyncio.run(search_google_maps(term, limit))
    except Exception as exc:
        return render_template_string(
            PAGE, term=term, limit=limit, offer=offer, profile=profile, results=[],
            analyzed=0, failed=0, skipped=0, error=f"Falha na pesquisa do Maps: {type(exc).__name__}: {exc}"
        ), 500

    results: list[dict[str, Any]] = []
    analyzed = 0
    skipped = 0
    saved_by_link = {item.get("link"): item for item in get_leads(path=db_path)}
    for lead in leads:
        try:
            lead_id, inserted = save_lead(lead, db_path)
        except Exception:
            lead_id, inserted = None, True

        # Skip completed leads; allow retry when the previous AI call failed.
        existing = saved_by_link.get(lead.get("link"))
        if not inserted and existing and existing.get("score") is not None:
            skipped += 1
            continue

        try:
            research = research_public_site(lead)
        except Exception as exc:
            research = {
                "address": lead.get("address", ""), "instagram": "", "channels": [],
                "menu_url": lead.get("menu_url", ""), "menu_items": [],
                "public_platforms": [], "research_notes": [
                    f"Pesquisa complementar falhou ({type(exc).__name__})."
                ], "sources": []
            }
        analysis_lead = {
            **lead,
            "address": research.get("address") or lead.get("address", ""),
            "instagram": research.get("instagram", ""),
            "channels": research.get("channels", []),
            "menu_url": research.get("menu_url") or lead.get("menu_url", ""),
            "menu_items": research.get("menu_items", []),
            "public_platforms": research.get("public_platforms", []),
            "research_notes": research.get("research_notes", []),
        }
        analyses = None
        error = None
        try:
            analyses = analyze_lead_profiles(analysis_lead, selected_profiles, offer)
            analyzed += 1
            if lead_id is not None:
                combined = {
                    "score": max(item["score"] for item in analyses.values()),
                    "justificativa": "\n".join(
                        f"{'4K Food Service' if key == '4k' else 'Presença digital'}: {item['justificativa']}"
                        for key, item in analyses.items()
                    ),
                    "mensagem": "\n\n".join(
                        f"{'4K Food Service' if key == '4k' else 'Presença digital'} — rascunho não enviado:\n{item['mensagem']}"
                        for key, item in analyses.items()
                    ),
                }
                update_analysis(lead_id, combined, db_path)
        except Exception as exc:
            error = f"IA não concluiu ({type(exc).__name__}). Os dados coletados foram mantidos."
        results.append({"lead": lead, "lead_id": lead_id, "research": research, "analyses": analyses, "error": error})

    return render_template_string(
        PAGE, term=term, limit=limit, offer=offer, profile=profile, results=results,
        analyzed=analyzed, failed=len(results) - analyzed, skipped=skipped, error=None
    )



STATUS_LABELS = {
    "to_visit": "Para visitar",
    "visited": "Visitado",
    "client": "Cliente",
}


@app.get("/history")
def history():
    db_path = os.getenv("DATABASE_PATH", "data/mapeador.sqlite3")
    init_db(db_path)
    selected = (request.args.get("status") or "all").strip()
    if selected not in {"all", *STATUS_LABELS.keys()}:
        selected = "all"
    leads = get_leads(path=db_path)
    for lead in leads:
        if lead.get("status") not in STATUS_LABELS:
            lead["status"] = "to_visit"
        lead["status_label"] = STATUS_LABELS[lead["status"]]
    if selected != "all":
        leads = [lead for lead in leads if lead["status"] == selected]
    return render_template_string(HISTORY_PAGE, leads=leads, selected=selected, labels=STATUS_LABELS)


@app.post("/status")
def set_status():
    db_path = os.getenv("DATABASE_PATH", "data/mapeador.sqlite3")
    try:
        lead_id = int(request.form.get("lead_id", ""))
        status = request.form.get("status", "")
        update_lead_status(lead_id, status, db_path)
    except (ValueError, TypeError) as exc:
        return f"Não foi possível atualizar a etapa: {exc}", 400
    return redirect(url_for("history"))


HISTORY_PAGE = r"""
<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Mapeador | Restaurantes já pesquisados</title>
<style>
:root{color-scheme:dark;--line:#26354d;--muted:#a6b4ca;--text:#edf4ff;--blue:#4da3ff}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(ellipse at top left,#162b49 0,#0b1220 48%);font:15px/1.5 Inter,Segoe UI,Arial,sans-serif;color:var(--text)}
main{max-width:1180px;margin:auto;padding:34px 22px 64px}.brand{display:flex;gap:12px;align-items:center}.mark{width:46px;height:46px;border-radius:14px;background:linear-gradient(135deg,#58b7ff,#5b6cff);display:grid;place-items:center;font-size:24px;font-weight:800}h1{font-size:27px;margin:0}.sub,.muted{color:var(--muted)}.panel{background:#121d30;border:1px solid var(--line);border-radius:16px;padding:20px;margin:18px 0}.nav{display:flex;gap:10px;flex-wrap:wrap;margin:18px 0}.nav a{color:#b9dcff;text-decoration:none;border:1px solid #354761;background:#122039;padding:9px 13px;border-radius:10px}.filters{display:flex;gap:8px;flex-wrap:wrap;margin:12px 0 20px}.filters a{padding:8px 12px;border:1px solid var(--line);border-radius:9px;text-decoration:none;color:var(--text)}.filters a.active{background:#1c4772;border-color:#4da3ff}.entry{background:#0d1829;border:1px solid var(--line);border-radius:13px;padding:16px;margin:12px 0}.top{display:flex;justify-content:space-between;gap:12px;align-items:start}.entry h3{margin:0}.pill{border-radius:99px;padding:4px 10px;background:#18344f;color:#b9dcff;font-size:12px}.meta{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;margin:12px 0}.meta div{overflow-wrap:anywhere}.meta b{display:block;font-size:12px;color:var(--muted);font-weight:500}a{color:#83c5ff}select,button{border:1px solid #354761;background:#0c1627;color:var(--text);padding:10px;border-radius:9px;font:inherit}.statusform{display:flex;gap:8px;flex-wrap:wrap;align-items:center;border-top:1px solid var(--line);padding-top:12px}.statusform button{background:var(--blue);color:#071321;font-weight:700;cursor:pointer}.empty{color:var(--muted);padding:22px 0}.hint{font-size:12px;color:var(--muted)}@media(max-width:650px){main{padding:20px 13px}.meta{grid-template-columns:1fr}.top{flex-direction:column}}
</style></head><body><main>
<header><div class="brand"><div class="mark">M</div><div><h1>Restaurantes já pesquisados</h1><div class="muted">Seu histórico comercial fica salvo no banco local.</div></div></div>
<nav class="nav"><a href="/">＋ Nova prospecção</a><a href="/history">▤ Restaurantes já pesquisados</a></nav></header>
<section class="panel"><h2>{{ leads|length }} estabelecimento(s) nesta lista</h2>
<div class="filters">
<a href="/history" class="{{ 'active' if selected == 'all' else '' }}">Todos</a>
<a href="/history?status=to_visit" class="{{ 'active' if selected == 'to_visit' else '' }}">Para visitar</a>
<a href="/history?status=visited" class="{{ 'active' if selected == 'visited' else '' }}">Visitados</a>
<a href="/history?status=client" class="{{ 'active' if selected == 'client' else '' }}">Clientes</a>
</div>
{% if not leads %}<div class="empty">Nenhum restaurante nesta categoria ainda. Faça uma prospecção para adicionar empresas ao histórico.</div>{% endif %}
{% for lead in leads %}<article class="entry">
<div class="top"><div><h3>{{ lead.name }}</h3><div class="muted">{{ lead.category or "Categoria não identificada" }}</div></div><span class="pill">{{ lead.status_label }}</span></div>
<div class="meta">
<div><b>Telefone</b>{{ lead.phone or "Não identificado publicamente" }}</div>
<div><b>Site</b>{% if lead.website %}<a href="{{lead.website}}" target="_blank" rel="noopener">{{lead.website}}</a>{% else %}Não identificado publicamente{% endif %}</div>
<div><b>Prioridade preliminar</b>{{ (lead.score|string + "/100") if lead.score is not none else "Ainda não avaliada" }}</div>
<div><b>Última atualização</b>{{ lead.updated_at }}</div>
<div><b>Análise</b>{{ lead.justification or "Análise não registrada" }}</div>
</div>
{% if lead.message %}<details><summary>Ver rascunho de abordagem (não enviado)</summary><p style="white-space:pre-wrap">{{ lead.message }}</p></details>{% endif %}
{% if lead.link %}<p><a href="{{lead.link}}" target="_blank" rel="noopener">Abrir no Google Maps ↗</a></p>{% endif %}
<form class="statusform" method="post" action="/status"><input type="hidden" name="lead_id" value="{{lead.id}}">
<label for="history-status-{{lead.id}}" class="muted">Alterar etapa:</label>
<select id="history-status-{{lead.id}}" name="status">{% for value,label in labels.items() %}<option value="{{value}}" {% if lead.status == value %}selected{% endif %}>{{label}}</option>{% endfor %}</select>
<button type="submit">Salvar</button></form>
</article>{% endfor %}
<p class="hint">Uma empresa já cadastrada será ignorada nas próximas análises para reduzir repetição e chamadas à IA. O histórico fica neste computador, no banco SQLite local.</p>
</section></main></body></html>
"""


def _open_browser() -> None:
    webbrowser.open("http://127.0.0.1:5000")


if __name__ == "__main__":
    threading.Timer(1.0, _open_browser).start()
    app.run(host="127.0.0.1", port=int(os.getenv("PORT", "5000")), debug=False)
