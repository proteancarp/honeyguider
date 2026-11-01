"""Read-only browser adapter; no CLI, payment, environment or tracking imports."""
import asyncio
from dataclasses import dataclass
from importlib.resources import files

from .planning import Plan, PlanError, build_plan
from .research import Report, extract, research, safe_url, terms

DEFAULT_URL = "https://docs.celo.org/build/agents/8004"
DEFAULT_GOAL = "Register an ERC-8004 agent on Celo"


@dataclass(frozen=True)
class DemoResult:
    url: str
    goal: str
    offline: bool
    report: Report
    plan: Plan | None
    planning_error: str = ""


def run_demo(url: str, goal: str, *, offline: bool) -> DemoResult:
    """Reuse bounded retrieval and the planner's strict validation boundary."""
    url, goal = url.strip(), goal.strip()
    # Validate before any network access; the planner also validates the goal.
    safe_url(url)
    if not goal or len(goal) > 1000 or not terms(goal):
        raise PlanError("Enter a searchable development goal of at most 1000 characters.")
    if offline:
        if url != DEFAULT_URL:
            raise PlanError("The offline capture is available only for the default documentation URL. Select live retrieval for another URL.")
        body = files("honeyguider").joinpath("browser_example.html").read_bytes()
        report = Report(pages=[extract(body, DEFAULT_URL, goal)])
    else:
        report = asyncio.run(research(url, goal))
    try:
        plan = build_plan(report, goal)
    except PlanError as exc:
        return DemoResult(url, goal, offline, report, None, str(exc))
    return DemoResult(url, goal, offline, report, plan)
