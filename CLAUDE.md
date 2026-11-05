# CLAUDE.md

The design is in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). Read it before changing anything; it is the source of truth for contexts, invariants, the access policy and the build order.

## Working rules

- Build one step of the build order at a time and commit after each. The commit history is graded.
- Every line must be defensible in a live walkthrough. No speculative code, no gold-plating.
- Explain each step as you go: the owner is still learning Python and FastAPI.

## Boundaries

- Four bounded contexts under `src/kinetic/`: `identity`, `directory`, `care_team` (core), `records`.
- Each context has `domain/`, `application/`, `infrastructure/`, `api/`.
- `domain/` is pure Python (dataclasses). No SQLAlchemy, FastAPI or Pydantic there.
- Contexts talk only through ports or each other's public module, never by reaching into internals.
- `shared_kernel/` holds only ids, `Clock`, `TimeRange`, `DomainEvent`.
- Only `care_team.access.AccessPolicy` decides access. Nothing else re-derives policy.

## Commands

- `uv sync` to install, `uv run pytest` to test.
