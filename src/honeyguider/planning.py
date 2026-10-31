"""Strict, in-memory dependency plans. Providers return data, never executable code."""
from dataclasses import dataclass
import json
import re
from typing import Protocol
import unicodedata

from .research import Report, clean

MAX_TASKS = 20
MAX_RESPONSE_BYTES = 64 * 1024


class PlanError(ValueError):
    """Invalid provider output, insufficient evidence, or invalid completion data."""


@dataclass(frozen=True)
class PlanTask:
    id: str
    title: str
    action: str
    prerequisites: tuple[str, ...]
    sources: tuple[str, ...]
    classification: str


@dataclass(frozen=True)
class Plan:
    schema_version: int
    tasks: tuple[PlanTask, ...]


class PlanningProvider(Protocol):
    def generate(self, evidence: Report, goal: str) -> str:
        """Return a JSON plan; callers must validate it before using it."""
        ...


def _text(value: object, limit: int, field: str) -> str:
    if (not isinstance(value, str) or not value.strip() or len(value) > limit
            or any(unicodedata.category(c).startswith("C") for c in value)):
        raise PlanError(f"Invalid {field}: expected nonempty text of at most {limit} characters without controls")
    return value


def _strings(value: object, limit: int, field: str, text_limit: int) -> list[str]:
    if not isinstance(value, list) or len(value) > limit:
        raise PlanError(f"Invalid {field} list")
    result = [_text(item, text_limit, field) for item in value]
    if len(result) != len(set(result)):
        raise PlanError(f"Duplicate {field}")
    return result


