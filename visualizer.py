from __future__ import annotations

import math
from collections import Counter
from typing import Any

from .models import DeepSearchReport
from .utils import html_escape, root_domain

CONFIDENCE_WEIGHTS = {"high": 4, "medium": 3, "low": 2, "very_low": 1, "none": 0}


def _limit_dict(d: dict[str, int], n: int = 8) -> list[tuple[str, int]]:
    return [(str(k), int(v)) for k, v in list(d.items())[:n] if int(v) > 0]


def _bar_rows(rows: list[tuple[str, int | float]], max_rows: int = 8, suffix: str = "") -> str:
    rows = rows[:max_rows]
    if not rows:
        return "<div class='empty'>No data</div>"
    maxv = max(float(v) for _, v in rows) or 1
    html = "<div class='bars'>"
    for label, value in rows:
        pct = max(3, min(100, float(value) / maxv * 100))
        html += f"""
        <div class='bar-row'>
          <div class='bar-label' title='{html_escape(str(label))}'>{html_escape(str(label))}</div>
          <div class='bar-track'><div class='bar-fill' style='width:{pct:.1f}%'></div></div>
          <div class='bar-value'>{html_escape(str(value))}{html_escape(suffix)}</div>
        </div>"""
    html += "</div>"
    return html


def _confidence_rows(report: DeepSearchReport) -> list[tuple[str, int]]:
    c = Counter(ev.confidence for ev in report.evidence)
    return [(k, c[k]) for k in ["high", "medium", "low", "very_low"] if c[k]]


def _entity_rows(report: DeepSearchReport) -> list[tuple[str, int]]:
    counts = report.findings.get("visual_profile", {}).get("entity_counts", {}) if report.findings else {}
    labels = [
        ("social_profiles", "Social"), ("emails", "Emails"), ("phones", "Phones"),
        ("usernames", "Usernames"), ("images", "Images"), ("videos", "Videos"),
        ("locations", "Locations"), ("organizations", "Organizations"), ("related_names", "Names"),
        ("dates", "Dates"),
    ]
    return [(label, int(counts.get(key, 0))) for key, label in labels if int(counts.get(key, 0)) > 0]


def _score_rows(report: DeepSearchReport) -> list[tuple[str, float]]:
    return [(f"#{ev.id} {ev.source or ev.title[:20]}", ev.relevance_score) for ev in report.evidence[:8]]


def _mini_network_svg(report: DeepSearchReport) -> str:
    # Small, readable radial graph. Only top evidence + curated entity nodes.
    nodes: list[dict[str, Any]] = [{"id": "q", "label": report.query[:34], "group": "query"}]
    edges: list[tuple[int, int]] = []

    def add_node(label: str, group: str) -> int:
        label = str(label or "").strip()
        if not label:
            return -1
        if len(label) > 38:
            label = label[:37] + "…"
        for i, n in enumerate(nodes):
            if n["label"] == label and n["group"] == group:
                return i
        nodes.append({"id": f"n{len(nodes)}", "label": label, "group": group})
        return len(nodes) - 1

    for ev in report.evidence[:7]:
        d = root_domain(ev.source or ev.url)
        di = add_node(d, "domain")
        if di >= 0:
            edges.append((0, di))
        ti = add_node(f"#{ev.id} {ev.title[:26]}", "evidence")
        if di >= 0 and ti >= 0:
            edges.append((di, ti))
        for s in ev.social_profiles[:2]:
            si = add_node(root_domain(s) or s[:22], "social")
            if ti >= 0 and si >= 0:
                edges.append((ti, si))
        for o in ev.organizations[:2]:
            oi = add_node(o, "org")
            if ti >= 0 and oi >= 0:
                edges.append((ti, oi))
        for l in ev.locations[:2]:
            li = add_node(l, "loc")
            if ti >= 0 and li >= 0:
                edges.append((ti, li))

    nodes = nodes[:34]
    allowed = set(range(len(nodes)))
    edges = [(a, b) for a, b in edges if a in allowed and b in allowed][:60]
    if len(nodes) <= 1:
        return "<div class='empty'>No graph data</div>"

    w, h = 920, 440
    cx, cy = w / 2, h / 2
    coords: list[tuple[float, float]] = [(cx, cy)]
    n = len(nodes) - 1
    for i in range(n):
        angle = 2 * math.pi * i / max(1, n)
        radius = 150 + (45 if i % 2 else 0)
        coords.append((cx + math.cos(angle) * radius, cy + math.sin(angle) * radius))

    group_class = {"query": "node-query", "domain": "node-domain", "evidence": "node-evidence", "social": "node-social", "org": "node-org", "loc": "node-loc"}
    lines = []
    for a, b in edges:
        x1, y1 = coords[a]; x2, y2 = coords[b]
        lines.append(f"<line x1='{x1:.1f}' y1='{y1:.1f}' x2='{x2:.1f}' y2='{y2:.1f}' />")
    circles = []
    for i, node in enumerate(nodes):
        x, y = coords[i]
        cls = group_class.get(node.get("group"), "node-evidence")
        r = 18 if i == 0 else 9
        label_y = y - 16 if i else y - 26
        circles.append(f"<circle class='{cls}' cx='{x:.1f}' cy='{y:.1f}' r='{r}'/><text x='{x:.1f}' y='{label_y:.1f}'>{html_escape(node['label'])}</text>")
    return f"<svg class='mini-network' viewBox='0 0 {w} {h}' role='img'>{''.join(lines)}{''.join(circles)}</svg>"


def render_visual_dashboard(report: DeepSearchReport) -> str:
    findings = report.findings or {}
    top_domains = _limit_dict(findings.get("mentions", {}).get("top_domains", {}), 8)
    confidence = _confidence_rows(report)
    entities = _entity_rows(report)
    scores = _score_rows(report)
    kpis = [
        ("Accepted evidence", len(report.evidence)),
        ("Confidence", report.confidence_overall),
        ("Domains", len(findings.get("mentions", {}).get("top_domains", {}) or {})),
        ("Profiles", len(findings.get("social_profiles", []) or [])),
        ("Images", len(findings.get("media", {}).get("images", []) or [])),
        ("Rejected", sum((report.stats.get("rejected", {}) or {}).values())),
    ]
    kpi_html = "".join(f"<div class='kpi'><span>{html_escape(k)}</span><b>{html_escape(str(v))}</b></div>" for k, v in kpis)
    dates = findings.get("dates", [])[:12]
    date_html = "".join(f"<span class='chip'>{html_escape(str(d))}</span>" for d in dates) or "<span class='empty'>No date hints</span>"
    return f"""
<section class='panel visual-panel'>
  <div class='section-title'><div><h2>Visual overview</h2><p>Curated signals only. Large noisy raw lists are hidden from the main view.</p></div></div>
  <div class='kpi-grid'>{kpi_html}</div>
  <div class='viz-grid'>
    <div class='viz-card'><h3>Source domains</h3>{_bar_rows(top_domains)}</div>
    <div class='viz-card'><h3>Evidence confidence</h3>{_bar_rows(confidence)}</div>
    <div class='viz-card'><h3>Entity summary</h3>{_bar_rows(entities)}</div>
    <div class='viz-card'><h3>Top evidence scores</h3>{_bar_rows(scores)}</div>
  </div>
  <div class='viz-card full'><h3>Readable relationship map</h3>{_mini_network_svg(report)}</div>
  <div class='viz-card full'><h3>Date hints</h3><div class='chip-row'>{date_html}</div></div>
</section>
"""
