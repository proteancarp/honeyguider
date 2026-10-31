"""Small, dependency-aware plan model."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Task:
    id: str
    title: str
    action: str
    prerequisites: tuple[str, ...] = ()
    tools: tuple[str, ...] = ()
    sources: tuple[str, ...] = ()


def blockers(task: Task, completed: list[str], checks: dict) -> list[str]:
    return [f"task:{p}" for p in task.prerequisites if p not in completed] + [
        f"tool:{tool} (run check)" for tool in task.tools
        if checks.get(tool, {}).get("available") is not True
    ]


def next_task(tasks: tuple[Task, ...], completed: list[str], checks: dict) -> Task | None:
    return next((t for t in tasks if t.id not in completed and not blockers(t, completed, checks)), None)
