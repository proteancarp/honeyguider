import copy
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from typer.testing import CliRunner

from honeyguider.cli import app
from honeyguider.planning import (
    FixtureProvider, MAX_TASKS, PlanError, build_plan, next_action,
    task_state, validate_completed, validate_plan,
)
from honeyguider.research import Report, extract

URL = 'https://docs.example.com/guide'


def task(task_id='review', dependencies=None, classification='required'):
    return {'id': task_id, 'title': 'Review evidence', 'action': 'Read the cited section and record the documented prerequisites.',
            'prerequisites': dependencies or [], 'sources': [URL], 'classification': classification}


def payload(tasks=None):
    return {'schema_version': 1, 'tasks': tasks if tasks is not None else [task()]}


def validated(tasks):
    return validate_plan(json.dumps(payload(tasks)), {URL})


@pytest.fixture
def evidence():
    return Report(pages=[extract(b'<h2>Install a package</h2><p>Install in a local virtual environment.</p>', URL, 'install package')])


@pytest.mark.parametrize('response', ['', 'not JSON', '```json\n{}\n```', 'null', '[]', 'true', '{}', '{"schema_version":1,"schema_version":1,"tasks":[]}', 42, {}, 'x' * 65537])
def test_reject_malformed_response(response):
    with pytest.raises(PlanError):
        validate_plan(response, {URL})


@pytest.mark.parametrize('change', [
    {'schema_version': True}, {'schema_version': 2}, {'extra': 1},
    {'tasks': []}, {'tasks': {}}, {'tasks': [task()] * (MAX_TASKS + 1)},
])
def test_plan_envelope_is_strict(change):
    with pytest.raises(PlanError):
        validate_plan(json.dumps(payload() | change), {URL})


@pytest.mark.parametrize('change', [
    {'id': ''}, {'id': 'bad id'}, {'id': 'x' * 41}, {'title': ''}, {'title': 'x' * 161},
    {'action': 'x' * 1201}, {'action': 'hidden\x1b[31m'}, {'sources': []},
    {'sources': [URL, URL]}, {'sources': ['https://not-retrieved.example.com/']},
    {'sources': [URL + '#not-retrieved']}, {'sources': URL}, {'sources': [None]},
    {'classification': 'maybe'}, {'classification': True}, {'prerequisites': 'review'},
    {'prerequisites': [None]}, {'unknown_field': 'ignore this'},
])
def test_task_fields_and_citations_are_strict(change):
    with pytest.raises(PlanError):
        validated([task() | change])


@pytest.mark.parametrize('field', ['id', 'title', 'action', 'sources', 'prerequisites', 'classification'])
def test_missing_fields_rejected(field):
    raw = task()
    del raw[field]
    with pytest.raises(PlanError):
        validated([raw])


@pytest.mark.parametrize('tasks,message', [
    ([task(), task()], 'Duplicate task IDs'),
    ([task(dependencies=['unknown'])], 'Unknown dependency'),
    ([task(dependencies=['review'])], 'Self-dependency'),
    ([task('a'), task('b', ['a', 'a'])], 'Duplicate prerequisites'),
    ([task('a', ['b']), task('b', ['a'])], 'cycle'),
    ([task('a', ['b']), task('b', ['c']), task('c', ['a'])], 'cycle'),
])
def test_dependency_validation(tasks, message):
    with pytest.raises(PlanError, match=message):
        validated(tasks)


def test_diamond_dependencies_do_not_form_cycle():
    plan = validated([task('end', ['left', 'right']), task('left', ['root']), task('right', ['root']), task('root')])
    assert next_action(plan, frozenset()).id == 'root'
    done = validate_completed(plan, ['root', 'left'])
    assert task_state(plan.tasks[0], done) == 'blocked'
    assert next_action(plan, done).id == 'right'
    done = validate_completed(plan, ['root', 'left', 'right'])
    assert next_action(plan, done).id == 'end'


def test_states_required_and_optional_priority():
    plan = validated([task('extra', classification='optional'), task('implement', ['review']), task('review')])
    done = validate_completed(plan, [])
    assert [task_state(t, done) for t in plan.tasks] == ['ready', 'blocked', 'ready']
    assert next_action(plan, done).id == 'review'
    done = validate_completed(plan, ['review'])
    assert task_state(plan.tasks[2], done) == 'completed'
    assert next_action(plan, done).id == 'implement'
    done = validate_completed(plan, ['review', 'implement'])
    assert next_action(plan, done).id == 'extra'
    assert next_action(plan, validate_completed(plan, ['review', 'implement', 'extra'])) is None


def test_optional_prerequisite_unblocks_required_work():
    plan = validated([task('unrelated', classification='optional'), task('required', ['dependency']), task('dependency', classification='optional')])
    assert next_action(plan, frozenset()).id == 'dependency'
    assert task_state(plan.tasks[1], frozenset()) == 'blocked'


@pytest.mark.parametrize('done', [['unknown'], ['review', 'review'], ['implement']])
def test_completion_validation(done):
    plan = validated([task('review'), task('implement', ['review'])])
    with pytest.raises(PlanError):
        validate_completed(plan, done)