def _object(pairs: list[tuple]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise PlanError(f"Duplicate JSON field: {key}")
        result[key] = value
    return result


def validate_plan(response: str, retrieved_urls: set[str]) -> Plan:
    """Reject malformed JSON, invalid graphs and citations outside the evidence."""
    if not isinstance(response, str) or len(response) > MAX_RESPONSE_BYTES:
        raise PlanError("Provider response must be bounded JSON text")
    try:
        if len(response.encode("utf-8")) > MAX_RESPONSE_BYTES:
            raise PlanError("Provider response exceeds byte limit")
        data = json.loads(response, object_pairs_hook=_object)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise PlanError(f"Malformed provider response: {exc}") from exc
    if not isinstance(data, dict) or set(data) != {"schema_version", "tasks"}:
        raise PlanError("Plan must contain exactly schema_version and tasks")
    if type(data["schema_version"]) is not int or data["schema_version"] != 1:
        raise PlanError("Unsupported plan schema version")
    raw_tasks = data["tasks"]
    if not isinstance(raw_tasks, list) or not 1 <= len(raw_tasks) <= MAX_TASKS:
        raise PlanError(f"Plan must contain 1 to {MAX_TASKS} tasks")
    tasks = []
    for raw in raw_tasks:
        if not isinstance(raw, dict) or set(raw) != {"id", "title", "action", "prerequisites", "sources", "classification"}:
            raise PlanError("Task has missing or unknown fields")
        task_id = _text(raw["id"], 40, "task ID")
        if not re.fullmatch(r"[a-z][a-z0-9-]*", task_id):
            raise PlanError("Task IDs must use lowercase letters, digits and hyphens")
        title = _text(raw["title"], 160, "title")
        action = _text(raw["action"], 1200, "action")
        prerequisites = _strings(raw["prerequisites"], MAX_TASKS - 1, "prerequisites", 40)
        sources = _strings(raw["sources"], 3, "sources", 4096)
        if not sources or any(source not in retrieved_urls for source in sources):
            raise PlanError("Each task needs citations to actually retrieved page URLs")
        if raw["classification"] not in ("required", "optional"):
            raise PlanError("Classification must be required or optional")
        tasks.append(PlanTask(task_id, title, action, tuple(prerequisites), tuple(sources), raw["classification"]))
    by_id = {task.id: task for task in tasks}
    if len(by_id) != len(tasks):
        raise PlanError("Duplicate task IDs")
    for task in tasks:
        if task.id in task.prerequisites:
            raise PlanError("Self-dependency")
        if any(dep not in by_id for dep in task.prerequisites):
            raise PlanError("Unknown dependency")
    visited, active = set(), set()

    def visit(task_id: str):
        if task_id in active:
            raise PlanError("Dependency cycle")
        if task_id not in visited:
            active.add(task_id)
            for dep in by_id[task_id].prerequisites:
                visit(dep)
            active.remove(task_id)
            visited.add(task_id)

    for task in tasks:
        visit(task.id)
    return Plan(1, tuple(tasks))


def validate_completed(plan: Plan, completed: list[str]) -> frozenset[str]:
    if len(completed) != len(set(completed)):
        raise PlanError("Duplicate completed task IDs")
    done = frozenset(completed)
    if done - {task.id for task in plan.tasks}:
        raise PlanError("Unknown completed task ID")
    if any(task.id in done and not set(task.prerequisites) <= done for task in plan.tasks):
        raise PlanError("Completed task has unfinished prerequisites")
    return done


def task_state(task: PlanTask, completed: frozenset[str]) -> str:
    if task.id in completed:
        return "completed"
    return "ready" if set(task.prerequisites) <= completed else "blocked"


def next_action(plan: Plan, completed: frozenset[str]) -> PlanTask | None:
    """Prefer required work and its prerequisites; optional-only work comes last."""
    by_id = {task.id: task for task in plan.tasks}
    needed = set()

    def require(task_id):
        if task_id not in needed and task_id not in completed:
            needed.add(task_id)
            for dep in by_id[task_id].prerequisites:
                require(dep)

    for task in plan.tasks:
        if task.classification == "required":
            require(task.id)
    ready = [task for task in plan.tasks if task_state(task, completed) == "ready"]
    return next((task for task in ready if task.id in needed), ready[0] if ready else None)


class FixtureProvider:
    """Authored demonstration scaffold, not inferred technical requirements."""

    def generate(self, evidence: Report, goal: str) -> str:
        tasks = []
        seen = set()
        for page in evidence.pages:
            for section in page.sections:
                heading = section["heading"]
                key = (page.url, heading)
                if key in seen:
                    continue
                seen.add(key)
                task_id = f"review-{len(tasks) + 1}"
                tasks.append({"id": task_id, "title": f"Review: {clean(heading)[:140]}",
                              "action": f"Read the retrieved passage titled '{clean(heading)[:200]}' at the cited URL. Record its stated prerequisites and ordered steps in local project notes; check truncation and omissions against the source before implementing anything.",
                              "prerequisites": [tasks[-1]["id"]] if tasks else [],
                              "sources": [page.url], "classification": "required"})
                if len(tasks) == MAX_TASKS - 2:
                    break
            if len(tasks) == MAX_TASKS - 2:
                break
        if not tasks:
            raise PlanError("No relevant retrieved sections; cannot build an evidence-linked plan")
        source = tasks[0]["sources"]
        tasks.append({"id": "prototype", "title": "Build a local prototype from the reviewed steps",
                      "action": f"Write a minimal local prototype for this goal: {clean(goal)[:400]}. Use the reviewed notes to choose the implementation steps and record unresolved questions. Do not execute copied documentation commands automatically.",
                      "prerequisites": [tasks[-1]["id"]], "sources": source, "classification": "required"})
        tasks.append({"id": "test-prototype", "title": "Add an offline regression test",
                      "action": "Write and manually run an offline test for the prototype's expected input and output; record the actual result in project notes.",
                      "prerequisites": ["prototype"], "sources": source, "classification": "optional"})
        return json.dumps({"schema_version": 1, "tasks": tasks})


def build_plan(evidence: Report, goal: str, provider: PlanningProvider | None = None) -> Plan:
    """Single validation boundary shared by fixture and future provider adapters."""
    _text(goal, 1000, "goal")
    if not evidence.pages:
        raise PlanError("No retrieved pages; cannot plan")
    retrieved_urls = {page.url for page in evidence.pages}
    response = (provider or FixtureProvider()).generate(evidence, goal)
    return validate_plan(response, retrieved_urls)
