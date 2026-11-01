"""Small opt-in navigation layer over the existing command functions."""
from pathlib import Path
import shlex
import sys

import typer
from typer.main import get_command

from . import cli, track_cli
from .demo import TASKS
from .model import next_task
from .planning import next_action
from .state import fresh_state


def interactive_terminal() -> bool:
    """Require both input and output terminals; pipes must never prompt."""
    return sys.stdin.isatty() and sys.stdout.isatty()


def choose(label: str, choices: dict[str, str]) -> str:
    for key, description in choices.items():
        cli.console.print(f"  {key}  {description}")
    while True:
        answer = typer.prompt(label, default="0").strip()
        if answer in choices:
            return answer
        cli.console.print("Invalid choice. Enter one of: " + ", ".join(choices))


def track_context(ctx: typer.Context, directory: Path, command: str):
    """Use the group's parser and callback, including its storage boundary."""
    group = get_command(track_cli.app)
    return group, group.make_context(
        "track", ["--state-dir", str(directory), command], parent=ctx
    )


def session(ctx: typer.Context, directory: Path | None = None):
    """Read progress only; mutations remain explicit existing commands."""
    while True:
        if directory is None:
            state = cli.read(ctx)
            task = next_task(TASKS, state["completed"], state["checks"])
            cli.console.print(f"Offline demo: {len(state['completed'])}/{len(TASKS)} complete")
            finished = len(state["completed"]) == len(TASKS)
        else:
            # Apply the same path checks and private-state validation as track.
            _, child = track_context(ctx, directory, "next")
            with child, track_cli.boundary():
                child.invoke(track_cli.main, ctx=child, state_dir=directory)
                _, plan, completed = track_cli.read(child)
                finished = all(t.id in completed for t in plan.tasks if t.classification == "required")
                task = None if finished else next_action(plan, completed)
                cli.console.print(f"Tracked plan: {len(completed)}/{len(plan.tasks)} complete (self-reported)")
        if task:
            cli.console.print(f"Next action: {task.id}: {task.title}", style="bold")
            cli.console.print(task.action, highlight=False)
            cli.console.print("Completion command: " + (
                f"honeyguider done {task.id}" if directory is None else
                f"honeyguider track --state-dir {shlex.quote(str(directory))} done {task.id}"
            ), highlight=False, soft_wrap=True)
        else:
            cli.console.print("All required tasks complete." if finished else
                              "No actionable task. View progress for blockers; run honeyguider check to refresh demo tool checks.")
        choice = choose("Plan", {"1": "Full next-task details and citations", "2": "Progress and blockers",
                                 "3": "All task details" if directory else "Demo command help", "0": "Back"})
        if choice == "0":
            return
        if directory is not None:
            group, child = track_context(ctx, directory, {"1": "next", "2": "status", "3": "show"}[choice])
            with child:
                group.invoke(child)
        elif choice == "1":
            ctx.invoke(cli.next_command, ctx=ctx)
        elif choice == "2":
            ctx.invoke(cli.status, ctx=ctx)
        else:
            cli.console.print("explore --demo: initialize/resume; check: inspect tool versions; next: details and citations; done TASK_ID: record completion; status: blockers")
            cli.console.print("Put --state-file PATH before the command when using custom demo storage.")


def documentation(ctx: typer.Context):
    cli.console.print("Research retrieves public HTTPS documentation. Plans use a deterministic demonstration provider; they are not inferred requirements or saved tracking plans.")
    choice = choose("Documentation", {"1": "Research excerpts", "2": "Prepare a demonstration development plan", "0": "Back"})
    if choice == "0":
        return
    url = typer.prompt("Documentation HTTPS URL").strip()
    goal = typer.prompt("Development goal").strip()
    if not url or not goal:
        cli.console.print("URL and goal must be non-empty. Returning to welcome.")
        return
    if typer.confirm("Retrieve documentation over the network now?", default=False):
        if choice == "1":
            ctx.invoke(cli.research, url=url, goal=goal)
        else:
            ctx.invoke(cli.plan, ctx=ctx, url=url, goal=goal)


def welcome(ctx: typer.Context):
    cli.console.print("Honeyguider", style="bold")
    cli.console.print("Choose a starting point. Opening this menu is offline and does not change progress.")
    try:
        while True:
            choice = choose("Welcome", {
                "1": "Explore the deterministic offline demo",
                "2": "Research documentation / prepare a development plan",
                "3": "Resume a local plan / view progress",
                "4": "Command help", "0": "Exit",
            })
            if choice == "0":
                return
            if choice == "1":
                state = cli.read(ctx) if ctx.obj.exists() else fresh_state()
                cli.write(ctx, state)
                cli.console.print("Celo practice fixture; not verified event requirements. Existing progress preserved.")
                session(ctx)
            elif choice == "2":
                documentation(ctx)
            elif choice == "3":
                kind = choose("Resume", {"1": "Offline demo (selected --state-file)", "2": "Previously imported tracked plan", "0": "Back"})
                if kind == "1":
                    session(ctx)
                elif kind == "2":
                    directory = Path(typer.prompt("Tracking directory", default=".honeyguider/track")).expanduser()
                    session(ctx, directory)
            else:
                cli.console.print(ctx.get_help())
    except (typer.Abort, KeyboardInterrupt, EOFError):
        cli.console.print("Navigation cancelled.")
