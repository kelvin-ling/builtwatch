"""BuiltWatch command line.

Everything the product does is reachable here, including the parts a scheduler calls.
The CLI is the local runnable mode: no AWS deployment is required to use BuiltWatch.
"""

from __future__ import annotations

import logging
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from . import __version__
from .config import CostMeter, Settings
from .export import to_json, to_markdown
from .models import Disposition, DispositionAction, Relevance
from .pipeline import run_scan
from .registry import coverage_statement, load_registry
from .store import Store, new_id

app = typer.Typer(
    add_completion=False,
    help="BuiltWatch — remember what you built, notice when the world changes under it.",
)
system_app = typer.Typer(help="Manage the inventory of systems you have built.")
source_app = typer.Typer(help="Inspect the curated source registry.")
finding_app = typer.Typer(help="Review, dispose of, and export findings.")
app.add_typer(system_app, name="system")
app.add_typer(source_app, name="source")
app.add_typer(finding_app, name="finding")

console = Console()


def _settings() -> Settings:
    return Settings()


def _store(settings: Settings) -> Store:
    return Store(settings.db_path)


@app.callback()
def main(verbose: bool = typer.Option(False, "--verbose", "-v")) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )


@app.command()
def version() -> None:
    """Print the BuiltWatch version."""
    console.print(f"BuiltWatch {__version__}")


# ---------------------------------------------------------------------------- systems


@system_app.command("add")
def system_add(
    description: str = typer.Argument(None, help="Plain-text description of the system."),
    from_file: Path = typer.Option(None, "--from-file", help="Read the description from a file."),
    system_id: str = typer.Option(None, "--id", help="Override the generated system id."),
) -> None:
    """Describe a system in plain text; BuiltWatch extracts a structured passport."""
    from .intake import from_text

    settings = _settings()
    if settings.demo_mode:
        console.print("[red]Demo mode is read-only. Cannot add systems.[/red]")
        raise typer.Exit(1)

    text = from_file.read_text(encoding="utf-8") if from_file else description
    if not text:
        console.print("[red]Provide a description or --from-file.[/red]")
        raise typer.Exit(1)

    store = _store(settings)
    meter = CostMeter(settings, store.spent_today(), store.spent_this_month())
    with console.status("Extracting system passport..."):
        passport = from_text(text, settings, meter, system_id=system_id)
    store.upsert_system(passport)

    console.print(Panel(f"[bold]{passport.name}[/bold]  (`{passport.id}`)\n{passport.purpose}"))
    _print_passport(passport)
    console.print(f"\n[dim]Extraction cost ~${meter.run_cost:.4f}[/dim]")
    console.print("\n[yellow]Confirm these before relying on them.[/yellow] "
                  f"Edit with: builtwatch system show {passport.id} --json")


@system_app.command("import")
def system_import(path: Path = typer.Argument(..., help="Path to a JSON system passport.")) -> None:
    """Import a versioned JSON system passport."""
    from .intake import from_json_file

    settings = _settings()
    store = _store(settings)
    passport = from_json_file(path)
    store.upsert_system(passport)
    console.print(f"[green]Imported[/green] {passport.name} (`{passport.id}`)")


@system_app.command("list")
def system_list() -> None:
    """List every system in the inventory."""
    store = _store(_settings())
    systems = store.list_systems()
    if not systems:
        console.print("[dim]No systems yet. Add one with: builtwatch system add \"...\"[/dim]")
        return
    table = Table("id", "name", "services", "unknowns", title="Inventory")
    for s in systems:
        table.add_row(s.id, s.name, ", ".join(s.services[:3]) or "—", str(len(s.unknowns)))
    console.print(table)


@system_app.command("show")
def system_show(
    system_id: str,
    as_json: bool = typer.Option(False, "--json", help="Emit the passport as JSON."),
) -> None:
    """Show one system passport."""
    store = _store(_settings())
    passport = store.get_system(system_id)
    if passport is None:
        console.print(f"[red]No such system: {system_id}[/red]")
        raise typer.Exit(1)
    if as_json:
        console.print_json(passport.model_dump_json(indent=2))
        return
    console.print(Panel(f"[bold]{passport.name}[/bold]\n{passport.purpose}"))
    _print_passport(passport)


def _print_passport(passport) -> None:
    table = Table("field", "value", show_header=False, box=None)
    for label, values in (
        ("technologies", passport.technologies),
        ("services", passport.services),
        ("data categories", passport.data_categories),
        ("jurisdictions", passport.jurisdictions or ["(not recorded)"]),
        ("assumptions", passport.assumptions),
        ("constraints", passport.constraints),
    ):
        table.add_row(label, "\n".join(f"• {v}" for v in values) or "—")
    if passport.consequential_actions:
        table.add_row(
            "consequential actions",
            "\n".join(f"• {a.description}" for a in passport.consequential_actions),
        )
    if passport.unknowns:
        table.add_row("[yellow]unknowns[/yellow]", "\n".join(f"• {u}" for u in passport.unknowns))
    console.print(table)


