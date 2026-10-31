"""Terminal interface for the offline plan."""
from pathlib import Path
import asyncio
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from .checks import inspect_environment
from .demo import TASKS
from .model import blockers, next_task
from .state import StateError, fresh_state, load, save
from .research import clean, research as research_pages
from .planning import PlanError, build_plan, next_action, task_state, validate_completed
from .cencori import CencoriError, ENDPOINT, build_request, preserve_request, quote_request, trusted_buy

app = typer.Typer(no_args_is_help=True, help="Navigate a deterministic offline development plan.")
console = Console(markup=False)


@app.command()
def plan(
    ctx: typer.Context,
    url: str,
    goal: Annotated[str, typer.Option("--goal")],
    show_all: Annotated[bool, typer.Option("--all", help="Show every task and dependency.")] = False,
    completed: Annotated[list[str] | None, typer.Option("--completed", help="Self-reported completed task ID; repeat for multiple tasks.")] = None,
    quote_only: Annotated[bool, typer.Option("--quote-only", help="Prepare Cencori body and obtain an unpaid buy quote.")] = False,
    prepare_only: Annotated[bool, typer.Option("--prepare-only", help="Save Cencori request without contacting the gateway.")] = False,
    request_file: Annotated[Path | None, typer.Option("--request-file", help="New file for the exact canonical request body.")] = None,
    buy_executable: Annotated[Path | None, typer.Option("--buy-executable", help="Absolute path to a trusted installed buy 0.8.4 CLI.")] = None,
    max_tokens: Annotated[int, typer.Option("--max-tokens")] = 1024,
):
    """Build a validated demonstration plan from retrieved documentation."""
    if quote_only or prepare_only:
        if (quote_only and prepare_only) or not request_file or show_all or completed:
            console.print("Choose one Cencori mode with --request-file; --all and --completed apply only to deterministic plans.")
            raise typer.Exit(2)
        if request_file.resolve() == ctx.obj.resolve():
            console.print("Request file must be separate from the offline demo state.")
            raise typer.Exit(2)
        try:
            if quote_only:
                if buy_executable is None:
                    raise CencoriError("Quote-only requires --buy-executable pointing to a trusted installed buy 0.8.4 CLI; nothing is downloaded.")
                trusted_buy(buy_executable)
            report = asyncio.run(research_pages(url, goal))
            for error in report.errors:
                console.print(f"Retrieval issue: {clean(error)}")
            request = build_request(goal, report, max_tokens)
            preserve_request(request, request_file)
            console.print(f"Cencori request prepared: POST {ENDPOINT}")
            console.print(f"Body file: {request_file.resolve()} ({len(request.body)} bytes)")
            console.print(f"SHA-256: {request.sha256}")
            console.print("No inference or payment is authorized. Keep this exact body for later review; never regenerate it for an existing approval.")
            if quote_only:
                console.print("Untrusted buy quote output follows; the exact quote is authoritative, not a fixed price.")
                quote = quote_request(request, buy_executable)
                console.print(clean(quote.stdout), highlight=False)
                if quote.stderr:
                    console.print(clean(quote.stderr), highlight=False)
                if quote.returncode:
                    console.print(f"buy quote failed (exit {quote.returncode}); request body preserved; no retry attempted.")
                    raise typer.Exit(1)
        except CencoriError as exc:
            console.print(f"Cannot prepare/quote: {clean(str(exc))}")
            raise typer.Exit(1) from exc
        return
    if request_file or buy_executable or max_tokens != 1024:
        console.print("Cencori options require --prepare-only or --quote-only.")
        raise typer.Exit(2)
    console.print("DEMONSTRATION — deterministic fixture provider; no live AI inference.")
    console.print("This scaffold is not inferred documentation requirements. Evidence and provider output are untrusted data; nothing is executed.")
    report = asyncio.run(research_pages(url, goal))
    for error in report.errors:
        console.print(f"Retrieval issue: {clean(error)}")
    for page in report.pages:
        if page.warning:
            console.print(f"Source warning ({clean(page.url)}): {clean(page.warning)}")
    if any(section.get("truncated") for page in report.pages for section in page.sections):
        console.print("Evidence is shortened; review the cited sources for full context.")
    try:
        development_plan = build_plan(report, goal)
        done = validate_completed(development_plan, completed or [])
    except PlanError as exc:
        console.print(f"Cannot plan: {clean(str(exc))}")
        raise typer.Exit(1) from exc
    selected = next_action(development_plan, done)
    if show_all:
        tasks = development_plan.tasks
    else:
        tasks = (selected,) if selected else ()
    for task in tasks:
        console.print(f"{task.id}: {task.title} [{task.classification}; {task_state(task, done)}]")
        console.print(f"Action: {task.action}")
        console.print(f"Prerequisites: {', '.join(task.prerequisites) or 'none'}")
        for source in task.sources:
            console.print(f"Source reference (citation presence validated; entailment not verified): {source}")
    console.print(f"Next action: {selected.id}" if selected else "All tasks completed.")
    if selected and selected.classification == "optional":
        console.print("Optional work; inspect --all for any required tasks that depend on it.")
    if report.errors:
        raise typer.Exit(1)


