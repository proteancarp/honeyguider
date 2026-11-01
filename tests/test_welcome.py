"""Deterministic navigation tests; no real network, tools or paid operations."""
import os.path
from pathlib import Path
import shlex
import socket
import subprocess
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from typer.testing import CliRunner

from honeyguider import cencori, cli, paid, tracking, welcome
from honeyguider.research import Report, extract
from honeyguider.state import fresh_state, load, save

terminal_detector = welcome.interactive_terminal


@pytest.fixture(autouse=True)
def offline_terminal(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(welcome, "interactive_terminal", lambda: True)

    def forbidden(*args, **kwargs):
        pytest.fail("Navigation attempted external I/O or payment")

    for target, name in [(socket, "getaddrinfo"), (socket, "create_connection"),
                         (subprocess, "run"), (subprocess, "Popen"),
                         (httpx.Client, "send"), (httpx.AsyncClient, "send"),
                         (paid, "infer"), (paid, "wallet_environment"),
                         (paid, "supervise"), (cencori, "_run")]:
        monkeypatch.setattr(target, name, forbidden)


def invoke(text="", args=()):
    return CliRunner().invoke(cli.app, list(args), input=text)


def test_welcome_help_exit_do_not_create_state(tmp_path):
    result = invoke("4\n0\n")
    assert result.exit_code == 0, result.output
    for command in ("explore", "research", "plan", "track", "check", "next", "done", "status"):
        assert command in result.output
    assert not (tmp_path / ".pathf1ndar").exists()
    assert not (tmp_path / ".honeyguider").exists()


def test_demo_navigation_and_full_citations(tmp_path):
    state = tmp_path / "custom.json"
    result = invoke("1\n1\n2\n3\n0\n0\n", ("--state-file", str(state)))
    assert result.exit_code == 0, result.output
    assert "Next action: scope:" in result.output
    assert "Documentation reference (not fetched): https://docs.celo.org/" in result.output
    assert "0/5 complete" in result.output
    assert load(state) == fresh_state()
    compact = invoke("1\n0\n0\n", ("--state-file", str(state)))
    assert "Next action: scope:" in compact.output
    assert "Documentation reference" not in compact.output
    assert "prototype:" not in compact.output


def test_resume_preserves_state_and_shows_blockers(tmp_path):
    state = tmp_path / "progress.json"
    save(state, fresh_state() | {"completed": ["scope"]})
    before = state.read_bytes()
    result = invoke("3\n1\n2\n0\n0\n", ("--state-file", str(state)))
    assert result.exit_code == 0, result.output
    assert "No actionable task" in result.output
    assert "1/5 complete" in result.output
    assert state.read_bytes() == before


@pytest.mark.parametrize("directory_name", ["private-plan", "private plan", "plan's $(not-run); [draft]"])
@pytest.mark.parametrize("use_home", [False, True])
def test_resume_tracked_plan(tmp_path, directory_name, use_home):
    directory = tmp_path / directory_name
    directory.mkdir(mode=0o700)
    url = "https://docs.example.com/"
    state = {"schema_version": 1, "revision": 0, "receipt": str(tmp_path / "missing-receipt"),
             "request_sha256": "a" * 64, "completion_sha256": "b" * 64,
             "sources": [url], "completed": [], "plan": {"schema_version": 1, "tasks": [
                 {"id": "review", "title": "Review docs", "action": "Read the source.",
                  "prerequisites": [], "sources": [url], "classification": "required"}]}}
    tracking.append(directory, state)
    before = (directory / "000000.json").read_bytes()
    # Reach only the temporary fixture via ~, without changing the real home.
    entered = "~/" + os.path.relpath(directory, Path.home()) if use_home else str(directory)
    selected = Path.home() / os.path.relpath(directory, Path.home()) if use_home else directory
    result = invoke(f"3\n2\n{entered}\n1\n2\n3\n0\n0\n")
    assert result.exit_code == 0, result.output
    assert "Next action: review: Review docs" in result.output
    assert f"Source: {url}" in result.output
    assert "Required: 0/1 complete" in result.output
    commands = [line.removeprefix("Completion command: ") for line in result.output.splitlines()
                if line.startswith("Completion command: ")]
    assert commands
    for command in commands:
        assert shlex.split(command) == ["honeyguider", "track", "--state-dir", str(selected), "done", "review"]
    assert (directory / "000000.json").read_bytes() == before
    assert len(list(directory.iterdir())) == 1


@pytest.mark.parametrize("text", ["bad\n99\n0\n", "\n", "0\n"])
def test_invalid_input_and_default_exit(text):
    result = invoke(text)
    assert result.exit_code == 0, result.output
    if text.startswith("bad"):
        assert result.output.count("Invalid choice") == 2


@pytest.mark.parametrize("text", ["", "\x03", "2\n1\n", "2\n2\nhttps://docs.example.com/\n"])
def test_cancellation_at_prompts(text, tmp_path):
    result = invoke(text)
    assert result.exit_code == 0, result.output
    assert "Navigation cancelled" in result.output
    assert not (tmp_path / ".pathf1ndar").exists()


@pytest.mark.parametrize("text", ["2\n0\n0\n", "3\n0\n0\n",
                                      "2\n1\nhttps://docs.example.com/\ninstall\nn\n0\n"])
def test_back_and_network_refusal(text, monkeypatch):
    retrieve = AsyncMock(side_effect=AssertionError("Unexpected retrieval"))
    monkeypatch.setattr(cli, "research_pages", retrieve)
    result = invoke(text)
    assert result.exit_code == 0, result.output
    retrieve.assert_not_called()


@pytest.mark.parametrize("choice", ["1", "2"])
def test_documentation_explicit_retrieval(choice, monkeypatch, tmp_path):
    url = "https://docs.example.com/"
    report = Report(pages=[extract(b"<h2>Install</h2><p>Install the package.</p>", url, "install")])
    retrieve = AsyncMock(return_value=report)
    monkeypatch.setattr(cli, "research_pages", retrieve)
    result = invoke(f"2\n{choice}\n{url}\ninstall\ny\n0\n")
    assert result.exit_code == 0, result.output
    retrieve.assert_awaited_once_with(url, "install")
    assert "Source" in result.output
    assert not (tmp_path / ".pathf1ndar").exists()


@pytest.mark.parametrize("stdin_tty,stdout_tty", [(False, True), (True, False), (False, False), (True, True)])
def test_terminal_detection(stdin_tty, stdout_tty, monkeypatch):
    monkeypatch.setattr(welcome.sys, "stdin", Mock(isatty=lambda: stdin_tty))
    monkeypatch.setattr(welcome.sys, "stdout", Mock(isatty=lambda: stdout_tty))
    assert terminal_detector() is (stdin_tty and stdout_tty)


def test_noninteractive_help_and_compatibility(monkeypatch, tmp_path):
    monkeypatch.setattr(welcome, "interactive_terminal", lambda: False)
    result = invoke("1\n")
    assert result.exit_code == 2
    assert "Usage:" in result.output
    assert "Welcome:" not in result.output
    assert invoke(args=("--help",)).exit_code == 0
    assert invoke(args=("unknown-command",)).exit_code == 2
    assert invoke(args=("explore",)).exit_code == 2
    assert invoke(args=("next",)).exit_code == 1
    assert invoke(args=("explore", "--demo")).exit_code == 0
    assert invoke(args=("next",)).output.startswith("scope:")
    assert invoke(args=("done", "scope")).exit_code == 0
    assert "1/5 complete" in invoke(args=("status",)).output


def test_explicit_commands_never_open_menu(monkeypatch):
    monkeypatch.setattr(welcome, "welcome", Mock(side_effect=AssertionError("Menu opened")))
    assert invoke(args=("--help",)).exit_code == 0
    assert invoke(args=("explore", "--demo")).exit_code == 0
    assert invoke(args=("track", "--help")).exit_code == 0


@pytest.mark.parametrize("selection", ["1\n", "3\n1\n"])
def test_corrupt_demo_fails_closed(selection, tmp_path):
    state = tmp_path / "state.json"
    state.write_text("broken")
    result = invoke(selection, ("--state-file", str(state)))
    assert result.exit_code == 1
    assert state.read_text() == "broken"


def test_missing_track_and_overlapping_storage_fail_closed(tmp_path):
    missing = tmp_path / "missing"
    result = invoke(f"3\n2\n{missing}\n")
    assert result.exit_code == 1
    assert not missing.exists()
    result = invoke(f"3\n2\n{tmp_path}\n", ("--state-file", str(tmp_path / "demo.json")))
    assert result.exit_code == 2
    assert "Tracking directory must be separate" in result.output
