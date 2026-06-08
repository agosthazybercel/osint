from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from .config import settings
from .models import DeepSearchReport, Evidence
from .utils import html_escape, safe_filename, stable_id


def save_report(report: DeepSearchReport, out_dir: Path | None = None) -> tuple[str, str, str]:
    out_dir = out_dir or settings.reports_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    file_id = stable_id(report.query + report.created_at)
    base = f"{safe_filename(report.query)}_{file_id}"
    json_path = out_dir / f"{base}.json"
    html_path = out_dir / f"{base}.html"
    md_path = out_dir / f"{base}.md"
    json_path.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    html_path.write_text(render_html_report(report), encoding="utf-8")
    md_path.write_text(render_markdown_report(report), encoding="utf-8")
    return str(json_path), str(html_path), str(md_path)


def render_markdown_report(report: DeepSearchReport) -> str:
    data = report.to_dict()
    lines = [
        f"# OSINT Professional Report: {report.query}",
        "",
        f"- Created: {report.created_at}",
        f"- Mode: {report.mode}",
        f"- Target type: {report.target_type}",
        f"- Overall confidence: {report.confidence_overall}",
        "",
        "## Executive summary",
        report.executive_summary or "—",
        "",
        "## AI Deep Report",
        report.summary or "—",
        "",
        "## Social Intelligence",
        "```json",
        json.dumps(data.get("findings", {}).get("social_intelligence", {}), ensure_ascii=False, indent=2),
        "```",
        "",
        "## Curated findings",
        "```json",
        json.dumps(data.get("findings", {}), ensure_ascii=False, indent=2),
        "```",
        "",
        "## Evidence",
    ]
    for ev in report.evidence:
        lines += [
            f"### [{ev.id}] {ev.title}",
            f"- URL: {ev.url}",
            f"- Source: {ev.source}",
            f"- Confidence: {ev.confidence}",
            f"- Score: {ev.relevance_score}",
            f"- Signals: {', '.join(ev.matched_terms)}",
            "",
            ev.snippet or ev.extracted_text[:700],
            "",
        ]
    return "\n".join(lines)


def _link(value: str, label: str | None = None, cls: str = "") -> str:
    if not value:
        return "<span class='muted'>—</span>"
    c = f" class='{cls}'" if cls else ""
    return f"<a{c} href='{html_escape(value)}' target='_blank' rel='noreferrer'>{html_escape(label or value)}</a>"


def _conf_class(conf: str) -> str:
    return {"high": "good", "medium": "medium", "low": "weak", "very_low": "bad", "none": "bad"}.get(conf, "weak")


def _pill(text: str, cls: str = "") -> str:
    return f"<span class='pill {cls}'>{html_escape(text)}</span>"


def _bar(label: str, value: int | float, maximum: int | float, cls: str = "") -> str:
    maximum = maximum or 1
    pct = max(3, min(100, int((float(value) / float(maximum)) * 100)))
    return f"<div class='bar-row'><span>{html_escape(str(label))}</span><div class='bar'><i class='{cls}' style='width:{pct}%'></i></div><b>{html_escape(str(value))}</b></div>"


def _list(items, limit: int = 10, empty: str = "—") -> str:
    if not items:
        return f"<span class='muted'>{html_escape(empty)}</span>"
    if isinstance(items, dict):
        rows = []
        for k, v in list(items.items())[:limit]:
            rows.append(f"<li><b>{html_escape(str(k))}</b>: {_list(v, 6)}</li>")
        return "<ul class='clean'>" + "".join(rows) + "</ul>"
    if isinstance(items, (str, int, float, bool)):
        val = str(items)
        return _link(val) if val.startswith("http") else html_escape(val)
    rows = []
    for item in list(items)[:limit]:
        if isinstance(item, str) and item.startswith("http"):
            rows.append(f"<li>{_link(item)}</li>")
        else:
            rows.append(f"<li>{html_escape(str(item))}</li>")
    if len(items) > limit:
        rows.append(f"<li class='muted'>+{len(items)-limit} more in JSON export</li>")
    return "<ul class='clean'>" + "".join(rows) + "</ul>"


