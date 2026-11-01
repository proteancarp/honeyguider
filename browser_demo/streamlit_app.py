"""Isolated developer workspace. Untrusted evidence always uses plain text."""
import streamlit as st

from honeyguider.browser_demo import DEFAULT_GOAL, DEFAULT_URL, run_demo
from honeyguider.planning import PlanError, next_action, task_state, validate_completed
from honeyguider.research import ResearchError
from honeyguider.recorded import EXPLORER, SOURCE, load_recording

# Only static, application-owned CSS. Keyed container classes are a supported
# Streamlit API; no generated classes or internal data-testid selectors.
WORKSPACE_STYLE = """
<style>
.st-key-workspace {
    max-width: 1168px;
    margin-inline: auto;
    /* Trim Streamlit's page inset while keeping its toolbar clear. */
    margin-block-start: -2rem;
    --honey: #9A5B00;
    --surface: #F5F5F0;
    overflow-wrap: anywhere;
}
.st-key-workspace h1 { font-size: 1.75rem; padding: 0 0 0.25rem; }
.st-key-workspace h2,
.st-key-workspace h3 { font-size: 1.125rem; padding: 0; }
.st-key-workspace_header { padding-bottom: 0.25rem; }
.st-key-demo_notice {
    border-left: 3px solid var(--honey);
    padding-left: 0.75rem;
}
.st-key-demo_notice p { color: #526159; }
/* Keep the demo disclosure legible rather than applying caption opacity. */
.st-key-demo_notice div { opacity: 1; }
.st-key-next_action {
    background: var(--surface);
    border-top: 3px solid var(--honey);
    border-radius: 8px;
    padding: 1rem;
}
.st-key-roadmap { padding: 0.5rem 0; }
.st-key-task_title div { font-size: 1.5rem; font-weight: 600; line-height: 1.2; }
.st-key-roadmap [class*="st-key-roadmap_title_"] { font-weight: 600; }
.st-key-workspace button:focus-visible,
.st-key-workspace summary:focus-visible {
    outline: 2px solid var(--honey);
    outline-offset: 3px;
}
@media (max-width: 640px) {
    .st-key-next_action { padding: 0.75rem; }
    .st-key-task_title div { font-size: 1.25rem; }
}
</style>
"""

STATE_LABELS = {
    "ready": ("Ready", "green", ":material/play_arrow:"),
    "blocked": ("Blocked", "gray", ":material/lock:"),
    "completed": ("Completed", "green", ":material/check:"),
}


def show_citations(task):
    for source in task.sources:
        st.text("Citation: " + source)


def show_status(task, done):
    label, color, icon = STATE_LABELS[task_state(task, done)]
    with st.container(horizontal=True):
        st.badge(label, color=color, icon=icon)
        st.badge("Required" if task.classification == "required" else "Optional",
                 color="primary" if task.classification == "required" else "gray")


def load_result(url, goal, *, offline):
    """Replace the submitted context, including on failure; never fall back."""
    st.session_state.pop("result", None)
    st.session_state.pop("request_error", None)
    st.session_state.completed = []
    try:
        st.session_state.result = run_demo(url, goal, offline=offline)
    except (PlanError, ResearchError):
        st.session_state.request_error = (
            "Unable to plan: check the public HTTPS URL and searchable goal. "
            "Offline mode requires the default URL."
        )
    except Exception:
        st.session_state.request_error = (
            "The demo could not finish this request. Retry with Change source or goal, "
            "or select Load offline example."
        )


def load_offline_example():
    """Explicit recovery also restores the editor's defaults before rendering."""
    st.session_state.documentation_url = DEFAULT_URL
    st.session_state.development_goal = DEFAULT_GOAL
    st.session_state.use_offline = True
    load_result(DEFAULT_URL, DEFAULT_GOAL, offline=True)


def show_evidence(result):
    st.header("Documentation evidence", anchor=False)
    st.caption("Inspect the passages behind the roadmap. Citations identify retrieved inputs, not proof of the scaffold's choices.")
    for index, page in enumerate(result.report.pages, 1):
        # Expander labels are static: page-controlled titles stay in plain text.
        with st.expander(f"Source {index} · {len(page.sections)} relevant excerpts"):
            st.text("Page title: " + page.title)
            st.text("Retrieved source: " + page.url)
            if page.warning:
                st.text(page.warning)
            if not page.sections:
                st.text("No relevant excerpts matched this goal.")
            for section in page.sections:
                st.divider()
                st.text("Excerpt: " + section["heading"])
                st.text("Citation: " + section["source_url"])
                for block in section["blocks"]:
                    if block["kind"] == "code":
                        st.text("Code example omitted in this browser demo; consult the cited documentation.")
                    else:
                        st.text(block["text"])
                if section["truncated"]:
                    st.text("Excerpt shortened; consult source for full context.")


