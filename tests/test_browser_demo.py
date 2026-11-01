"""Offline adapter tests; exercise the real retrieval and planning boundaries."""
import asyncio
from pathlib import Path
import subprocess
import sys
from unittest.mock import AsyncMock

import httpx
import pytest

from honeyguider import browser_demo as demo, research
from honeyguider.planning import build_plan, next_action


def test_default_capture_uses_actual_extractor_and_planner(monkeypatch):
    monkeypatch.setattr(demo, "research", AsyncMock(side_effect=AssertionError("network")))
    result = demo.run_demo(demo.DEFAULT_URL, demo.DEFAULT_GOAL, offline=True)
    assert result.plan == build_plan(result.report, demo.DEFAULT_GOAL)
    assert next_action(result.plan, frozenset()).id == "review-1"
    assert result.report.requests == 0
    assert all(task.sources == (demo.DEFAULT_URL,) for task in result.plan.tasks)
    # The shipped offline excerpts are verbatim paragraphs from the existing capture.
    original = (Path(__file__).parent / "fixtures/celo_8004_mdx.html").read_bytes()
    page = research.extract(original, demo.DEFAULT_URL, demo.DEFAULT_GOAL)
    original_texts = {b["text"] for s in page.sections for b in s["blocks"]}
    assert all(b["text"] in original_texts for s in result.report.pages[0].sections for b in s["blocks"])


@pytest.mark.parametrize("url,goal", [
    ("https://localhost", "install"), ("https://user:secret@example.com", "install"),
    (demo.DEFAULT_URL, ""), (demo.DEFAULT_URL, "x" * 1001),
    ("https://docs.example.com/", demo.DEFAULT_GOAL),
])
def test_invalid_offline_input_never_retrieves(monkeypatch, url, goal):
    retrieve = AsyncMock()
    monkeypatch.setattr(demo, "research", retrieve)
    with pytest.raises(ValueError):
        demo.run_demo(url, goal, offline=True)
    retrieve.assert_not_called()


def test_no_relevant_evidence_has_no_plan():
    result = demo.run_demo(demo.DEFAULT_URL, "quuxxyz", offline=True)
    assert result.plan is None
    assert "No relevant" in result.planning_error


def test_live_adapter_uses_real_bounded_retrieval_with_partial_failure(monkeypatch):
    calls = []

    def handler(request):
        calls.append(request)
        if request.url.path != "/start":
            return httpx.Response(503)
        return httpx.Response(200, headers={"content-type": "text/html"}, stream=httpx.ByteStream(b'<h2>Install package</h2><p>Install a package in a project.</p><a href="/package-install">Install package</a>'))

    monkeypatch.setattr(research, "resolve", AsyncMock(return_value=["93.184.216.34"]))

    async def retrieve(url, goal):
        return await research.research(url, goal, transport=httpx.MockTransport(handler))

    monkeypatch.setattr(demo, "research", retrieve)
    result = demo.run_demo("https://docs.example.com/start", "install package", offline=False)
    assert result.plan is not None and result.report.errors
    assert result.report.requests == len(calls) == 2
    assert all(task.sources == ("https://docs.example.com/start",) for task in result.plan.tasks)


def test_live_deadline_is_a_report_not_an_exception(monkeypatch):
    async def stalled(host):
        await asyncio.sleep(1)

    monkeypatch.setattr(research, "TOTAL_SECONDS", 0.01)
    monkeypatch.setattr(research, "resolve", stalled)
    result = demo.run_demo(demo.DEFAULT_URL, demo.DEFAULT_GOAL, offline=False)
    assert result.plan is None
    assert "deadline" in result.report.errors[0]


def test_browser_adapter_import_does_not_load_private_workflows():
    result = subprocess.run([sys.executable, "-c", "import sys; import honeyguider.browser_demo; assert not any('honeyguider.' + name in sys.modules for name in ['cli', 'paid', 'cencori', 'tracking', 'track_cli', 'state', 'checks'])"], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