def _metric(label: str, value, hint: str = "", cls: str = "") -> str:
    return f"<div class='metric {cls}'><span>{html_escape(label)}</span><strong>{html_escape(str(value))}</strong><small>{html_escape(hint)}</small></div>"


def _tabs_js() -> str:
    return """
<script>
function showTab(id){
  document.querySelectorAll('.tab-panel').forEach(p=>p.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(b=>b.classList.remove('active'));
  document.getElementById(id).classList.add('active');
  document.querySelector('[data-tab="'+id+'"]').classList.add('active');
}
function filterEvidence(){
  const q=(document.getElementById('evSearch')?.value||'').toLowerCase();
  const c=(document.getElementById('evConf')?.value||'all');
  document.querySelectorAll('#evidenceTable tbody tr').forEach(row=>{
    const text=row.innerText.toLowerCase(); const conf=row.getAttribute('data-conf');
    row.style.display=((c==='all'||conf===c)&&(!q||text.includes(q)))?'':'none';
  });
}
function copySummary(){
  navigator.clipboard.writeText(document.getElementById('execSummary').innerText);
}
</script>
"""


def _style() -> str:
    return """
<style>
:root{--bg:#060812;--panel:#0f172a;--panel2:#111c31;--panel3:#162238;--line:#25324a;--text:#eaf1ff;--muted:#8ea0bc;--brand:#7c3aed;--brand2:#06b6d4;--good:#22c55e;--medium:#f59e0b;--weak:#64748b;--bad:#ef4444;--pink:#ec4899;--violet:#8b5cf6;--cyan:#22d3ee}
*{box-sizing:border-box} html{scroll-behavior:smooth} body{margin:0;background:radial-gradient(circle at top left,#192252 0,#060812 40%,#03050b 100%);font-family:Inter,Segoe UI,Arial,sans-serif;color:var(--text);line-height:1.55} a{color:#9bd7ff;text-decoration:none} a:hover{text-decoration:underline}.layout{display:grid;grid-template-columns:268px minmax(0,1fr);min-height:100vh}.sidebar{position:sticky;top:0;height:100vh;padding:24px;background:rgba(7,12,24,.82);backdrop-filter:blur(18px);border-right:1px solid var(--line);overflow:auto}.brand{display:flex;align-items:center;gap:12px;font-weight:950;font-size:18px;margin-bottom:24px}.brand-mark{width:36px;height:36px;border-radius:13px;background:linear-gradient(135deg,var(--brand),var(--brand2));box-shadow:0 0 35px rgba(124,58,237,.35)}.nav-group{margin:18px 0}.nav-label{font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.12em;margin:12px 0}.tab-btn{display:flex;width:100%;align-items:center;gap:10px;border:1px solid transparent;background:transparent;color:#cbd5e1;border-radius:14px;padding:11px 12px;font-weight:800;text-align:left;cursor:pointer}.tab-btn:hover,.tab-btn.active{background:linear-gradient(90deg,rgba(124,58,237,.22),rgba(6,182,212,.08));border-color:#314268;color:white}.main{padding:28px;max-width:1480px;width:100%;margin:0 auto}.topbar{display:flex;justify-content:space-between;gap:18px;align-items:flex-start;margin-bottom:18px}.eyebrow{color:#67e8f9;font-size:12px;text-transform:uppercase;letter-spacing:.18em;font-weight:900}h1{font-size:clamp(30px,4.5vw,54px);line-height:1.02;margin:6px 0 10px;letter-spacing:-.04em}h2{font-size:25px;margin:0 0 6px}h3{margin:0 0 8px}.subtitle{color:#b8c5d9;max-width:900px}.actions{display:flex;gap:10px;flex-wrap:wrap}.btn{display:inline-flex;align-items:center;justify-content:center;gap:8px;padding:10px 13px;border-radius:13px;border:1px solid var(--line);background:#111c31;color:#eaf1ff;font-weight:900}.btn.primary{background:linear-gradient(90deg,var(--brand),var(--brand2));border:none}.btn.ghost{background:rgba(255,255,255,.04)}.panel{background:rgba(15,23,42,.82);border:1px solid var(--line);box-shadow:0 18px 60px rgba(0,0,0,.28);border-radius:24px;padding:20px;margin:16px 0}.panel-title{display:flex;justify-content:space-between;gap:16px;align-items:flex-start;margin-bottom:16px}.muted{color:var(--muted)}.metrics{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}.metric{background:linear-gradient(180deg,rgba(255,255,255,.06),rgba(255,255,255,.025));border:1px solid var(--line);border-radius:18px;padding:16px;min-height:108px}.metric span{display:block;color:#a8b5cd;font-size:13px}.metric strong{display:block;font-size:32px;letter-spacing:-.03em;margin:5px 0}.metric small{color:var(--muted)}.metric.good{border-color:rgba(34,197,94,.35)}.metric.warn{border-color:rgba(245,158,11,.38)}.grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}.grid.two{grid-template-columns:repeat(2,minmax(0,1fr))}.card{background:rgba(255,255,255,.035);border:1px solid var(--line);border-radius:18px;padding:16px}.executive{font-size:16px;color:#dbeafe;background:linear-gradient(135deg,rgba(124,58,237,.18),rgba(34,211,238,.08));border:1px solid #384568;border-radius:22px;padding:18px}.pill{display:inline-flex;align-items:center;padding:6px 9px;border-radius:999px;background:#1e293b;border:1px solid #334155;color:#dbeafe;font-size:12px;font-weight:850;margin:3px}.pill.good,.badge.good{background:rgba(34,197,94,.14);border-color:rgba(34,197,94,.38);color:#86efac}.pill.medium,.badge.medium{background:rgba(245,158,11,.14);border-color:rgba(245,158,11,.38);color:#fde68a}.pill.weak,.badge.weak{background:rgba(100,116,139,.14);border-color:rgba(100,116,139,.38);color:#cbd5e1}.pill.bad,.badge.bad{background:rgba(239,68,68,.13);border-color:rgba(239,68,68,.38);color:#fecaca}.badge{display:inline-flex;border-radius:999px;padding:5px 9px;border:1px solid #334155;font-size:12px;font-weight:950;text-transform:uppercase}.score{font-size:22px;font-weight:950}.clean{margin:8px 0 0 18px;padding:0}.clean li{margin:5px 0}.bar-row{display:grid;grid-template-columns:120px 1fr 38px;gap:10px;align-items:center;margin:10px 0;color:#cbd5e1}.bar{height:11px;background:#1e293b;border-radius:999px;overflow:hidden}.bar i{display:block;height:100%;background:linear-gradient(90deg,var(--brand),var(--brand2));border-radius:999px}.bar i.good{background:var(--good)}.bar i.medium{background:var(--medium)}.bar i.bad{background:var(--bad)}.social-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}.social-card{position:relative;overflow:hidden;background:linear-gradient(180deg,rgba(255,255,255,.065),rgba(255,255,255,.025));border:1px solid var(--line);border-radius:20px;padding:16px}.social-card:before{content:"";position:absolute;inset:0 0 auto 0;height:3px;background:linear-gradient(90deg,var(--brand),var(--cyan))}.social-head{display:flex;justify-content:space-between;gap:10px}.avatar{width:52px;height:52px;object-fit:cover;border-radius:16px;background:#0b1220;border:1px solid var(--line)}.profile-title{font-weight:950;font-size:16px}.bio{color:#cbd5e1;font-size:13px;max-height:66px;overflow:hidden}.topics{margin-top:8px}.table-wrap{overflow:auto;border:1px solid var(--line);border-radius:18px}table{width:100%;border-collapse:collapse;background:rgba(6,10,20,.22)}th,td{padding:12px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}th{position:sticky;top:0;background:#111c31;color:#cbd5e1;font-size:12px;text-transform:uppercase;letter-spacing:.08em}tr:hover td{background:rgba(255,255,255,.025)}input,select{width:100%;background:#0b1220;border:1px solid var(--line);color:var(--text);border-radius:13px;padding:11px 12px}.filters{display:grid;grid-template-columns:1fr 220px;gap:10px;margin-bottom:12px}.gallery{display:grid;grid-template-columns:repeat(auto-fill,minmax(130px,1fr));gap:10px}.gallery a{display:block;border-radius:15px;overflow:hidden;border:1px solid var(--line);background:#0b1220}.gallery img{width:100%;height:130px;object-fit:cover;display:block}.network{width:100%;height:360px;border-radius:18px;border:1px solid var(--line);background:radial-gradient(circle at center,rgba(124,58,237,.15),rgba(255,255,255,.025));overflow:hidden}.detail{background:rgba(255,255,255,.025);border:1px solid var(--line);border-radius:16px;margin:10px 0;padding:12px}.detail summary{cursor:pointer}.detail-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin:10px 0}pre{white-space:pre-wrap;overflow:auto;background:#020617;border:1px solid var(--line);border-radius:15px;padding:14px;color:#dbeafe;max-height:360px}.tab-panel{display:none}.tab-panel.active{display:block}.empty{padding:20px;border:1px dashed #334155;border-radius:18px;color:var(--muted);background:rgba(255,255,255,.02)}.small{font-size:12px}.kpi-strip{display:flex;gap:8px;flex-wrap:wrap}.warning{border-color:rgba(245,158,11,.35);background:rgba(245,158,11,.08)}@media(max-width:1100px){.layout{grid-template-columns:1fr}.sidebar{position:relative;height:auto}.metrics,.grid,.grid.two,.social-grid{grid-template-columns:1fr}.topbar{display:block}.filters{grid-template-columns:1fr}.detail-grid{grid-template-columns:1fr}.main{padding:16px}}
</style>
"""