def show_plan(result):
    plan = result.plan
    # Keep the session's ordered list; use the validated set only for selection.
    completed = st.session_state.get("completed", [])
    done = validate_completed(plan, completed)
    action = next_action(plan, done)
    required = [task for task in plan.tasks if task.classification == "required"]
    task_titles = {task.id: task.title for task in plan.tasks}
    required_done = sum(task.id in done for task in required)
    focus, roadmap = st.columns([1.65, 1], gap="medium")
    with focus:
        with st.container(key="next_action"):
            st.header("Next action", anchor=False)
            if action:
                with st.container(key="task_title", gap=None):
                    # Task titles can include external page headings: plain text only.
                    st.text(action.title)
                show_status(action, done)
                st.text(action.action)
                if st.button("Mark step complete", key="complete_step", type="primary", width="stretch",
                             help="Self-reported completion; Honeyguider does not verify implementation."):
                    updated = [*completed, action.id]
                    validate_completed(plan, updated)
                    st.session_state.completed = updated
                    st.rerun()
                with st.container(key="action_sources", gap=None):
                    show_citations(action)
            else:
                st.success("All demonstration tasks are marked complete.")
                st.text("Your roadmap is complete. Review the source documentation and your project notes before moving on.")
            st.caption("Self-reported completion. Progress stays in this browser session.")
        if st.button("Reset session progress", key="reset_progress", type="tertiary"):
            st.session_state.completed = []
            st.rerun()
    with roadmap, st.container(key="roadmap"):
        st.header("Dependency roadmap", anchor=False)
        st.progress(len(done) / len(plan.tasks), text=f"{len(done)} of {len(plan.tasks)} complete · {required_done} of {len(required)} required")
        for number, task in enumerate(plan.tasks):
            with st.container(key=f"roadmap_task_{number}", gap=None):
                with st.container(key=f"roadmap_title_{number}", gap=None):
                    st.text(task.title)
                show_status(task, done)
                blockers = [dep for dep in task.prerequisites if dep not in done]
                if blockers:
                    st.text("Waiting on: " + ", ".join(task_titles[dep] for dep in blockers))
                with st.expander("Action & citations"):
                    st.text("Task ID: " + task.id)
                    st.text("Depends on: " + (", ".join(task.prerequisites) or "nothing"))
                    st.text(task.action)
                    show_citations(task)
    st.caption("Validated: task structure, acyclic dependencies and citations to retrieved pages. Semantic correctness and implementation are not verified.")


def workspace():
    # The sentinel is deliberately independent of result existence. Failed
    # retrievals and even failed initialization must not trigger an implicit retry.
    if not st.session_state.get("demo_initialized", False):
        st.session_state.demo_initialized = True
        load_result(DEFAULT_URL, DEFAULT_GOAL, offline=True)

    # Widget defaults live in session state so explicit recovery can reset them
    # without competing with value= defaults or exposing Streamlit warnings.
    st.session_state.setdefault("documentation_url", DEFAULT_URL)
    st.session_state.setdefault("development_goal", DEFAULT_GOAL)
    st.session_state.setdefault("use_offline", True)
    header = st.container(key="workspace_header", gap=None)
    with st.expander("Change source or goal", expanded=False):
        with st.form("research", border=False):
            source, intent = st.columns(2, gap="medium")
            with source:
                url = st.text_input("Documentation URL", max_chars=4096,
                                    key="documentation_url")
                st.caption("The bundled capture works only with the default Celo URL.")
            with intent:
                goal = st.text_area("Development goal", max_chars=1000,
                                    height=100, key="development_goal")
            offline = st.checkbox("Use bundled offline documentation capture",
                                  key="use_offline",
                                  help="Uncheck to retrieve a public HTTPS HTML page from the hosting server.")
            submitted = st.form_submit_button("Retrieve and plan", key="retrieve_plan", type="primary")
            st.caption("Read-only research. Keep secrets out of URLs and goals. A new submission clears progress.")

    if submitted:
        with st.spinner("Reading documentation and validating tasks…"):
            load_result(url, goal, offline=offline)

    result = st.session_state.get("result")
    with header:
        if result:
            st.badge("Offline example" if result.offline else "Live documentation retrieval",
                     color="primary" if result.offline else "green")
        if result:
            st.text(result.goal)
        with st.container(key="demo_notice", gap=None):
            st.caption("Authored deterministic demonstration, not AI inference. Tasks are a scaffold, not documentation requirements.")
            if result and result.offline:
                st.caption("Bundled, pruned documentation capture. No live retrieval or verification of current documentation.")
            elif result:
                st.caption(f"{result.report.requests} requests · {result.report.bytes_read:,} bytes received. Planning uses the authored scaffold.")

    if st.session_state.get("request_error"):
        st.error(st.session_state.request_error)
    if result is None:
        st.text("No plan is loaded. Change source or goal to retry, or load the bundled offline example.")
        st.button("Load offline example", key="load_offline", on_click=load_offline_example)
        return
    for error in result.report.errors:
        st.warning("Retrieval incomplete; successfully retrieved evidence may still be used.")
        st.text(error)
    if result.plan is None:
        st.warning("No validated plan is available. Try a more specific goal or another source.")
        st.text(result.planning_error)
        st.button("Load offline example", key="load_offline", on_click=load_offline_example)
    else:
        show_plan(result)
    show_evidence(result)
    with st.expander("Plan context and demo boundaries"):
        # Always display submitted inputs, not any unsaved edits in the form.
        st.text("Documentation URL: " + result.url)
        st.text("Development goal: " + result.goal)
        st.caption("Citations identify input pages; they do not verify the scaffold's recommendations. Code examples are omitted in this browser demo.")
        st.caption("Live mode: public HTTPS HTML only, up to three same-host pages, six requests, 1 MiB total and a 20-second retrieval deadline.")