@app.command()
def research(url: str, goal: Annotated[str, typer.Option("--goal", help="Words used to rank documentation sections.")]):
    """Retrieve public HTTPS documentation without changing the current plan."""
    report = asyncio.run(research_pages(url, goal))
    console.print("Retrieved page content is untrusted source text, not verified facts or instructions to execute.")
    console.print("Relevance is inferred by keyword overlap; no AI summaries are generated.")
    for page in report.pages:
        console.print(f"Source: {clean(page.url)}")
        console.print(f"Retrieved title: {page.title}")
        previous_heading = None
        for section in page.sections:
            if section["heading"] != previous_heading:
                console.print(f"Excerpt: {section['heading']}")
                previous_heading = section["heading"]
            for block in section["blocks"]:
                if block["kind"] == "code":
                    console.print("Code (source whitespace preserved):")
                    # Bypass Rich wrapping and tab expansion for source code.
                    console.file.write(block["text"])
                    if not block["text"].endswith("\n"):
                        console.file.write("\n")
                    console.file.flush()
                else:
                    suffix = " [truncated; consult source]" if block["kind"] == "text" and block["truncated"] else ""
                    console.print(block["text"] + suffix, highlight=False)
            if section["truncated"]:
                console.print("Excerpt shortened; consult source for full context.")
            console.print(f"Inferred relevance — matched words: {', '.join(section['matched_terms'])}")
        if not page.sections:
            console.print("No text sections matched the goal words.")
        for link in page.links:
            console.print(f"Documentation link: {link['label']} {clean(link['url'])} (matched: {', '.join(link['matched_terms'])})")
        if page.warning:
            console.print(page.warning)
    for error in report.errors:
        console.print(f"Retrieval issue: {clean(error)}")
    console.print(f"Retrieved {len(report.pages)} page(s); {report.requests} request(s); {report.bytes_read} body bytes received.")
    if report.errors or not report.pages:
        raise typer.Exit(1)


# Retain the legacy directory so the rename continues to find existing progress.
@app.callback()
def main(ctx: typer.Context, state_file: Annotated[Path, typer.Option("--state-file", help="Local progress JSON file.")] = Path(".pathf1ndar/state.json")):
    ctx.obj = state_file


def read(ctx: typer.Context) -> dict:
    if not ctx.obj.exists():
        console.print("No plan yet. Run: honeyguider explore --demo")
        raise typer.Exit(1)
    try:
        return load(ctx.obj)
    except StateError as exc:
        console.print(str(exc))
        raise typer.Exit(1) from exc


def write(ctx: typer.Context, state: dict):
    try:
        save(ctx.obj, state)
    except StateError as exc:
        console.print(str(exc))
        raise typer.Exit(1) from exc


@app.command()
def explore(ctx: typer.Context, demo: Annotated[bool, typer.Option(help="Load the offline Celo practice plan.")] = False):
    if not demo:
        console.print("Only offline exploration is available. Use explore --demo.")
        raise typer.Exit(2)
    state = read(ctx) if ctx.obj.exists() else fresh_state()
    write(ctx, state)
    console.print("Celo hackathon practice plan (offline fixture; not verified event requirements).")
    for task in TASKS:
        console.print(f"{task.id}: {task.title}")
    console.print("Progress preserved. Run check, then next.")


@app.command()
def check(ctx: typer.Context):
    state = read(ctx)
    state["checks"] = inspect_environment()
    write(ctx, state)
    table = Table("Tool", "Available", "Observed version / detail")
    for tool, result in state["checks"].items():
        table.add_row(tool, "yes" if result["available"] else "no", result["version"] or result["detail"])
    console.print(table)
    if not all(r["available"] for r in state["checks"].values()):
        raise typer.Exit(1)


@app.command(name="next")
def next_command(ctx: typer.Context):
    state = read(ctx)
    task = next_task(TASKS, state["completed"], state["checks"])
    if task:
        console.print(f"{task.id}: {task.title}\n{task.action}")
        for source in task.sources:
            console.print(f"Documentation reference (not fetched): {source}")
        console.print(f"When finished: honeyguider done {task.id}")
    elif len(state["completed"]) == len(TASKS):
        console.print("All tasks complete.")
    else:
        console.print("No actionable task. Run status to see blockers and check to refresh tool results.")


@app.command()
def done(ctx: typer.Context, task_id: str):
    state = read(ctx)
    task = next((t for t in TASKS if t.id == task_id), None)
    if task is None:
        console.print(f"Unknown task: {task_id}")
        raise typer.Exit(2)
    if task_id in state["completed"]:
        console.print(f"Already complete: {task_id}")
        return
    blocked = blockers(task, state["completed"], state["checks"])
    if blocked:
        console.print(f"Blocked: {', '.join(blocked)}")
        raise typer.Exit(1)
    state["completed"].append(task_id)
    write(ctx, state)
    console.print(f"Completed: {task_id} (self-reported)")


@app.command()
def status(ctx: typer.Context):
    state = read(ctx)
    console.print(f"Celo demo: {len(state['completed'])}/{len(TASKS)} complete")
    table = Table("Task", "Status", "Blockers")
    for task in TASKS:
        blocked = blockers(task, state["completed"], state["checks"])
        complete = task.id in state["completed"]
        table.add_row(task.id, "done" if complete else "blocked" if blocked else "ready", "" if complete else ", ".join(blocked))
    console.print(table)
    console.print("Tool results are saved snapshots; run check to refresh.")