# ---------------------------------------------------------------------------- sources


@source_app.command("list")
def source_list() -> None:
    """Show exactly which sources are watched. Coverage is explicit, never implied."""
    settings = _settings()
    console.print(coverage_statement(load_registry(settings.registry_path)))


# ------------------------------------------------------------------------------- scan


@app.command()
def scan(
    mode: str = typer.Option("replay", "--mode", help="replay | live"),
    system: list[str] = typer.Option(None, "--system", help="Limit to specific system ids."),
    force: bool = typer.Option(False, "--force", help="Re-report even if already disposed."),
) -> None:
    """Run one watch pass: fetch sources, assess relevance, record findings."""
    settings = _settings()
    if mode == "live" and settings.demo_mode:
        console.print("[red]Demo mode does not permit live fetching.[/red]")
        raise typer.Exit(1)
    if mode not in {"replay", "live"}:
        console.print("[red]--mode must be 'replay' or 'live'[/red]")
        raise typer.Exit(1)

    store = _store(settings)
    with console.status(f"Running {mode} scan..."):
        result = run_scan(
            store, settings, mode=mode, system_ids=list(system or []), force_reassess=force
        )

    console.print()
    console.print(Panel(result.summary_line(), title=f"Scan {result.run.id} ({mode})"))

    if result.coverage_failures:
        table = Table("source", "status", "detail", title="[red]Coverage failures[/red]")
        for health in result.coverage_failures:
            table.add_row(health.source_id, health.fetch_status.value, health.error or "—")
        console.print(table)
        console.print(
            "[yellow]These sources were not checked. Absence of findings for them "
            "does not mean nothing changed.[/yellow]\n"
        )

    for finding in result.new_findings:
        _print_finding(finding)

    if result.insufficient:
        table = Table("system", "title", "missing", title="Needs more information")
        for f in result.insufficient:
            table.add_row(f.system_id, f.title, "; ".join(f.unknowns[:2]) or "—")
        console.print(table)

    if result.suppressed_duplicates:
        console.print(
            f"[dim]{len(result.suppressed_duplicates)} finding(s) suppressed as already "
            f"reported or already dispositioned.[/dim]"
        )
    if result.screened_out:
        console.print(f"[dim]{result.screened_out} pair(s) screened out cheaply.[/dim]")
    console.print(
        f"[dim]Estimated cost ${result.run.estimated_cost_usd:.4f} "
        f"({result.run.input_tokens} in / {result.run.output_tokens} out)[/dim]"
    )


def _print_finding(finding) -> None:
    body = [f"[bold]{finding.title}[/bold]", f"system: {finding.system_id}"]
    if finding.adoption_status.value == "proposed":
        body.append("[yellow]status: PROPOSED — not an adopted requirement[/yellow]")
    if finding.evidence:
        passage = finding.evidence[0].passage.strip().replace("\n", " ")
        body.append(f"\n[italic]“{passage[:280]}”[/italic]")
    if finding.system_facts:
        body.append(f"\nmatched: {finding.system_facts[0].key} = {finding.system_facts[0].value}")
    if finding.review_suggestions:
        body.append("\nsuggested review:")
        body.extend(f"  • {s}" for s in finding.review_suggestions[:3])
    body.append(f"\n[dim]{finding.id}[/dim]")
    console.print(Panel("\n".join(body), border_style="cyan"))


# ---------------------------------------------------------------------------- findings


@finding_app.command("list")
def finding_list(
    system: str = typer.Option(None, "--system"),
    relevance: str = typer.Option(
        None, "--relevance", help="relevant | not_relevant | insufficient_information"
    ),
) -> None:
    """List stored findings."""
    store = _store(_settings())
    findings = store.list_findings(system_id=system, relevance=relevance)
    if not findings:
        console.print("[dim]No findings.[/dim]")
        return
    table = Table("id", "system", "verdict", "status", "title")
    for f in findings:
        table.add_row(f.id, f.system_id, f.relevance.value, f.adoption_status.value, f.title[:60])
    console.print(table)


@finding_app.command("show")
def finding_show(finding_id: str) -> None:
    """Show one finding in full."""
    store = _store(_settings())
    finding = store.get_finding(finding_id)
    if finding is None:
        console.print(f"[red]No such finding: {finding_id}[/red]")
        raise typer.Exit(1)
    passport = store.get_system(finding.system_id)
    console.print(to_markdown(finding, passport))


