"""Versioned JSON state with validation and atomic replacement."""
import json
import os
from pathlib import Path
import tempfile

from .demo import TASKS


class StateError(ValueError):
    pass


def fresh_state() -> dict:
    return {"schema_version": 1, "plan": "celo-demo", "completed": [], "checks": {}}


def load(path: Path) -> dict:
    try:
        state = json.loads(path.read_text())
        if not isinstance(state, dict) or state.get("schema_version") != 1 or state.get("plan") != "celo-demo":
            raise ValueError("Unsupported state format")
        completed, checks = state["completed"], state["checks"]
        ids = {t.id for t in TASKS}
        if not isinstance(completed, list) or any(not isinstance(i, str) or i not in ids for i in completed) or len(set(completed)) != len(completed):
            raise ValueError("Invalid completed tasks")
        if any(t.id in completed and any(p not in completed for p in t.prerequisites) for t in TASKS):
            raise ValueError("Completed tasks have unfinished prerequisites")
        if not isinstance(checks, dict) or any(k not in {"python", "git", "node", "npm"} or not isinstance(v, dict) or type(v.get("available")) is not bool or not isinstance(v.get("version"), str) or not isinstance(v.get("detail"), str) for k, v in checks.items()):
            raise ValueError("Invalid environment checks")
        return state
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise StateError(f"Cannot read state at {path}: {exc}") from exc


def save(path: Path, state: dict) -> None:
    temporary = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as handle:
            temporary = handle.name
            json.dump(state, handle, indent=2)
            handle.write("\n")
        os.replace(temporary, path)
    except OSError as exc:
        raise StateError(f"Cannot save state at {path}: {exc}") from exc
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)
