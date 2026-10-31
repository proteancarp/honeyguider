"""Curated practice scenario; no live hackathon rules or deadlines implied."""
from .model import Task

CELO = "https://docs.celo.org/"
AGENTS = "https://docs.celo.org/build-on-celo"
TASKS = (
    Task("scope", "Define a Celo hackathon agent", "Write a one-paragraph use case for an agent that explains a developer's next step. List inputs, expected output, and a demo success criterion. Review the linked documentation when online.", sources=(CELO,)),
    Task("workspace", "Prepare a local workspace", "Create a project directory and initialize Git manually. Record Python, Node.js and npm versions in your project notes.", ("scope",), ("python", "git", "node", "npm"), (CELO,)),
    Task("prototype", "Build a deterministic agent prototype", "Implement a local function that maps sample developer questions to documented next steps. Use fixture data; do not connect a wallet or send transactions.", ("workspace",), sources=(AGENTS,)),
    Task("validate", "Validate the demo flow", "Add offline tests for one successful flow and one blocked flow, then run them and record the actual results.", ("prototype",)),
    Task("submission", "Prepare a submission draft", "Write a README with setup steps, architecture, limitations, source links and a short demo script. Verify actual event eligibility and submission requirements separately before submitting.", ("validate",), sources=(CELO,)),
)