@finding_app.command("ack")
def finding_ack(finding_id: str, reason: str = typer.Option(None, "--reason")) -> None:
    """Acknowledge a finding so it is not raised again unchanged."""
    _dispose(finding_id, DispositionAction.ACKNOWLEDGED, reason)


@finding_app.command("dismiss")
def finding_dismiss(
    finding_id: str, reason: str = typer.Option(..., "--reason", help="Why it does not apply.")
) -> None:
    """Dismiss a finding with a recorded reason."""
    _dispose(finding_id, DispositionAction.DISMISSED, reason)


def _dispose(finding_id: str, action: DispositionAction, reason: str | None) -> None:
    store = _store(_settings())
    if store.get_finding(finding_id) is None:
        console.print(f"[red]No such finding: {finding_id}[/red]")
        raise typer.Exit(1)
    store.add_disposition(
        Disposition(id=new_id("disp"), finding_id=finding_id, action=action, reason=reason)
    )
    console.print(f"[green]{action.value}[/green] {finding_id}")


@finding_app.command("export")
def finding_export(
    finding_id: str,
    fmt: str = typer.Option("markdown", "--format", help="markdown | json"),
    out: Path = typer.Option(None, "--out", help="Write to a file instead of stdout."),
) -> None:
    """Export a finding as a builder handoff."""
    store = _store(_settings())
    finding = store.get_finding(finding_id)
    if finding is None:
        console.print(f"[red]No such finding: {finding_id}[/red]")
        raise typer.Exit(1)
    passport = store.get_system(finding.system_id)
    rendered = to_json(finding, passport) if fmt == "json" else to_markdown(finding, passport)

    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(rendered, encoding="utf-8")
        store.add_disposition(
            Disposition(
                id=new_id("disp"),
                finding_id=finding_id,
                action=DispositionAction.EXPORTED,
                reason=f"exported to {out}",
            )
        )
        console.print(f"[green]Wrote[/green] {out}")
    else:
        console.print(rendered)


@app.command()
def doctor() -> None:
    """Probe which Bedrock models this account can actually invoke, and recommend a pair.

    The control plane lists models an account may not be entitled to use, so this performs
    a real one-token invocation per model. Total cost is a fraction of a cent.
    """
    from .doctor import diagnose

    settings = _settings()
    with console.status("Probing Bedrock model entitlement..."):
        report = diagnose(settings)

    console.print(
        Panel(
            f"account: {report['account']}\nprincipal: {report['arn']}\n"
            f"region: {report['region']}",
            title="AWS identity",
        )
    )

    table = Table("model", "invocable", "$/1K in", "$/1K out", "detail")
    probed = {r.model_id: r for r in report["screen_results"] + report["assess_results"]}
    for result in probed.values():
        table.add_row(
            result.model_id,
            "[green]yes[/green]" if result.ok else "[red]no[/red]",
            f"{result.input_price:.6f}",
            f"{result.output_price:.6f}",
            (result.error_code or "") if not result.ok else "",
        )
    console.print(table)

    for result in report["screen_results"] + report["assess_results"]:
        if not result.ok and result.hint:
            console.print(f"[yellow]{result.error_code}[/yellow]: {result.hint}")
            break

    if not report["usable"]:
        console.print(
            "\n[red]No usable model pair. "
            "BuiltWatch cannot run the real-model path.[/red]"
        )
        raise typer.Exit(1)

    console.print(
        Panel(
            f"screen: [bold]{report['screen_pick']}[/bold]\n"
            f"assess: [bold]{report['assess_pick']}[/bold]\n\n"
            f"export BW_SCREEN_MODEL={report['screen_pick']}\n"
            f"export BW_ASSESS_MODEL={report['assess_pick']}",
            title="[green]Recommended configuration[/green]",
        )
    )


@app.command()
def status() -> None:
    """Show inventory size, recent runs, coverage health, and spend to date."""
    settings = _settings()
    store = _store(settings)
    systems = store.list_systems()
    runs = store.list_runs(limit=5)

    console.print(Panel(
        f"systems: {len(systems)}\n"
        f"open findings: {len(store.list_findings(relevance=Relevance.RELEVANT.value))}\n"
        f"spend today: ${store.spent_today():.4f} "
        f"(ceiling ${settings.limits.max_cost_per_day_usd:.2f})\n"
        f"spend this month: ${store.spent_this_month():.4f} "
        f"(ceiling ${settings.limits.max_cost_per_month_usd:.2f})",
        title="BuiltWatch status",
    ))
    if runs:
        table = Table("run", "mode", "status", "sources ok/failed", "cost")
        for r in runs:
            ok = r.sources_attempted - len(r.sources_failed)
            table.add_row(
                r.id, r.mode, r.status, f"{ok}/{len(r.sources_failed)}",
                f"${r.estimated_cost_usd:.4f}",
            )
        console.print(table)


if __name__ == "__main__":
    app()