def _social_section(report: DeepSearchReport) -> str:
    social = (report.findings or {}).get("social_intelligence") or {}
    profiles = social.get("profiles") or []
    summary = social.get("summary") or {}
    platform_counts = social.get("platform_counts") or {}
    conf_counts = social.get("confidence_counts") or {}
    topic_counts = social.get("topic_counts") or {}
    flags = social.get("visibility_flags") or {}
    max_platform = max(platform_counts.values()) if platform_counts else 1
    max_topic = max(topic_counts.values()) if topic_counts else 1

    cards = ""
    for p in profiles[:18]:
        img = p.get("image") or ""
        img_html = f"<img class='avatar' src='{html_escape(img)}' alt='' loading='lazy'/>" if img else "<div class='avatar'></div>"
        topics = "".join(_pill(t) for t in (p.get("topics") or [])[:5])
        reasons = "".join(_pill(r, "weak") for r in (p.get("reason") or [])[:5])
        cards += f"""
        <article class='social-card'>
          <div class='social-head'>
            <div><div class='profile-title'>{html_escape(p.get('platform','Unknown'))} · @{html_escape(p.get('username',''))}</div><div class='muted small'>{html_escape(p.get('status',''))} · HTTP {html_escape(str(p.get('http_status') or '—'))}</div></div>
            {img_html}
          </div>
          <p class='bio'>{html_escape(p.get('bio') or p.get('title') or 'No public bio metadata captured.')}</p>
          <div class='kpi-strip'><span class='badge {_conf_class(p.get('confidence','low'))}'>{html_escape(p.get('confidence','low'))}</span><span class='pill'>score {html_escape(str(p.get('score',0)))}</span></div>
          <div class='topics'>{topics or '<span class="muted small">No topic hints</span>'}</div>
          <div class='topics'>{reasons}</div>
          <p>{_link(p.get('url',''), 'Open profile', 'btn ghost')}</p>
        </article>
        """

    if not cards:
        cards = "<div class='empty'>No public social profiles accepted. Try username mode, add known username/context, or configure stronger search APIs.</div>"

    return f"""
    <section class='panel'>
      <div class='panel-title'><div><h2>Social media intelligence</h2><p class='muted'>Public profile metadata, platform distribution, topics, visibility flags and manual-verification hints.</p></div></div>
      <div class='metrics'>
        {_metric('Profiles', summary.get('total_profiles', 0), 'public profile URLs analyzed')}
        {_metric('High/medium', summary.get('high_or_medium', 0), 'usable social signals', 'good')}
        {_metric('Technical', summary.get('technical_profiles', 0), 'developer/platform profiles')}
        {_metric('Consumer social', summary.get('consumer_profiles', 0), 'IG/X/TikTok/etc.')}
      </div>
      <div class='grid two'>
        <div class='card'><h3>Platforms</h3>{''.join(_bar(k,v,max_platform) for k,v in platform_counts.items()) or '<span class="muted">—</span>'}</div>
        <div class='card'><h3>Confidence</h3>{''.join(_bar(k,v,max(conf_counts.values()) if conf_counts else 1, _conf_class(k)) for k,v in conf_counts.items()) or '<span class="muted">—</span>'}</div>
        <div class='card'><h3>Topic hints</h3>{''.join(_bar(k,v,max_topic) for k,v in topic_counts.items()) or '<span class="muted">—</span>'}</div>
        <div class='card'><h3>Visibility flags</h3>{_list(flags, 12)}</div>
      </div>
      <div class='social-grid'>{cards}</div>
    </section>
    """


