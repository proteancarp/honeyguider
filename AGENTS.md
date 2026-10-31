# Pathfinder Development Instructions

You are implementing pathf1ndar, a Python CLI agent.

Priorities:
1. Working MVP before additional features.
2. Simple, maintainable architecture.
3. Safe, read-only environment inspection.
4. Source-backed technical recommendations.
5. Deterministic offline tests.

Required CLI commands:
- explore
- check
- next
- done
- status

Constraints:
- Python 3.11+
- Typer, Rich, HTTPX, BeautifulSoup
- pytest
- Local JSON state
- No frontend or database
- No heavyweight agent frameworks
- No unrestricted shell execution
- No autonomous payments
- No wallet key access
- No fabricated sources or test results

Implement an offline demo mode first.

Use Codex for implementation and tests, but explain
architectural decisions and test outcomes.

Do not commit or push automatically.
