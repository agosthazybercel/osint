from __future__ import annotations

import argparse
import json
from pathlib import Path

from rich.console import Console
from rich.table import Table

from deepsearch_core.db import record_search
from deepsearch_core.engine import LawfulUseRequired, deep_search
from deepsearch_core.exports import export_csv
from deepsearch_core.report import save_report

console = Console()


def main() -> None:
    parser = argparse.ArgumentParser(description="DeepSearch Local Pro - public web research / people finder style tool")
    parser.add_argument("query", help="Name, email, phone, username, company, domain, URL, or topic")
    parser.add_argument("--mode", choices=["general", "person", "email", "phone", "username", "company", "domain"], default="general")
    parser.add_argument("--target-type", choices=["self", "consented_person", "public_person", "company", "journalism_or_research", "unknown"], default="unknown")
    parser.add_argument("--context", default="", help="Disambiguation context: city, school/company, username, domain, etc.")
    parser.add_argument("--max-results", type=int, default=None, help="Search results per generated query")
    parser.add_argument("--max-pages", type=int, default=None, help="Max result pages to fetch/analyze")
    parser.add_argument("--delay", type=float, default=None, help="Delay between HTTP requests")
    parser.add_argument("--provider", action="append", choices=["duckduckgo", "brave", "serpapi"], help="Search provider. Repeatable. Default: all configured providers + DuckDuckGo")
    parser.add_argument("--no-ai", action="store_true", help="Disable OpenAI Deep Report")
    parser.add_argument("--no-username-scan", action="store_true", help="Disable direct username profile scan")
    parser.add_argument("--lawful-use", action="store_true", help="Confirm lawful, proportionate, public-information use")
    parser.add_argument("--print-json", action="store_true", help="Print full JSON report to stdout")

    args = parser.parse_args()

    try:
        report = deep_search(
            query=args.query,
            mode=args.mode,
            target_type=args.target_type,
            max_results_per_query=args.max_results,
            max_pages=args.max_pages,
            delay_seconds=args.delay,
            providers=args.provider,
            ai=not args.no_ai,
            lawful_use_confirmed=args.lawful_use,
            scan_usernames=not args.no_username_scan,
            context=args.context,
        )
    except LawfulUseRequired as exc:
        console.print(f"[red]{exc}[/red]")
        raise SystemExit(2)

    json_path, html_path, md_path = save_report(report)
    csv_path = export_csv(report)
    record_search(report, json_path=json_path, html_path=html_path)

    if args.print_json:
        console.print_json(json.dumps(report.to_dict(), ensure_ascii=False))
        return

    console.print(f"\n[bold]Executive summary:[/bold] {report.executive_summary}")
    console.print(f"[bold]Overall confidence:[/bold] {report.confidence_overall}")

    if report.warnings:
        console.print("\n[yellow]Warnings:[/yellow]")
        for warning in report.warnings:
            console.print(f"- {warning}")

    table = Table(title="Top evidence")
    table.add_column("ID", justify="right")
    table.add_column("Confidence")
    table.add_column("Score", justify="right")
    table.add_column("Source")
    table.add_column("Title")
    table.add_column("URL")
    for ev in report.evidence[:12]:
        table.add_row(str(ev.id), ev.confidence, str(ev.relevance_score), ev.source[:28], ev.title[:54], ev.url[:70])
    console.print(table)

    console.print("\n[bold green]Files created:[/bold green]")
    console.print(f"HTML: {html_path}")
    console.print(f"JSON: {json_path}")
    console.print(f"Markdown: {md_path}")
    console.print(f"CSV: {csv_path}")

    if report.provider_errors:
        console.print("\n[yellow]Provider/AI messages:[/yellow]")
        for error in report.provider_errors[:8]:
            console.print(f"- {error}")


if __name__ == "__main__":
    main()