def _overview(report: DeepSearchReport) -> str:
    findings = report.findings or {}
    contacts = findings.get("contacts", {})
    media = findings.get("media", {})
    social = findings.get("social_intelligence", {}).get("summary", {})
    rejected = sum((report.stats.get("rejected", {}) or {}).values())
    adv = findings.get("advanced", {})
    completeness = (adv.get("profile_completeness") or {}).get("score", 0)
    return f"""
    <div class='topbar'>
      <div>
        <div class='eyebrow'>Local public OSINT report</div>
        <h1>{html_escape(report.query)}</h1>
        <p class='subtitle'>Mode: <b>{html_escape(report.mode)}</b> · Target type: <b>{html_escape(report.target_type)}</b> · Created: {html_escape(report.created_at)}</p>
      </div>
      <div class='actions'><a class='btn ghost' href='/'>New search</a><button class='btn primary' onclick='copySummary()'>Copy summary</button></div>
    </div>
    <section class='panel'>
      <div class='metrics'>
        {_metric('Overall confidence', report.confidence_overall, 'strict identity filter', _conf_class(report.confidence_overall))}
        {_metric('Evidence', len(report.evidence), 'accepted public sources')}
        {_metric('Social profiles', social.get('total_profiles', len(findings.get('social_profiles', []))), 'public profile signals')}
        {_metric('Rejected', rejected, 'noise / false positives filtered')}
        {_metric('Completeness', f'{completeness}%', 'profile completeness estimate')}
        {_metric('Images', len(media.get('images', [])), 'curated media URLs')}
        {_metric('Emails', len(contacts.get('emails', [])), 'only from accepted evidence')}
        {_metric('Phones', len(contacts.get('phones', [])), 'only from accepted evidence')}
      </div>
    </section>
    <section class='panel'>
      <div class='panel-title'><div><h2>Executive summary</h2><p class='muted'>Short, source-grounded overview.</p></div></div>
      <div class='executive' id='execSummary'>{html_escape(report.executive_summary or '—')}</div>
    </section>
    {_key_findings(report)}
    """


