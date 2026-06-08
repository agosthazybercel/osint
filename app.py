from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Form, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel

from deepsearch_core.config import settings
from deepsearch_core.db import load_search, popular_searches, recent_searches, record_search
from deepsearch_core.engine import LawfulUseRequired, deep_search
from deepsearch_core.exports import export_csv
from deepsearch_core.report import render_html_report, save_report
from deepsearch_core.utils import html_escape
from deepsearch_core.qa import answer_report_question
from deepsearch_core.monitoring import load_watchlist, add_watch, remove_watch
from deepsearch_core.models import DeepSearchReport, Evidence, UsernameProfile, MediaItem

app = FastAPI(title="OpenIntel OSINT Professional Suite", version="6.0.0-osint-pro")


class SearchRequest(BaseModel):
    query: str
    context: str = ""
    mode: str = "general"
    target_type: str = "unknown"
    max_results_per_query: int | None = None
    max_pages: int | None = None
    delay_seconds: float | None = None
    providers: list[str] | None = None
    ai: bool = True
    lawful_use_confirmed: bool = False
    scan_usernames: bool = True


BASE_STYLE = """
<style>
:root { --bg:#0b1020; --panel:#111827; --panel2:#151f32; --text:#eef2ff; --muted:#94a3b8; --line:#2a3654; --brand:#7c3aed; --brand2:#06b6d4; --good:#22c55e; --warn:#f59e0b; --bad:#ef4444; }
* { box-sizing:border-box; }
body { margin:0; font-family:Inter, Segoe UI, Arial, sans-serif; color:var(--text); background:radial-gradient(circle at top left,#1e1b4b 0,#0b1020 38%,#070b14 100%); line-height:1.55; }
a { color:#93c5fd; word-break:break-word; }
.wrap { width:min(1120px, calc(100% - 36px)); margin:0 auto; }
nav { position:sticky; top:0; z-index:10; backdrop-filter:blur(14px); background:rgba(7,11,20,.78); border-bottom:1px solid var(--line); }
.nav-inner { display:flex; justify-content:space-between; align-items:center; padding:14px 0; }
.nav-inner a { color:var(--text); text-decoration:none; margin-left:16px; opacity:.85; }
.logo { font-weight:900; }
.hero { padding:42px 0 16px; }
h1 { font-size:clamp(34px, 6vw, 66px); line-height:1; letter-spacing:-.05em; margin:0 0 12px; }
.lead { color:#cbd5e1; max-width:780px; font-size:18px; }
.card, form { background:rgba(17,24,39,.82); border:1px solid var(--line); border-radius:24px; padding:24px; margin:18px 0; box-shadow:0 18px 50px rgba(0,0,0,.25); }
label { display:block; font-weight:800; margin:10px 0 6px; }
.help { color:var(--muted); font-size:13px; margin-top:-2px; }
input, select, button { width:100%; padding:13px 14px; border-radius:14px; border:1px solid var(--line); background:#0f172a; color:var(--text); font-size:15px; }
input::placeholder { color:#64748b; }
button { cursor:pointer; font-weight:900; background:linear-gradient(90deg,var(--brand),var(--brand2)); border:0; margin-top:16px; color:white; }
.row { display:grid; grid-template-columns:repeat(auto-fit,minmax(210px,1fr)); gap:14px; }
.checks label { font-weight:600; display:flex; gap:9px; align-items:flex-start; color:#dbeafe; }
.checks input { width:auto; margin-top:4px; }
.grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(250px,1fr)); gap:14px; }
.feature { background:rgba(255,255,255,.04); border:1px solid var(--line); border-radius:18px; padding:16px; }
table { width:100%; border-collapse:collapse; } th,td { padding:10px; border-bottom:1px solid var(--line); text-align:left; vertical-align:top; }
pre { white-space:pre-wrap; overflow:auto; border-radius:16px; padding:16px; background:#020617; color:#e2e8f0; border:1px solid var(--line); }
code { background:rgba(255,255,255,.08); padding:2px 6px; border-radius:7px; }
.saved { position:sticky; top:52px; z-index:8; }
</style>
"""


