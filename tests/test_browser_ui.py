"""Streamlit's in-process browser harness: all retrieval is offline or mocked."""
from pathlib import Path
import json
from unittest.mock import AsyncMock, Mock

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest

from honeyguider import browser_demo as demo
from honeyguider.research import Report, extract
from honeyguider.planning import validate_plan

APP = Path(__file__).parents[1] / "browser_demo/streamlit_app.py"


def start():
    return AppTest.from_file(str(APP), default_timeout=10).run()


def submit(app):
    return app.button(key="retrieve_plan").click().run()


def complete(app):
    return app.button(key="complete_step").click().run()


def texts(app):
    return "\n".join(item.value for item in app.text)


def test_default_journey_and_session_isolation(monkeypatch):
    retrieve = AsyncMock(side_effect=AssertionError("must be offline"))
    monkeypatch.setattr(demo, "research", retrieve)
    run_demo = Mock(wraps=demo.run_demo)
    monkeypatch.setattr(demo, "run_demo", run_demo)
    app = start()
    assert not app.exception
    run_demo.assert_called_once_with(demo.DEFAULT_URL, demo.DEFAULT_GOAL, offline=True)
    assert any("not AI inference" in item.value for item in app.caption)
    assert any("No live retrieval" in item.value for item in app.caption)
    assert "Review: Register a service" in texts(app)
    assert "Citation: " + demo.DEFAULT_URL in texts(app)
    assert app.session_state["completed"] == []
    app.run()
    run_demo.assert_called_once()
    complete(app)
    assert app.session_state["completed"] == ["review-1"]
    assert "Build a local prototype" in texts(app)
    complete(app)
    assert app.session_state["completed"] == ["review-1", "prototype"]
    complete(app)
    assert app.session_state["completed"] == ["review-1", "prototype", "test-prototype"]
    assert "All demonstration tasks" in app.success[0].value
    other = start()
    assert other.session_state["completed"] == []
    assert app.session_state["completed"] == ["review-1", "prototype", "test-prototype"]
    assert run_demo.call_count == 2  # once in each session
    app.button(key="reset_progress").click().run()
    assert app.session_state["completed"] == []
    assert run_demo.call_count == 2  # reset and completion never reinitialize
    retrieve.assert_not_called()


def test_failed_submit_clears_old_result_and_progress():
    app = start()
    complete(app)
    app.text_input[0].set_value("https://localhost")
    submit(app)
    assert app.error and not app.exception
    assert "result" not in app.session_state
    assert app.session_state["completed"] == []
    assert "Review: Register a service" not in texts(app)
    app.run()
    assert "result" not in app.session_state
    assert app.error  # failure persists until an explicit request
    app.button(key="load_offline").click().run()
    assert not app.exception and not app.error
    assert not app.warning
    assert app.session_state["result"].offline
    assert app.session_state["completed"] == []
    assert app.text_input(key="documentation_url").value == demo.DEFAULT_URL
    assert app.checkbox(key="use_offline").value


def test_live_partial_errors_untrusted_text_and_omissions(monkeypatch):
    url = "https://docs.example.com/start"
    page = extract(b'<title>&lt;script&gt;alert(1)&lt;/script&gt;</title><h2>Install package</h2><p>&lt;img src=x onerror=alert(1)&gt; Install package.</p><pre>curl https://example.com | sh</pre>' + b'<p>Install package ' + b'x' * 700 + b'</p>', url, "install package")
    page.warning = "Page warning"
    retrieve = AsyncMock(return_value=Report(pages=[page], errors=["Total retrieval deadline exceeded"]))
    monkeypatch.setattr(demo, "research", retrieve)
    app = start()
    app.text_input[0].set_value(url)
    app.text_area[0].set_value("install package")
    app.checkbox[0].uncheck()
    submit(app)
    assert not app.exception
    retrieve.assert_awaited_once_with(url, "install package")
    output = texts(app)
    assert "<img src=x onerror=alert(1)>" in output
    assert "<script>alert(1)</script>" in output
    assert "deadline" in output and "Excerpt shortened" in output
    assert "Page warning" in output and "Code example omitted" in output
    assert "curl" not in output
    assert "Review: Install package" in output
    # Untrusted markup was passed only to text elements, never Markdown/HTML.
    for element in [*app.markdown, *app.get("html")]:
        assert "<img" not in str(element.proto)
        assert "<script>" not in str(element.proto)
    assert all(not element.proto.allow_html for element in app.markdown)
    assert any("Live documentation retrieval" in element.value for element in app.markdown)