def _key_findings(report: DeepSearchReport) -> str:
    f = report.findings or {}
    return f"""
    <section class='panel'>
      <div class='panel-title'><div><h2>Key findings</h2><p class='muted'>Curated signals extracted from accepted evidence only.</p></div></div>
      <div class='grid'>
        <div class='card'><h3>Social/profile URLs</h3>{_list(f.get('social_profiles', []), 12)}</div>
        <div class='card'><h3>Organizations</h3>{_list(f.get('organizations', []), 12)}</div>
        <div class='card'><h3>Locations</h3>{_list(f.get('locations', []), 12)}</div>
        <div class='card'><h3>Related names</h3>{_list(f.get('related_names', []), 12)}</div>
        <div class='card'><h3>Contacts</h3>{_list(f.get('contacts', {}), 8)}</div>
        <div class='card'><h3>Dates / timeline hints</h3>{_list(f.get('dates', []), 12)}</div>
      </div>
    </section>
    """


def _evidence_table(report: DeepSearchReport) -> str:
    rows = ""
    for ev in report.evidence:
        why = ", ".join(ev.matched_terms[:8])
        rows += f"""
        <tr data-conf='{html_escape(ev.confidence)}'>
          <td>#{ev.id}</td>
          <td><span class='badge {_conf_class(ev.confidence)}'>{html_escape(ev.confidence)}</span></td>
          <td><span class='score'>{ev.relevance_score:.1f}</span></td>
          <td><b>{html_escape(ev.title[:100])}</b><br><span class='muted'>{html_escape(ev.source)}</span></td>
          <td>{html_escape((ev.snippet or ev.extracted_text[:220])[:340])}<br><span class='muted small'>Why: {html_escape(why)}</span></td>
          <td>{_link(ev.url, 'open', 'btn ghost')}</td>
        </tr>
        """
    if not rows:
        rows = "<tr><td colspan='6'>No accepted evidence. Add more context or use exact quotes.</td></tr>"
    details = ""
    for ev in report.evidence[:25]:
        details += f"""
        <details class='detail'>
          <summary><b>#{ev.id}</b> {html_escape(ev.title)} <span class='badge {_conf_class(ev.confidence)}'>{html_escape(ev.confidence)}</span></summary>
          <div class='detail-grid'>
            <div><h3>Match reasons</h3>{''.join(_pill(x) for x in ev.matched_terms[:16]) or '<span class="muted">—</span>'}</div>
            <div><h3>Contacts</h3>{_list({'emails': ev.emails, 'phones': ev.phones}, 8)}</div>
            <div><h3>Profiles</h3>{_list(ev.social_profiles, 8)}</div>
            <div><h3>Entities</h3>{_list({'orgs': ev.organizations, 'locations': ev.locations, 'names': ev.related_names}, 8)}</div>
          </div>
          <p>{_link(ev.url)}</p>
          <pre>{html_escape(ev.extracted_text[:3600])}</pre>
        </details>
        """
    return f"""
    <section class='panel'>
      <div class='panel-title'><div><h2>Evidence table</h2><p class='muted'>Filterable source table with confidence, score and match explanation.</p></div></div>
      <div class='filters'><input id='evSearch' oninput='filterEvidence()' placeholder='Filter by domain, title, signal, text...'><select id='evConf' onchange='filterEvidence()'><option value='all'>All confidence</option><option value='high'>High</option><option value='medium'>Medium</option><option value='low'>Low</option><option value='very_low'>Very low</option></select></div>
      <div class='table-wrap'><table id='evidenceTable'><thead><tr><th>ID</th><th>Confidence</th><th>Score</th><th>Source</th><th>Evidence</th><th>Link</th></tr></thead><tbody>{rows}</tbody></table></div>
      <h2 style='margin-top:24px'>Evidence details</h2>{details}
    </section>
    """


