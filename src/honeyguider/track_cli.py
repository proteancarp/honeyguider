"""Opt-in local AI plan tracking commands."""
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from . import tracking
from .planning import next_action, task_state, validate_completed

app = typer.Typer(no_args_is_help=True, help="Track an existing AI receipt offline; nothing is executed.")
console = Console(markup=False)


@contextmanager
def boundary():
    try:
        yield
    except tracking.ERRORS as exc:
        # Avoid echoing private receipt content or untrusted JSON keys.
        console.print(f"Cannot track plan ({type(exc).__name__}). Check private files, receipt validity, task IDs and prerequisites; existing state is preserved.")
        raise typer.Exit(1) from exc


@app.callback()
def main(ctx: typer.Context,
         state_dir: Annotated[Path, typer.Option('--state-dir', help='Separate private tracking directory; import requires a new path.')] = Path('.honeyguider/track')):
    demo = ctx.find_root().obj
    # Prevent tracking storage from enclosing or aliasing the selected demo file.
    if demo is not None and (state_dir.resolve() == demo.resolve()
                             or state_dir.resolve() in demo.resolve().parents):
        console.print('Tracking directory must be separate from demo state.')
        raise typer.Exit(2)
    ctx.obj = state_dir


def display(task, completed):
    console.print(f'{task.id}: {task.title} [{task.classification}; {task_state(task, completed)}]')
    console.print(f'Action: {task.action}', highlight=False)
    console.print(f"Prerequisites: {', '.join(task.prerequisites) or 'none'}")
    for source in task.sources:
        console.print(f'Source: {source}', highlight=False)


def read(ctx):
    state = tracking.load(ctx.obj)
    return state, tracking.validate(state), frozenset(state['completed'])


@app.command(name='import')
def import_command(ctx: typer.Context,
                   receipt_dir: Annotated[Path, typer.Option('--receipt-dir')]):
    """Revalidate a successful private inference receipt without network access."""
    with boundary():
        tracking.import_receipt(receipt_dir, ctx.obj)
    console.print('Imported AI plan. Unverified recommendations; completion is self-reported. Nothing is executed.')


@app.command()
def show(ctx: typer.Context):
    """Show every task, dependency, action, citation and completion state."""
    with boundary():
        _, plan, completed = read(ctx)
        console.print('AI-generated plan: unverified recommendations; nothing is executed.')
        for task in plan.tasks:
            display(task, completed)


@app.command(name='next')
def next_command(ctx: typer.Context):
    """Show the next required task or a prerequisite needed by required work."""
    with boundary():
        _, plan, completed = read(ctx)
        if all(task.id in completed for task in plan.tasks if task.classification == 'required'):
            console.print('All required tasks complete. Optional work remains visible in track show.')
            return
        task = next_action(plan, completed)
        if task:
            display(task, completed)


@app.command()
def done(ctx: typer.Context, task_id: str):
    """Record self-reported completion only after all prerequisites are complete."""
    with boundary():
        state, plan, _ = read(ctx)
        validate_completed(plan, state['completed'] + [task_id])
        state['completed'].append(task_id)
        state['revision'] += 1
        tracking.append(ctx.obj, state)
    console.print(f'Completed: {task_id} (self-reported)')


@app.command()
def status(ctx: typer.Context):
    """Show required and overall progress, including blockers."""
    with boundary():
        _, plan, completed = read(ctx)
        required = [task for task in plan.tasks if task.classification == 'required']
        console.print(f'Required: {sum(task.id in completed for task in required)}/{len(required)} complete; total: {len(completed)}/{len(plan.tasks)} complete (self-reported)')
        for task in plan.tasks:
            missing = [dep for dep in task.prerequisites if dep not in completed]
            console.print(f"{task.id}: {task_state(task, completed)}; blockers: {', '.join(missing) or 'none'}")