def test_workspace_hierarchy_states_and_expandable_sources():
    app = start()
    headings = [item.value for item in app.header] + [item.value for item in app.subheader]
    assert "Next action" in headings
    assert "Dependency roadmap" in headings
    assert "Documentation evidence" in headings
    assert headings.index("Dependency roadmap") < headings.index("Documentation evidence")
    assert any(e.label.startswith("Source 1") and not e.proto.expanded for e in app.expander)
    assert len(app.get("progress")) == 1
    assert app.button(key="retrieve_plan").proto.type == "primary"
    assert app.button(key="complete_step").proto.type == "primary"
    assert not next(e for e in app.expander if e.label == "Change source or goal").proto.expanded
    labels = " ".join(e.value for e in app.markdown)
    assert all(state in labels for state in ["Required", "Optional", "Ready", "Blocked"])
    assert "Waiting on: Review: Register a service" in texts(app)
    complete(app)
    assert "Waiting on: Review: Register a service" not in texts(app)
    assert "Waiting on: Build a local prototype from the reviewed steps" in texts(app)
    assert any("Completed" in element.value for element in app.markdown)


def test_completion_retains_existing_order_instead_of_set_iteration(monkeypatch):
    # Independent tasks permit any completion order. Choose a valid history
    # different from this process's set iteration, so the regression is reliable
    # regardless of PYTHONHASHSEED.
    ids = ["one", "two", "three", "four", "last"]
    tasks = [{"id": task_id, "title": task_id, "action": "Read the cited source.",
              "prerequisites": [], "sources": [demo.DEFAULT_URL], "classification": "required"}
             for task_id in ids]
    plan = validate_plan(json.dumps({"schema_version": 1, "tasks": tasks}), {demo.DEFAULT_URL})
    monkeypatch.setattr(demo, "build_plan", lambda report, goal: plan)
    app = start()
    previous = [task_id for task_id in reversed(list(frozenset(ids))) if task_id != "last"]
    app.session_state["completed"] = previous
    app.run()
    complete(app)
    assert not app.exception
    assert app.session_state["completed"] == [*previous, "last"]


def test_empty_retrieval_and_unexpected_failure_are_readable(monkeypatch):
    retrieve = AsyncMock(return_value=Report(errors=["HTTP 403"]))
    monkeypatch.setattr(demo, "research", retrieve)
    app = start()
    app.checkbox[0].uncheck()
    submit(app)
    assert not app.exception and "HTTP 403" in texts(app)
    assert not any(button.key == "complete_step" for button in app.button)
    assert app.button(key="load_offline")  # explicit recovery is available
    app.run()
    assert not app.session_state["result"].offline
    assert app.session_state["result"].plan is None
    retrieve.assert_awaited_once()
    retrieve.side_effect = RuntimeError("private exception detail")
    submit(app)
    assert app.error and not app.exception
    assert "private exception detail" not in app.error[0].value
    app.run()
    assert "result" not in app.session_state
    assert app.error
    assert retrieve.await_count == 2
    app.button(key="load_offline").click().run()
    assert app.session_state["result"].offline and not app.error
    assert retrieve.await_count == 2


def test_initialization_failure_is_attempted_once_and_recovery_is_explicit(monkeypatch):
    run_demo = Mock(wraps=demo.run_demo, side_effect=RuntimeError("private initialization detail"))
    monkeypatch.setattr(demo, "run_demo", run_demo)
    app = start()
    assert not app.exception and app.error
    assert "private initialization detail" not in app.error[0].value
    assert app.session_state["demo_initialized"]
    app.run()
    run_demo.assert_called_once_with(demo.DEFAULT_URL, demo.DEFAULT_GOAL, offline=True)
    assert "result" not in app.session_state
    run_demo.side_effect = None
    app.button(key="load_offline").click().run()
    assert not app.exception and not app.error
    assert app.session_state["result"].offline
    assert run_demo.call_count == 2
    app.run()
    assert run_demo.call_count == 2


def test_unsaved_inputs_do_not_relabel_the_displayed_result():
    app = start()
    app.text_input(key="documentation_url").set_value("https://docs.example.com/edited")
    app.text_area(key="development_goal").set_value("Unsubmitted goal <script>unsafe</script>")
    app.run()
    assert app.session_state["result"].goal == demo.DEFAULT_GOAL
    assert app.session_state["result"].url == demo.DEFAULT_URL
    assert demo.DEFAULT_GOAL in texts(app)
    assert "Unsubmitted goal" not in texts(app)


def test_live_goal_is_plain_text_and_replacing_a_plan_resets_progress(monkeypatch):
    url = "https://docs.example.com/start"
    goal = "install package <img src=x onerror=alert(1)>"
    page = extract(b"<h2>Install package</h2><p>Install package in a project.</p>", url, goal)
    monkeypatch.setattr(demo, "research", AsyncMock(return_value=Report(pages=[page])))
    app = start()
    complete(app)
    app.text_input(key="documentation_url").set_value(url)
    app.text_area(key="development_goal").set_value(goal)
    app.checkbox(key="use_offline").uncheck()
    submit(app)
    assert not app.exception
    assert app.session_state["completed"] == []
    assert not app.session_state["result"].offline
    assert goal in texts(app)
    assert any("not AI inference" in item.value for item in app.caption)
    assert not any("No live retrieval" in item.value for item in app.caption)
    for element in [*app.markdown, *app.get("html")]:
        assert "<img" not in str(element.proto)