def _identity_section(report: DeepSearchReport) -> str:
    adv = (report.findings or {}).get("advanced") or {}
    comp = adv.get("profile_completeness") or {}
    candidates = adv.get("identity_candidates") or []
    fp = adv.get("false_positive_control") or {}
    source_quality = adv.get("source_quality") or []
    checks = comp.get("checks") or {}
    cand_rows = "".join(f"<tr><td>{html_escape(str(c.get('candidate','')))}</td><td><span class='score'>{html_escape(str(c.get('score','')))}</span></td><td>{html_escape(str(c.get('summary','')))}</td><td>{html_escape(', '.join(map(str,c.get('evidence_ids',[]))))}</td></tr>" for c in candidates[:12]) or "<tr><td colspan='4'>—</td></tr>"
    sq_rows = "".join(f"<tr><td>#{q.get('evidence_id')}</td><td>{html_escape(q.get('domain',''))}</td><td>{q.get('score')}</td><td>{html_escape(q.get('band',''))}</td><td>{html_escape(', '.join(q.get('reasons',[])))}</td></tr>" for q in source_quality[:20]) or "<tr><td colspan='5'>—</td></tr>"
    check_html = "".join(_pill(f"{k}: {'yes' if v else 'no'}", 'good' if v else 'weak') for k, v in checks.items()) or "<span class='muted'>—</span>"
    return f"""
    <section class='panel'>
      <div class='panel-title'><div><h2>Identity resolution</h2><p class='muted'>Candidate clustering, completeness and false-positive controls.</p></div></div>
      <div class='grid'>
        <div class='card'><h3>Profile completeness</h3><p><span class='score'>{html_escape(str(comp.get('score',0)))}%</span> <span class='muted'>{html_escape(comp.get('band','unknown'))}</span></p><div>{check_html}</div></div>
        <div class='card warning'><h3>False-positive control</h3>{_list(fp, 10)}</div>
        <div class='card'><h3>Recommended improvements</h3>{_list(adv.get('monitoring_suggestions', []), 8)}</div>
      </div>
      <h2 style='margin-top:20px'>Identity candidates</h2><div class='table-wrap'><table><thead><tr><th>Candidate</th><th>Score</th><th>Summary</th><th>Evidence IDs</th></tr></thead><tbody>{cand_rows}</tbody></table></div>
      <h2 style='margin-top:20px'>Source quality</h2><div class='table-wrap'><table><thead><tr><th>Evidence</th><th>Domain</th><th>Score</th><th>Band</th><th>Reasons</th></tr></thead><tbody>{sq_rows}</tbody></table></div>
    </section>
    """