def test_fixture_provider_is_deterministic_and_uses_evidence(evidence):
    provider = FixtureProvider()
    before = copy.deepcopy(evidence)
    assert provider.generate(evidence, 'install package') == provider.generate(evidence, 'install package')
    plan = build_plan(evidence, 'install package', provider)
    assert evidence == before
    assert len(plan.tasks) == 3
    assert plan.tasks[0].title == 'Review: Install a package'
    assert plan.tasks[-1].classification == 'optional'
    assert all(t.sources == (URL,) for t in plan.tasks)
    assert next_action(plan, frozenset()).id == 'review-1'


def test_provider_boundary_rejects_bad_output(evidence):
    class BrokenProvider:
        def generate(self, evidence, goal):
            return json.dumps(payload([task() | {'sources': ['https://invented.example.com']}]))
    with pytest.raises(PlanError, match='retrieved'):
        build_plan(evidence, 'install package', BrokenProvider())


def test_only_page_sources_are_allowed_not_discovered_links(evidence):
    evidence.pages[0].links.append({'url': 'https://docs.example.com/not-fetched'})
    class LinkProvider:
        def generate(self, evidence, goal):
            return json.dumps(payload([task() | {'sources': [evidence.pages[0].links[0]['url']]}]))
    with pytest.raises(PlanError):
        build_plan(evidence, 'install package', LinkProvider())


def test_provider_cannot_expand_citation_allowlist(evidence):
    class MutatingProvider:
        def generate(self, evidence, goal):
            invented = 'https://invented.example.com/'
            evidence.pages.append(extract(b'<p>Install package</p>', invented, goal))
            return json.dumps(payload([task() | {'sources': [invented]}]))
    with pytest.raises(PlanError, match='retrieved'):
        build_plan(evidence, 'install package', MutatingProvider())


def test_insufficient_evidence():
    with pytest.raises(PlanError, match='No retrieved'):
        build_plan(Report(), 'install package')
    report = Report(pages=[extract(b'<p>Unrelated</p>', URL, 'install package')])
    with pytest.raises(PlanError, match='No relevant'):
        build_plan(report, 'install package')


def invoke(evidence, *args, state=None):
    prefix = ['--state-file', str(state)] if state else []
    with patch('honeyguider.cli.research_pages', AsyncMock(return_value=evidence)) as research:
        result = CliRunner().invoke(app, [*prefix, 'plan', URL, '--goal', 'install package', *args])
    research.assert_awaited_once_with(URL, 'install package')
    return result


def test_cli_default_shows_one_action_and_never_touches_state(evidence, tmp_path):
    state = tmp_path / 'state.json'
    state.write_text('existing offline demo progress')
    result = invoke(evidence, state=state)
    assert result.exit_code == 0, result.output
    assert 'DEMONSTRATION' in result.output and 'no live AI inference' in result.output
    assert result.output.count('Action: ') == 1
    assert 'Next action: review-1' in result.output
    assert 'Action: Write a minimal' not in result.output
    assert state.read_text() == 'existing offline demo progress'
    absent = tmp_path / 'not-created.json'
    assert invoke(evidence, state=absent).exit_code == 0
    assert not absent.exists()


def test_cli_all_and_self_reported_progress(evidence):
    result = invoke(evidence, '--all', '--completed', 'review-1')
    assert result.exit_code == 0, result.output
    assert '[required; completed]' in result.output
    assert '[required; ready]' in result.output
    assert '[optional; blocked]' in result.output
    assert 'Prerequisites: prototype' in result.output
    assert 'Next action: prototype' in result.output
    result = invoke(evidence, '--completed', 'review-1', '--completed', 'prototype')
    assert result.exit_code == 0
    assert 'Optional work' in result.output
    assert 'Next action: test-prototype' in result.output
    result = invoke(evidence, '--completed', 'review-1', '--completed', 'prototype', '--completed', 'test-prototype')
    assert 'All tasks completed' in result.output
    assert result.output.count('Action: ') == 0


def test_cli_invalid_completion_and_failed_research(evidence):
    assert invoke(evidence, '--completed', 'prototype').exit_code == 1
    failed = invoke(Report(errors=['HTTP 403']))
    assert failed.exit_code == 1 and 'HTTP 403' in failed.output
    partial = copy.deepcopy(evidence)
    partial.errors.append('Linked page timed out')
    result = invoke(partial)
    assert result.exit_code == 1 and 'Next action: review-1' in result.output
    assert 'Linked page timed out' in result.output


def test_cli_rejects_malformed_provider_output(evidence):
    with patch('honeyguider.planning.FixtureProvider.generate', return_value='not JSON'):
        result = invoke(evidence)
    assert result.exit_code == 1 and 'Cannot plan' in result.output


def test_real_documentation_fixture_plan_is_bounded_and_cited():
    body = (Path(__file__).parent / 'fixtures' / 'celo_8004_mdx.html').read_bytes()
    source = 'https://docs.celo.org/build/agents/8004'
    evidence = Report(pages=[extract(body, source, 'Register an ERC-8004 agent on Celo')])
    plan = build_plan(evidence, 'Register an ERC-8004 agent on Celo')
    assert len(plan.tasks) == 3  # continuation excerpts share one heading/review task
    assert all(t.sources == (source,) for t in plan.tasks)
    assert 'Register a service' in plan.tasks[0].title