def shell(title: str, body: str) -> HTMLResponse:
    return HTMLResponse(
        f"""<!doctype html><html lang='hu'><head><meta charset='utf-8'/><meta name='viewport' content='width=device-width, initial-scale=1'/><title>{html_escape(title)}</title>{BASE_STYLE}</head>
<body><nav><div class='wrap nav-inner'><div class='logo'>OpenIntel OSINT</div><div><a href='/'>Search</a><a href='/history'>History</a><a href='/trending'>Trending</a><a href='/watchlist'>Watchlist</a><a href='/docs'>API</a></div></div></nav><main class='wrap'>{body}</main></body></html>"""
    )


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return shell(
        "DeepSearch Signal Intelligence Pro",
        """
<section class="hero">
  <h1>OpenIntel Professional OSINT</h1>
  <p class="lead">Lokális, publikus-webes OSINT dashboard social media intelligence modullal, identity resolutionnel, bizonyítéksúlyozással, timeline-nal, network graphel és AI riporttal.</p>
</section>
<form method="post" action="/search">
    <label>Primary query</label>
    <input name="query" placeholder='pl. "Agostházy Bercel" vagy agosthazyb vagy email/domain' required />
    <div class="help">Személynél a legjobb forma: pontos név idézőjelben. Példa: <code>"Agostházy Bercel"</code></div>

    <label>Disambiguation context</label>
    <input name="context" placeholder="város, iskola, cég, username, domain — pl. Budapesti Piarista Gimnázium" />
    <div class="help">Ez javítja a találatokat, mert külön kezeli a nevet és a kontextust. Ne mindent egy mezőbe írj.</div>

    <div class="row">
        <div><label>Mode</label><select name="mode">
            <option value="general">auto/general</option><option value="person">person</option><option value="email">email</option><option value="phone">phone</option><option value="username">username</option><option value="company">company</option><option value="domain">domain/url</option>
        </select></div>
        <div><label>Target type</label><select name="target_type">
            <option value="unknown">unknown</option><option value="self">self</option><option value="consented_person">consented person</option><option value="public_person">public person</option><option value="company">company</option><option value="journalism_or_research">journalism/research</option>
        </select></div>
        <div><label>Max pages</label><input type="number" name="max_pages" value="40" min="1" max="180" /></div>
        <div><label>Results/query</label><input type="number" name="max_results_per_query" value="8" min="1" max="30" /></div>
    </div>
    <div class="checks">
      <label><input type="checkbox" name="ai" checked /> OpenAI Deep Report — alapértelmezett modell: gpt-5-nano</label>
      <label><input type="checkbox" name="scan_usernames" checked /> Direct username scan, ha username mód vagy username-szerű query</label>
      <label><input type="checkbox" name="lawful_use_confirmed" required /> Megerősítem, hogy csak jogszerű, arányos, publikus információkutatásra használom.</label>
    </div>
    <button type="submit">Start professional OSINT scan</button>
</form>
<section class="grid">
  <div class="feature"><h3>Strict identity filter</h3><p>Nem elég egy gyenge névegyezés: erős név-, username-, email- vagy telefonjel kell.</p></div>
  <div class="feature"><h3>Context-aware ranking</h3><p>Külön kontextusmezővel csökkenti az azonos nevű emberek összekeverését.</p></div>
  <div class="feature"><h3>Clean visual UI</h3><p>Best matches, kurált findingok, olvasható grafikonok és kompakt hálótérkép.</p></div>
  <div class="feature"><h3>Noise suppression</h3><p>Kiszűri az ikonokat, app-badge-eket, tracking képeket, listing oldalakat és irreleváns entitásokat.</p></div>
</section>
""",
    )


@app.post("/search", response_class=HTMLResponse)
def search_form(
    query: str = Form(...),
    context: str = Form(""),
    mode: str = Form("general"),
    target_type: str = Form("unknown"),
    max_pages: int = Form(40),
    max_results_per_query: int = Form(8),
    ai: str | None = Form(None),
    scan_usernames: str | None = Form(None),
    lawful_use_confirmed: str | None = Form(None),
):
    try:
        report = deep_search(
            query=query,
            context=context,
            mode=mode,  # type: ignore
            target_type=target_type,  # type: ignore
            max_results_per_query=max_results_per_query,
            max_pages=max_pages,
            ai=ai is not None,
            lawful_use_confirmed=lawful_use_confirmed is not None,
            scan_usernames=scan_usernames is not None,
        )
    except LawfulUseRequired as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    json_path, html_path, md_path = save_report(report)
    csv_path = export_csv(report)
    search_id = record_search(report, json_path=json_path, html_path=html_path)
    html = render_html_report(report)
    links = f"""
    <section class='panel saved'><b>Saved files:</b>
    <a class='btn ghost' href='/download?path={html_escape(html_path)}'>HTML</a>
    <a class='btn ghost' href='/download?path={html_escape(json_path)}'>JSON</a>
    <a class='btn ghost' href='/download?path={html_escape(md_path)}'>Markdown</a>
    <a class='btn ghost' href='/download?path={html_escape(csv_path)}'>CSV</a>
    <span class='muted'>History ID: {search_id}</span></section>
    """
    return HTMLResponse(html.replace("<main class='main'>", "<main class='main'>" + links, 1))


@app.post("/api/search")
def api_search(req: SearchRequest):
    try:
        report = deep_search(
            query=req.query,
            context=req.context,
            mode=req.mode,  # type: ignore
            target_type=req.target_type,  # type: ignore
            max_results_per_query=req.max_results_per_query,
            max_pages=req.max_pages,
            delay_seconds=req.delay_seconds,
            providers=req.providers,
            ai=req.ai,
            lawful_use_confirmed=req.lawful_use_confirmed,
            scan_usernames=req.scan_usernames,
        )
    except LawfulUseRequired as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    json_path, html_path, _ = save_report(report)
    record_search(report, json_path=json_path, html_path=html_path)
    return JSONResponse(report.to_dict())