def _timeline(report: DeepSearchReport) -> str:
    adv = (report.findings or {}).get("advanced") or {}
    timeline = adv.get("timeline") or []
    rows = "".join(f"<tr><td>{html_escape(str(t.get('date','')))}</td><td>#{t.get('evidence_id','')}</td><td>{html_escape(str(t.get('title','')))}</td><td>{html_escape(str(t.get('source','')))}</td></tr>" for t in timeline[:60]) or "<tr><td colspan='4'>No date hints extracted.</td></tr>"
    return f"<section class='panel'><div class='panel-title'><div><h2>Timeline</h2><p class='muted'>Date hints extracted from accepted evidence.</p></div></div><div class='table-wrap'><table><thead><tr><th>Date</th><th>Evidence</th><th>Title</th><th>Source</th></tr></thead><tbody>{rows}</tbody></table></div></section>"


def _media(report: DeepSearchReport) -> str:
    media = (report.findings or {}).get("media") or {}
    images = media.get("images") or []
    videos = media.get("videos") or []
    gallery = "".join(f"<a href='{html_escape(u)}' target='_blank' rel='noreferrer'><img src='{html_escape(u)}' loading='lazy' alt=''/></a>" for u in images[:30]) or "<div class='empty'>No reliable images accepted after noise filtering.</div>"
    return f"<section class='panel'><div class='panel-title'><div><h2>Media gallery</h2><p class='muted'>Curated images and videos linked from accepted sources.</p></div></div><h3>Images</h3><div class='gallery'>{gallery}</div><h3 style='margin-top:18px'>Videos</h3>{_list(videos, 18)}</section>"


def _network(report: DeepSearchReport) -> str:
    f = report.findings or {}
    nodes = [report.query]
    nodes += list((f.get("mentions", {}).get("top_domains", {}) or {}).keys())[:10]
    nodes += list(f.get("organizations", []))[:8]
    nodes += list(f.get("locations", []))[:6]
    nodes += [p.get("platform", "") for p in (f.get("social_intelligence", {}).get("profiles") or [])[:8]]
    nodes = [n for n in dict.fromkeys(nodes) if n]
    if len(nodes) <= 1:
        return "<section class='panel'><h2>Network</h2><div class='empty'>Not enough nodes to draw a useful graph.</div></section>"
    w, h, cx, cy = 920, 360, 460, 180
    import math
    svg_nodes = f"<circle cx='{cx}' cy='{cy}' r='36' fill='#7c3aed'/><text x='{cx}' y='{cy+4}' text-anchor='middle' fill='white' font-size='13' font-weight='800'>TARGET</text>"
    svg_edges = ""
    for i, n in enumerate(nodes[1:28], start=0):
        angle = (2 * math.pi * i) / max(1, min(len(nodes)-1, 27))
        x = cx + int(math.cos(angle) * 300)
        y = cy + int(math.sin(angle) * 125)
        svg_edges += f"<line x1='{cx}' y1='{cy}' x2='{x}' y2='{y}' stroke='rgba(148,163,184,.38)'/>"
        label = html_escape(str(n)[:24])
        color = '#06b6d4' if '.' in str(n) else '#22c55e'
        svg_nodes += f"<circle cx='{x}' cy='{y}' r='12' fill='{color}'/><text x='{x+16}' y='{y+4}' fill='#dbeafe' font-size='12'>{label}</text>"
    return f"<section class='panel'><div class='panel-title'><div><h2>Relationship network</h2><p class='muted'>Curated high-signal map: target, domains, organizations, locations and social platforms.</p></div></div><svg class='network' viewBox='0 0 {w} {h}'>{svg_edges}{svg_nodes}</svg></section>"


