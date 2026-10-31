import json
import subprocess
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from pathf1ndar.cli import app
from pathf1ndar.checks import inspect_environment
from pathf1ndar.demo import TASKS
from pathf1ndar.model import next_task
from pathf1ndar.state import StateError, fresh_state, load, save


runner = CliRunner()


def tools_ok():
    return {name: {"available": True, "version": "fixture", "detail": "mock"} for name in ("python", "git", "node", "npm")}


def test_dependency_selection():
    assert next_task(TASKS, [], {}).id == "scope"
    assert next_task(TASKS, ["scope"], {}) is None
    assert next_task(TASKS, ["scope"], tools_ok()).id == "workspace"
    assert next_task(TASKS, [t.id for t in TASKS], tools_ok()) is None


def test_cli_full_journey(tmp_path):
    path = tmp_path / "state.json"
    def invoke(*args):
        return runner.invoke(app, ["--state-file", str(path), *args])
    assert invoke("status").exit_code == 1
    assert invoke("explore").exit_code == 2
    assert invoke("explore", "--demo").exit_code == 0
    assert invoke("done", "workspace").exit_code == 1
    assert invoke("done", "bogus").exit_code == 2
    assert "scope:" in invoke("next").output
    assert invoke("done", "scope").exit_code == 0
    assert "No actionable task" in invoke("next").output
    assert invoke("explore", "--demo").exit_code == 0
    assert load(path)["completed"] == ["scope"]
    with patch("pathf1ndar.cli.inspect_environment", return_value=tools_ok()):
        assert invoke("check").exit_code == 0
    for task in TASKS[1:]:
        assert f"{task.id}:" in invoke("next").output
        assert invoke("done", task.id).exit_code == 0
    assert "All tasks complete" in invoke("next").output
    assert "5/5 complete" in invoke("status").output
    assert "Already complete" in invoke("done", "scope").output
    assert len(load(path)["completed"]) == 5


def test_state_roundtrip_and_corruption(tmp_path):
    path = tmp_path / "nested" / "state.json"
    save(path, fresh_state())
    assert load(path) == fresh_state()
    path.write_text("broken")
    with pytest.raises(StateError):
        load(path)
    result = runner.invoke(app, ["--state-file", str(path), "explore", "--demo"])
    assert result.exit_code == 1
    assert path.read_text() == "broken"


@pytest.mark.parametrize("change", [{"schema_version": 99}, {"completed": ["unknown"]}, {"completed": ["workspace"]}, {"checks": {"node": {"available": "yes"}}}])
def test_invalid_state(tmp_path, change):
    state = fresh_state() | change
    path = tmp_path / "state.json"
    path.write_text(json.dumps(state))
    with pytest.raises(StateError):
        load(path)


def test_missing_tools():
    with patch("pathf1ndar.checks.shutil.which", return_value=None), patch("pathf1ndar.checks.subprocess.run") as run:
        results = inspect_environment()
    run.assert_not_called()
    assert results["python"]["available"] is True
    assert all(results[t]["available"] is False for t in ("git", "node", "npm"))


def test_fixed_commands_and_failures():
    with patch("pathf1ndar.checks.shutil.which", side_effect=lambda name: f"/usr/bin/{name}"), patch("pathf1ndar.checks.subprocess.run", side_effect=[subprocess.CompletedProcess([], 0, "git version fixture", ""), subprocess.TimeoutExpired("node", 5), subprocess.CompletedProcess([], 1, "", "failed")]) as run:
        results = inspect_environment()
    assert results["git"]["available"]
    assert not results["node"]["available"]
    assert not results["npm"]["available"]
    assert [call.args[0] for call in run.call_args_list] == [[f"/usr/bin/{name}", "--version"] for name in ("git", "node", "npm")]
    assert all(call.kwargs["shell"] is False and call.kwargs["timeout"] == 5 for call in run.call_args_list)


def test_failed_check_is_persisted(tmp_path):
    path = tmp_path / "state.json"
    save(path, fresh_state())
    checks = tools_ok()
    checks["node"]["available"] = False
    with patch("pathf1ndar.cli.inspect_environment", return_value=checks):
        result = runner.invoke(app, ["--state-file", str(path), "check"])
    assert result.exit_code == 1
    assert load(path)["checks"]["node"]["available"] is False
