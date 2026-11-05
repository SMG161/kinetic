# Kinetic Care Team: Architecture & Build Plan

## Overview

We build a small, deep slice of Kinetic: working identity and auth, plus a client-owned care team model that expresses every scenario in the brief. Most of the time goes into the care team. Scheduling, billing, messaging, documents and wearables are not built; they appear only on the context map to justify the boundaries.

**Stack:** Python, FastAPI, Pydantic, PostgreSQL, SQLAlchemy 2.0, Alembic, pytest, docker compose, uv.

**Deliverables:** running code, a README (overview, setup, architecture, 3–5 key decisions, cuts and next steps) and a list of open questions.

## Subdomains and bounded contexts

We build four bounded contexts: `identity`, `directory`, `care_team` (the core) and `records`. Four more exist only on the map.

| Subdomain | Type | Context | Built? | Why |
|---|---|---|---|---|
| Care coordination | Core | `care_team` | Yes, deeply | What Kinetic sells: several providers serving one client without stepping on each other |
| Practice directory | Supporting | `directory` | Yes, thin | Orgs, staff, providers, clients. Needed, mostly CRUD with a few rules |
| Clinical records | Supporting | `records` | Yes, minimal | Exists so "see vs act" can be exercised and tested |
| Identity and authentication | Generic | `identity` | Yes, small | Every SaaS needs it; in production you would buy it |
| Scheduling, Billing, Messaging, Documents/Wearables | Out of scope | none | No | Described in the README to justify the boundaries; they consume care_team events and decisions |

### Ubiquitous language per context

- **identity** (who someone is): Person, Account, Credential, Session, Invitation. Hands everyone a `person_id` and nothing else.
- **directory** (what someone is in the business): Organization, StaffMembership (owner, admin, front desk), Provider (disciplines, credentials, affiliations; may be independent), Client. One person can hold several personas, all pointing at one `person_id`.
- **care_team** (the core): Care Team, Membership, Engagement, Designation (Booking Contact, Clinical Lead), Handoff, Coverage, Team Event. Owns the `AccessPolicy`.
- **records** (thin): Clinical Record, Record Category, Author, Org Context. Asks `care_team` for every access decision.

The same word means different things per context, which is the reason the contexts are separate:

- **Provider** in `directory` is a professional with credentials and affiliations. In `care_team` the same person is only a **Member** with a discipline and an engagement level.
- **Client** in `directory` is a profile record. In `care_team` it is the subject the team exists for. In `identity` it is just a Person.
- **Organization** in `directory` is an entity with staff. In `care_team` it is only an **org context** stamped on a membership or record.

### Context map

- **identity → everyone:** upstream; publishes `person_id`, which others accept as-is.
- **directory → care_team:** customer/supplier. `care_team` reads disciplines and affiliations through its own `ProviderDirectory` port, an anti-corruption layer.
- **care_team → records:** records conforms; it calls the `CareAccess` port and accepts the answer.
- **care_team → scheduling/billing (stubs):** in-process domain events such as `BookingContactHandedOff`; billing asks "can bill?".

```
 identity (generic) ──person_id──▶ directory (supporting)
        │                                │
        │                        ProviderDirectory port
        │                                ▼
        └────────person_id────▶ care_team (core) ──CareAccess──▶ records (supporting)
                                         ┊
                                   domain events
                                         ▼
                         ┌╌ Scheduling, Billing, Messaging (not built) ╌┐
```

Arrows point downstream. The dashed box is described in the README only.

Boundaries are enforced with one Postgres schema per context (no cross-schema foreign keys except to `identity.person`) and an **import-linter** contract: `care_team.domain` imports nothing outside itself and the shared kernel, and contexts import each other only through a public module.

### Rejected boundaries

- **A separate authorization context:** it would need facts from every context and become a module that knows everything. Access rules come from team facts, so they live in the core.
- **A separate consent context:** probably right in real healthcare; too much for three days. Listed as next.
- **Merging directory into care_team:** org staff management and team coordination change for different reasons; merging leaks gym-admin concerns into the core.
- **Episodes of care as a context:** more likely a future concept inside `care_team` that scopes memberships and records to one concern.

## Identity and authentication

Authentication and identity stay in one context, `identity`, modelled as two aggregates. Authorization lives elsewhere, in `care_team`.

### Authentication vs authorization

