"""Terminal interface for the offline plan."""
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from .checks import inspect_environment
from .demo import TASKS
from .model import blockers, next_task
from .state import StateError, fresh_state, load, save

app = typer.Typer(no_args_is_help=True, help="Navigate a deterministic offline development plan.")
console = Console(markup=False)


@app.callback()
def main(ctx: typer.Context, state_file: Annotated[Path, typer.Option("--state-file", help="Local progress JSON file.")] = Path(".pathf1ndar/state.json")):
    ctx.obj = state_file


def read(ctx: typer.Context) -> dict:
    if not ctx.obj.exists():
        console.print("No plan yet. Run: pathf1ndar explore --demo")
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
        console.print(f"When finished: pathf1ndar done {task.id}")
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