@app.get("/history", response_class=HTMLResponse)
def history() -> HTMLResponse:
    rows = "".join(
        f"<tr><td>{r['id']}</td><td>{html_escape(r['created_at'])}</td><td>{html_escape(r['query'])}</td><td>{html_escape(r['mode'])}</td><td>{r['evidence_count']}</td><td>{html_escape(r['confidence_overall'])}</td><td><a href='/history/{r['id']}'>open</a></td></tr>"
        for r in recent_searches(100)
    )
    return shell("History", f"<h1>History</h1><div class='card'><table><tr><th>ID</th><th>Created</th><th>Query</th><th>Mode</th><th>Evidence</th><th>Confidence</th><th></th></tr>{rows or '<tr><td colspan=7>—</td></tr>'}</table></div>")


@app.get("/history/{search_id}", response_class=HTMLResponse)
def history_item(search_id: int) -> HTMLResponse:
    row = load_search(search_id)
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    report_json = row.get("report_json") or "{}"
    import json
    data = json.loads(report_json)
    return shell("Search history item", f"<h1>{html_escape(row['query'])}</h1><pre>{html_escape(json.dumps(data, ensure_ascii=False, indent=2))}</pre>")


@app.get("/trending", response_class=HTMLResponse)
def trending() -> HTMLResponse:
    rows = "".join(f"<tr><td>{html_escape(r['query'])}</td><td>{html_escape(r['mode'])}</td><td>{r['count']}</td><td>{html_escape(r['last_seen'])}</td></tr>" for r in popular_searches(50))
    return shell("Trending", f"<h1>Trending / popular local searches</h1><div class='card'><table><tr><th>Query</th><th>Mode</th><th>Count</th><th>Last seen</th></tr>{rows or '<tr><td colspan=4>—</td></tr>'}</table></div>")


@app.get("/download")
def download(path: str):
    p = Path(path).resolve()
    root = settings.root_dir.resolve()
    if not str(p).startswith(str(root)) or not p.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(str(p), filename=p.name)


@app.get("/health")
def health():
    return {"ok": True, "version": "4.0.0-signal-ui"}



def _report_from_dict(data: dict) -> DeepSearchReport:
    evidence = []
    for ed in data.get("evidence", []):
        media = [MediaItem(**m) for m in ed.get("media", [])]
        ed = dict(ed); ed["media"] = media
        evidence.append(Evidence(**ed))
    profiles = [UsernameProfile(**p) for p in data.get("username_profiles", [])]
    return DeepSearchReport(
        query=data.get("query", ""),
        mode=data.get("mode", "general"),
        target_type=data.get("target_type", "unknown"),
        created_at=data.get("created_at", ""),
        search_queries=data.get("search_queries", []),
        summary=data.get("summary", ""),
        executive_summary=data.get("executive_summary", ""),
        confidence_overall=data.get("confidence_overall", "none"),
        findings=data.get("findings", {}),
        evidence=evidence,
        username_profiles=profiles,
        warnings=data.get("warnings", []),
        provider_errors=data.get("provider_errors", []),
        stats=data.get("stats", {}),
    )


@app.get("/watchlist", response_class=HTMLResponse)
def watchlist() -> HTMLResponse:
    items = load_watchlist()
    rows = "".join(
        f"<tr><td>{i}</td><td>{html_escape(x.get('query',''))}</td><td>{html_escape(x.get('context',''))}</td><td>{html_escape(x.get('mode',''))}</td><td>{html_escape(x.get('created_at',''))}</td><td><a href='/watchlist/remove/{i}'>remove</a></td></tr>"
        for i, x in enumerate(items)
    )
    form = """
    <form method='post' action='/watchlist/add'>
      <label>Query to monitor</label><input name='query' required>
      <label>Context</label><input name='context'>
      <label>Mode</label><select name='mode'><option>general</option><option>person</option><option>username</option><option>company</option><option>domain</option></select>
      <button>Add to watchlist</button>
    </form>
    """
    return shell("Watchlist", f"<h1>Monitoring watchlist</h1>{form}<div class='card'><table><tr><th>#</th><th>Query</th><th>Context</th><th>Mode</th><th>Created</th><th></th></tr>{rows or '<tr><td colspan=6>—</td></tr>'}</table></div>")


@app.post("/watchlist/add")
def watchlist_add(query: str = Form(...), context: str = Form(""), mode: str = Form("general")):
    add_watch(query, context, mode)
    return HTMLResponse("<script>location.href='/watchlist'</script>")


@app.get("/watchlist/remove/{index}")
def watchlist_remove(index: int):
    remove_watch(index)
    return HTMLResponse("<script>location.href='/watchlist'</script>")


@app.post("/api/history/{search_id}/ask")
def ask_history(search_id: int, question: str = Form(...)):
    row = load_search(search_id)
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    import json
    report = _report_from_dict(json.loads(row.get("report_json") or "{}"))
    return {"answer": answer_report_question(report, question)}