- **Authentication** (are you who you say you are?) lives in `identity`. It covers credentials, login and sessions, and ends by producing a `person_id`.
- **Authorization** (what may you do?) depends on team memberships, engagement, coverage windows and org staff roles. It lives in the `care_team` `AccessPolicy`, with `directory` supplying org-staff facts through a port.

### Person is not Account

- **Person** is the real-world human: name, contact details, a stable `person_id`.
- **Account** is a way that person signs in: credentials and sessions.
- A Person can exist without an Account: a client who was invited but hasn't accepted, a guardian-managed minor later, a record migrated from a legacy system. One Person could later have several sign-in methods.

### Why one context, not two

Signup, invitation acceptance and "link this login to an existing person" touch both aggregates in one transaction. They share a language and change together, so a split would add cross-context coordination for no benefit.

We would split them if authentication moved to a vendor (Auth0, Cognito, an org's SSO). A small `identity` context would then map the vendor's subject ID to our `person_id`. Keeping Person and Account separate now makes that swap cheap.

### Mechanism

- Email and password, hashed with **argon2**.
- **Short-lived JWT access tokens plus opaque refresh tokens** (the Supabase / Auth0 shape):
  - The access token is a JWT (HS256, 15 minutes) holding only `sub` (person_id), `sid` (session id) and `exp`. Verifying it needs no database lookup.
  - The refresh token is opaque, valid for 30 days, stored hashed in `identity.session` and rotated on every use. `POST /auth/refresh` swaps it for a new access token.
  - Logout deletes the session row, so no new access tokens can be issued. **Trade-off accepted:** an access token already issued stays valid until it expires, at most 15 minutes.
  - The algorithm is pinned when verifying, which rejects `alg: none` and algorithm-swap forgeries. Expiry is checked against the injected `Clock`.
  - Considered and replaced: opaque session tokens checked on every request. They give instant revocation, but JWT is the industry-standard bearer format and is what an external identity provider would issue, so adopting it now keeps a later move to a vendor cheap.
- The token resolves only to `person_id` and a session id. Personas and permissions are looked up on the server for every request. Roles in a token go stale; a covering provider would keep access after the coverage window ended. That is why the JWT carries no roles.
- `GET /me` returns the person and all their personas (client, provider, staff memberships).

### Onboarding and invitations

- **Client self-signup** creates a Person, an Account and a Client profile.
- **Invitations** use a random token stored hashed, with a type (org invites staff or provider; provider or org invites client, optionally into a care team). Accepting either creates an account or links to an existing person by email.
- Email sending is stubbed: the token is returned in the API response and the README says so.

## The care team (core)

The team is **of the client**: each client has exactly one `CareTeam`, owned by no organization. Each membership records the org (or none) the provider serves the client on behalf of.

### Why the client

- The client is the only thing that stays the same across every org.
- **Rejected, org-owned case:** it cannot hold the independent physio without the gym "owning" a provider who doesn't work for it.
- **Rejected, episode-of-care aggregate:** the trainer's relationship and the booking contact span episodes. Episodes are a "what's next" item inside this context.

### Aggregate shape

`CareTeam` is the aggregate root. It is small (a handful of members), so it is loaded whole.

| Element | Kind | Holds |
|---|---|---|
| `CareTeam` | Aggregate root | client_id, version, the entities below |
| `Membership` | Entity | provider_id, org_context_id or null, engagement, reason, `TimeRange` |
| `DesignationAssignment` | Entity | designation, membership_id, `TimeRange` |
| `Coverage` | Entity | covered_membership_id, covering_provider_id, `TimeRange`, reason |
| `TeamEvent` | Recorded with every command | actor, reason, at, event type |
| `TimeRange` | Value object | half-open `[from, to)` |
| `Engagement` | Value object | `ACTIVE`, `CONSULTING`, `ALUMNI` |
| `Designation` | Value object | `BOOKING_CONTACT`, `CLINICAL_LEAD` |
| `Discipline`, `Reason`, `Capability` | Value objects | provider profession; why; an allowed action |

### Invariants

Each invariant gets a unit test.

1. One care team per client.
2. A provider never has two overlapping memberships on the same team.
3. Periods are never mutated, only closed and reopened. A change of engagement closes the current period and opens a new one; nothing is deleted.
4. At any instant there is at most one holder of each designation. Once the team has an active member, there is exactly one booking contact.
5. A designation holder must be an `ACTIVE` member. The clinical lead must also have a clinical discipline (physio or physician).
6. A handoff is atomic: the old assignment closes at time t and the new one opens at t in the same transaction. No gap, no overlap.
7. A membership holding a designation cannot be ended or demoted unless the same command hands the designation off.
8. Coverage falls inside the covered membership's period, the covering provider is not the covered provider, and one membership has no overlapping coverages.
9. Every command records a `TeamEvent` with actor, reason and time.

Invariants 2 and 4 are also enforced in Postgres with exclusion constraints (needs `btree_gist`):

```sql
EXCLUDE USING gist (team_id WITH =, designation WITH =, tstzrange(valid_from, valid_to) WITH &&)
```

A `version` column on `care_team` gives optimistic locking, so two concurrent handoffs cannot both succeed.

### Commands and who may issue them

Add member, change engagement, end membership, hand off a designation, schedule coverage, end coverage. The client can always issue them; the current booking contact and clinical lead hold `manage_team`. Covering providers and org admins do not (an open question).

### Coverage semantics

During the window, the covering provider gets the covered member's capabilities except `manage_team` and designations. The designation stays with the original holder; an "effective booking contact" query resolves to the cover during the window, so the answer is unambiguous at every instant. Access ends because the policy evaluates the window at request time. No background job revokes anything.

### History

Closed periods plus `TeamEvent` rows keep who was on the team, in what role, when and why. `GET /care-teams/{id}?as_of=<timestamp>` reconstructs the team at any instant. **Rejected, event sourcing:** too costly for three days; current-state tables, append-only periods and an event table give "keep, don't overwrite" at a fraction of the cost.

### How each scenario is expressed

| Scenario | Expression in the model |
|---|---|
| Trainer, physio and physician at once | Three concurrent `ACTIVE` memberships with different disciplines and org contexts |
| The "face" is not the clinical lead | Two independent designations, each handed off on its own |
| Two-week coverage, then handback | A `Coverage` with a window; access is computed at request time; handback ends the coverage |
| Physio steps back after rehab | `ACTIVE` period closes, `CONSULTING` period opens with a reason; history intact |
| Physician sees, massage therapist doesn't | Discipline decides record categories (Access policy section) |
| Gym client with an independent physio | `org_context_id` on memberships and records; org admins see only their org's slice |
| History is kept | Closed periods, `TeamEvent`s and the `as_of` query |

## Access policy

Access combines two small tables instead of one permissions matrix: **discipline** decides which record categories a member can see, and **engagement** decides which actions they can take. Allowed means both say yes.

### Engagement decides actions

| Engagement | view | write_note | run_session | message_client | bill |
|---|---|---|---|---|---|
| ACTIVE | yes | yes | yes | yes | yes |
| CONSULTING | yes | no | no | yes | no |
| ALUMNI | own authored only | no | no | no | no |

### Discipline decides record categories

| Discipline | Record categories visible |
|---|---|
| Physician, physio | medical_history, assessment, session_note, training_plan |
| Trainer | training_plan, non-clinical session_note, assessment summary |
| Massage, nutrition | their own plan type, non-clinical session_note |

This separates "see" from "act" naturally. The physio stepping back after rehab is only a change from `ACTIVE` to `CONSULTING`, and no table changes.

### One decision point

`AccessPolicy.decide(principal, action, resource, at) -> Decision(allowed, reason)` lives in `care_team`.

- Every endpoint calls it through a FastAPI dependency. `records` calls it through the `CareAccess` port. No other code decides access.
- `at` comes from an injected `Clock`, so tests can move time ("day 15: the cover is denied").
- Every decision carries a **reason**, such as "denied: coverage ended at 2026-11-17". An `/access/explain` endpoint shows it, which makes a strong walkthrough demo.

### Cross-organization rules

- Memberships and records carry an `org_context_id` (null for an independent provider).
- An org admin sees team membership and records only within their own org's context, never the independent physio's notes.
- The client always sees their own team and its history.

### Principals

The principal is resolved from the session token to `person_id`, then to personas: client profile, provider profile, staff memberships. A person can act as client of their own team and as provider on someone else's. Nothing about who someone is or what they may do comes from the request body.

## Stack, persistence, layout and testing

The domain is pure Python; SQLAlchemy lives only in each context's infrastructure layer.

### Decisions

- **SQLAlchemy 2.0, mapped by repositories.** Domain classes are plain dataclasses; repositories map to and from ORM table models. **Rejected:** ORM models as domain models, which is faster but leaks persistence into the domain.
- **Alembic** for migrations, including the `btree_gist` extension and exclusion constraints.
- **One Postgres schema per context** (`identity`, `directory`, `care_team`, `records`).
- **Postgres-specific features used on purpose:** `tstzrange`, exclusion constraints and a `version` column for optimistic locking.
- **Tooling:** uv for packages, docker compose for Postgres, `make` targets for `up`, `migrate`, `seed`, `demo`, `test`.

### Layout

```
src/kinetic/
  shared_kernel/        # ids, Clock, TimeRange, DomainEvent
  identity/
    domain/  application/  infrastructure/  api/
  directory/
    domain/  application/  infrastructure/  api/
  care_team/
    domain/  application/  infrastructure/  api/
    access/             # AccessPolicy, capability tables
  records/
    domain/  application/  infrastructure/  api/
  main.py
tests/
  unit/                 # pure domain, no database
  scenarios/            # one test per brief scenario, real Postgres
scripts/
  seed.py  demo.py
```

### API surface (thin)

- `POST /auth/signup`, `POST /auth/login`, `POST /auth/refresh`, `POST /auth/logout`, `GET /me`
- `POST /invitations`, `POST /invitations/{token}/accept`
- `POST /orgs`, `POST /orgs/{id}/staff`, `POST /providers`
- `GET /care-teams/{id}` (filtered by viewer, optional `as_of`), `GET /care-teams/{id}/history`
- `POST /care-teams/{id}/members`, `POST .../members/{mid}/engagement`, `POST .../members/{mid}/end`
- `POST /care-teams/{id}/handoffs`, `POST /care-teams/{id}/coverages`, `POST .../coverages/{cid}/end`
- `GET /clients/{id}/records`, `POST /clients/{id}/records`
- `GET /access/explain`

### Testing

- **Unit tests** for every invariant and every value object, with no database.
- **Scenario tests** through the HTTP API against real Postgres, one per bullet in the brief plus the extra cases found, using a fixed `Clock`.
- **Seed and demo scripts** with synthetic people: client Maya, IronWorks Gym, a trainer, an independent physio and her covering colleague, a sports physician, a massage therapist. The demo prints each access decision with its reason.
- **import-linter** runs with the tests, so a boundary violation fails the build.

## Build order

Three days, one commit per step. The care team domain is built and tested before any persistence.

### Day 1: foundation

- [ ] Scaffold: docker compose, settings, FastAPI app, Alembic, `/health`
- [ ] Shared kernel: `TimeRange` and `Clock`, with tests
- [ ] Identity: signup, login, refresh, logout, `/me` with personas
- [ ] Directory: orgs, staff memberships, provider profiles, independent providers
- [ ] Invitations: hashed token, returned in the response instead of emailed

### Day 2: the core

- [ ] CareTeam domain model and invariant unit tests, no database
- [ ] Persistence: exclusion constraints, optimistic locking, repositories
- [ ] Commands: add member, change engagement, end membership, handoff, coverage
- [ ] `AccessPolicy` and `/access/explain`
- [ ] Thin `records` context calling the policy through its port

### Day 3: proof and writing

- [ ] Scenario tests, one per brief bullet plus the extra cases found
- [ ] Seed and demo scripts
- [ ] import-linter contract
- [ ] README: overview, setup, architecture, 3–5 key decisions, cuts and next steps
- [ ] Open questions and the migration write-up

## Migration, cuts and open questions

### Migration from one-provider-per-client (written up, not built)

A strangler migration, no big-bang cutover:

1. Backfill each legacy `client.provider_id` as a one-member care team holding both designations.
2. Translate legacy writes to `provider_id` into handoff commands (dual-write).
3. Run the new `AccessPolicy` in shadow mode and log every decision that disagrees with the old check.
4. Switch reads to the new policy behind a flag, then drop the legacy column.

### What we cut

- Scheduling, billing and messaging. Only the "can X?" decision exists.
- Episodes of care.
- A full consent workflow and client-specific access overrides.
- Guardians and proxies, and break-the-glass emergency access.
- Email sending, rate limiting, refresh-token reuse detection (revoking the whole session when an old refresh token is replayed).
- A real event bus; events are dispatched in-process.
