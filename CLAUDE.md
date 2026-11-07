# CLAUDE.md

The design is in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). Read it before changing anything; it is the source of truth for contexts, invariants, the access policy and the build order.

## Working rules

- Build one step of the build order at a time and commit after each. The commit history is graded.
- Every line must be defensible in a live walkthrough. No speculative code, no gold-plating.
- Explain each step as you go: the owner is still learning Python and FastAPI.

## Boundaries

- Five bounded contexts under `src/kinetic/`: `identity`, `directory`, `care_team` (core), `records`, `access` (the policy decision point).
- Each context has `domain/`, `application/`, `infrastructure/`, `api/`. `access` has no `infrastructure/`: its facts come through ports other contexts implement.
- `domain/` is pure Python (dataclasses). No SQLAlchemy, FastAPI or Pydantic there.
- Contexts talk only through ports or each other's public module, never by reaching into internals.
- `shared_kernel/` holds only ids, `Clock`, `TimeRange`, `DomainEvent`.
- Only `access` decides access. Other contexts supply facts through its ports and call it through `access.public`; `access` imports no other context except `identity.public`, to know who is calling. Nothing else re-derives policy.

## Commands

- `uv sync` to install, `uv run python -m pytest` to test (scenario tests need Postgres running).
- `cp .env.example .env`, then `docker compose up -d --wait` (Postgres on host port 5433).
- `uv run python -m alembic upgrade head` to migrate; migrations are hand-written in `migrations/versions/`.
- `uv run python -m uvicorn kinetic.main:app --reload` to serve; `GET /health` checks the database.
- `uv run python scripts/seed.py --reset` fills the dev database with synthetic demo data through the API; the demo page is at `http://localhost:8000/demo/`.
- No `make` on the dev machine: use the commands above.
- Use `uv run python -m <tool>`: on this Windows machine `uv run <tool>` fails with "uv trampoline failed to canonicalize script path".