def _ai_report(report: DeepSearchReport) -> str:
    warnings = "".join(f"<li>{html_escape(w)}</li>" for w in report.warnings) or "<li>—</li>"
    errors = "".join(f"<li>{html_escape(e)}</li>" for e in report.provider_errors[:20]) or "<li>—</li>"
    queries = "".join(f"<li><code>{html_escape(q)}</code></li>" for q in report.search_queries[:60])
    return f"<section class='panel'><div class='panel-title'><div><h2>AI report & diagnostics</h2><p class='muted'>AI summary, warnings, provider errors and search queries.</p></div></div><h3>AI Deep Report</h3><pre>{html_escape(report.summary or '—')}</pre><div class='grid'><div class='card warning'><h3>Warnings</h3><ul class='clean'>{warnings}</ul></div><div class='card'><h3>Provider / AI messages</h3><ul class='clean'>{errors}</ul></div><div class='card'><h3>Search queries</h3><ul class='clean'>{queries}</ul></div></div></section>"


def render_html_report(report: DeepSearchReport) -> str:
    html = f"""<!doctype html>
<html lang='hu'>
<head>
<meta charset='utf-8'/><meta name='viewport' content='width=device-width, initial-scale=1'/>
<title>OSINT Professional Report · {html_escape(report.query)}</title>
{_style()}
</head>
<body>
<div class='layout'>
  <aside class='sidebar'>
    <div class='brand'><div class='brand-mark'></div><div>OpenIntel<br><span class='muted small'>Professional OSINT</span></div></div>
    <div class='nav-group'><div class='nav-label'>Report</div>
      <button class='tab-btn active' data-tab='overview' onclick="showTab('overview')">Overview</button>
      <button class='tab-btn' data-tab='identity' onclick="showTab('identity')">Identity</button>
      <button class='tab-btn' data-tab='social' onclick="showTab('social')">Social media</button>
      <button class='tab-btn' data-tab='evidence' onclick="showTab('evidence')">Evidence</button>
      <button class='tab-btn' data-tab='timeline' onclick="showTab('timeline')">Timeline</button>
      <button class='tab-btn' data-tab='network' onclick="showTab('network')">Network</button>
      <button class='tab-btn' data-tab='media' onclick="showTab('media')">Media</button>
      <button class='tab-btn' data-tab='ai' onclick="showTab('ai')">AI & diagnostics</button>
    </div>
    <div class='nav-group'><div class='nav-label'>Safety</div><p class='muted small'>Public web only. No login bypass, no private databases, no paywall or privacy circumvention.</p></div>
  </aside>
  <main class='main'>
    <section id='overview' class='tab-panel active'>{_overview(report)}</section>
    <section id='identity' class='tab-panel'>{_identity_section(report)}</section>
    <section id='social' class='tab-panel'>{_social_section(report)}</section>
    <section id='evidence' class='tab-panel'>{_evidence_table(report)}</section>
    <section id='timeline' class='tab-panel'>{_timeline(report)}</section>
    <section id='network' class='tab-panel'>{_network(report)}</section>
    <section id='media' class='tab-panel'>{_media(report)}</section>
    <section id='ai' class='tab-panel'>{_ai_report(report)}</section>
  </main>
</div>
{_tabs_js()}
</body></html>"""
    return html