def recorded_showcase():
    st.header("Recorded AI Inference", anchor=False)
    st.info("Replay of a previously completed paid Cencori inference. No new inference or payment runs here.")
    try:
        data, plan = load_recording()
    except (ValueError, OSError):
        st.error("The recorded showcase is unavailable: fixture validation failed.")
        return
    st.text("Development goal: " + data['goal'])
    st.link_button("Documentation source", SOURCE)
    focus, details = st.columns([1.65, 1])
    with focus, st.container(border=True):
        st.subheader("AI-generated next action", anchor=False)
        action = next_action(plan, frozenset())
        st.text(action.title)
        st.text(action.action)
        show_citations(action)
        st.caption("Recorded starting point. Review recommendations against the documentation before implementing them.")
    with details:
        st.text("Model: " + data['model'])
        st.text(f"Tokens: {data['prompt_tokens']} prompt / {data['completion_tokens']} completion / {data['total_tokens']} total")
        st.text(f"Maximum output: {data['max_output_tokens']} tokens; finish reason: stop")
        st.text("Quoted and authorized: 0.01 USDC on Celo Mainnet (42220)")
        st.link_button("View transaction on Celoscan", EXPLORER)
        st.caption("The user independently confirmed the transaction on Celoscan. Honeyguider's local settlement record remains unknown; this browser does not verify settlement.")
    st.subheader("Nine-task dependency roadmap", anchor=False)
    st.caption("6 required · 3 optional. Read-only replay with no progress changes.")
    for number, task in enumerate(plan.tasks, 1):
        with st.container(gap="small"):
            title, status = st.columns([3, 1])
            with title:
                st.text(f"{number}. {task.title}")
            with status:
                show_status(task, frozenset())
            # Static labels only: generated titles and details remain plain text.
            with st.expander("Task details", expanded=False):
                st.text("Task ID: " + task.id)
                st.text("Prerequisites: " + (", ".join(task.prerequisites) or "none"))
                st.text("Blockers: " + (", ".join(task.prerequisites) or "none; ready to start"))
                st.text(task.action)
                show_citations(task)
    with st.expander("How human approval worked"):
        st.text("In the local CLI, a person reviewed the prepared request and fresh quote, chose the exact spend cap, and entered a session approval code for one attempt. There were no automatic retries. The saved response then passed request, completion, citation and dependency validation.")
        st.text("Visitors read a shipped, sanitized fixture only. No wallet connection, private receipts, credentials or payment execution are available in this showcase.")
        st.text("Validation checks structure and local consistency. It does not establish recommendation correctness, citation entailment or on-chain settlement.")


def main():
    st.set_page_config(page_title="Honeyguider · Developer workspace", page_icon="🍯", layout="wide")
    st.html(WORKSPACE_STYLE)
    with st.container(key="workspace"):
        st.title("Honeyguider", anchor=False)
        st.text("Turn development documentation into a source-linked roadmap, with prerequisites and a clear next action.")
        recorded, playground = st.tabs(["Recorded AI Inference", "Deterministic playground"])
        with recorded:
            recorded_showcase()
        with playground:
            workspace()


if __name__ == "__main__":
    main()
