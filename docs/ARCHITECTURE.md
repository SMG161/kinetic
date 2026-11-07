# Kinetic Care Team: Architecture & Build Plan

## Overview

We build a small, deep slice of Kinetic: working identity and auth, plus a client-owned care team model that expresses every scenario in the brief. Most of the time goes into the care team. Scheduling, billing, messaging, documents and wearables are not built; they appear only on the context map to justify the boundaries.

**Stack:** Python, FastAPI, Pydantic, PostgreSQL, SQLAlchemy 2.0, Alembic, pytest, docker compose, uv.

**Deliverables:** running code, a README (overview, setup, architecture, 3–5 key decisions, cuts and next steps) and a list of open questions.

## Subdomains and bounded contexts

We build five bounded contexts: `identity`, `directory`, `care_team` (the core), `records` and `access`. Four more exist only on the map.

| Subdomain | Type | Context | Built? | Why |
|---|---|---|---|---|
| Care coordination | Core | `care_team` | Yes, deeply | What Kinetic sells: several providers serving one client without stepping on each other |
| Practice directory | Supporting | `directory` | Yes, thin | Orgs, staff, providers, clients. Needed, mostly CRUD with a few rules |
| Clinical records | Supporting | `records` | Yes, minimal | Exists so "see vs act" can be exercised and tested |
| Identity and authentication | Generic | `identity` | Yes, small | Every SaaS needs it; in production you would buy it |
| Authorization | Generic | `access` | Yes, small | One decision point every context calls, so a new context adds rules, not a new mechanism; the engine behind it can be swapped |
| Scheduling, Billing, Messaging, Documents/Wearables | Out of scope | none | No | Described in the README to justify the boundaries; they consume care_team events and decisions |

### Ubiquitous language per context

- **identity** (who someone is): Person, Account, Credential, Session. Hands everyone a `person_id` and nothing else.
- **directory** (what someone is in the business): Organization, StaffMembership (owner, admin, front desk, practitioner), Provider (qualified disciplines; independent unless a practitioner somewhere), Client, Client Relationship (an org serving a client), Practice Lead (the org's face and accountable person for that client), Invitation (an org bringing someone in as staff, a practitioner or a client). One person can hold several personas, all pointing at one `person_id`.
- **care_team** (the core): Care Team, Membership, Engagement, Coverage, Care Invitation (a solo provider inviting a client), Team Event. Supplies team facts to `access`.
- **records** (thin): Clinical Record, Record Category, Author. Append-only. Asks `access` for every decision.
- **access** (who may do what): Principal, Action, Resource, Decision (allowed, with a reason), Policy. Knows the rules, not the data: facts arrive through ports the other contexts implement.

The same word means different things per context, which is the reason the contexts are separate:

- **Provider** in `directory` is a professional with credentials and affiliations. In `care_team` the same person is only a **Member** with a discipline and an engagement level.
- **Client** in `directory` is a profile record. In `care_team` it is the subject the team exists for. In `identity` it is just a Person.
- **Organization** in `directory` is an entity with staff. In `care_team` it is only an **org context** stamped on a membership or record.
- **Lead** means one thing: the **Practice Lead** (`directory`), an org's face for a client. They handle that org's bookings and answer for that org's side of the care, and only that org's. They may be non-clinical. A solo provider is their own lead. The team has no team-wide designations (see "One face per organization").

### Context map

- **identity → everyone:** upstream; publishes `person_id`, which others accept as-is.
- **directory → care_team:** customer/supplier. `care_team` reads disciplines, practitioner memberships, client relationships and practice leads through its own `ProviderDirectory` port, an anti-corruption layer.
- **access ↔ everyone:** `access` defines the ports it needs (`TeamFacts`, `PracticeFacts`); `care_team` and `directory` implement them, and the composition root (`main.py`) wires the implementations in. Every protected endpoint calls `access` through its public module. So contexts depend on `access`, and `access` depends on none of them: dependency inversion, not a module that knows everything.
- **records → access:** records asks `access` for every read and write, passing the record's category and author.
- **care_team → scheduling/billing (stubs):** in-process domain events such as `CoverageScheduled`; billing asks `access` "can bill?".

```
 identity (generic) ──person_id──▶ directory (supporting)
        │                                │
        │                        ProviderDirectory port
        │                                ▼
        ├────────person_id────▶ care_team (core)        records (supporting)
        │                                │                      │
        │                  TeamFacts / PracticeFacts        decide()
        │                    (implemented here)                 │
        │                                ▼                      ▼
        └────────person_id────▶ access (generic): the policy decision point
                                         ▲
                                     decide()
                         ┌╌ Scheduling, Billing, Messaging (not built) ╌┐
```

Arrows point downstream. The dashed box is described in the README only.

Boundaries are enforced with one Postgres schema per context (no cross-schema foreign keys except to `identity.person`) and an **import-linter** contract: `care_team.domain` and `access.domain` import nothing outside themselves and the shared kernel, `access` imports no other context except `identity.public` (authentication comes before authorization), and contexts import each other only through a public module.

### Rejected boundaries

- **Authorization inside the core** (our first design): simpler, but every new context (scheduling, billing) would have to depend on `care_team` to ask a question, and swapping in an engine would mean editing the core. We chose a separate `access` context instead. The usual objection, that it needs facts from everywhere and ends up knowing everything, is answered by ports: `access` declares the facts it needs and the owning contexts supply them.
- **A separate consent context:** probably right in real healthcare; too much for three days. Listed as next.
- **Merging directory into care_team:** org staff management and team coordination change for different reasons; merging leaks gym-admin concerns into the core.
- **Episodes of care as a context:** more likely a future concept inside `care_team` that scopes memberships and records to one concern.

## Identity and authentication

Authentication and identity stay in one context, `identity`, modelled as two aggregates. Authorization lives elsewhere, in `access`.

### Authentication vs authorization

- **Authentication** (are you who you say you are?) lives in `identity`. It covers credentials, login and sessions, and ends by producing a `person_id`.
- **Authorization** (what may you do?) depends on team memberships, engagement, coverage windows and org staff roles. It lives in `access`, with `care_team` and `directory` supplying those facts through its ports.
- The one exception is managing an org itself (who may invite staff, practitioners or clients, and hand off a practice lead). That is a rule about directory's own data, so it stays an invariant of the `Organization` aggregate. With `access` separate it could move there without a cycle (directory would implement one more port); not done yet, listed as next.

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
- `POST /auth/signup` and `GET /me` combine identity with directory data (a Client profile, the personas). Identity is upstream and never imports directory, so these two routes live in `directory`'s API and call identity's public module. Whatever combines two contexts lives in the downstream one.

### Onboarding and invitations

- **Self-signup** creates a Person, an Account and either a Client profile or, when qualifications are given, a Provider profile (and no Client profile). A provider becomes a client only by accepting a client invitation.
- **Invitations are the only way into an org.** Nobody is added as staff, practitioner or client without accepting, so every org membership and client relationship carries that person's consent.
- **Org invitations** live in `directory`, because what they do (a staff membership, a provider profile, a client relationship) is directory data; identity only creates the account. Three kinds, issued by an org's owner or admin: staff, practitioner, client.
  - The token is 256 random bits, stored as a SHA-256 hash, valid for 7 days and usable once (a compare-and-swap update stops two acceptances).
  - Accepting applies the org's domain rules acting as the inviter, so the inviter's authority and the invitee's qualifications are re-checked. One transaction: if any rule fails, nothing is kept and the invitation stays pending.
  - An owner who also treats invites themselves as a practitioner and accepts: one path, no exception.
  - Signed in, you accept as yourself and your email must match. Not signed in, you give a name and password and an account is created for the invited email.
  - The token travels in the request body, never the URL, so it stays out of logs, browser history and `Referer` headers.
  - Invited staff and practitioners do not become clients; only a client invitation creates a Client profile, and accepting it is the client's consent to the relationship.
- **Care invitations** live in `care_team`: a solo provider invites a client, and accepting adds the provider to the client's care team with no org context. Any provider can send one, in a discipline they are qualified in, including one who also works at an org. The client accepts signed in, and access allows only the client to accept (`ACCEPT_CARE_INVITATION`): that acceptance is their consent. The token rules match org invitations (hashed, 7 days, once, for the invited email). To hire people, a provider founds an org and invites them.
- Email sending is stubbed: the token is returned in the API response and the README says so.

## The practice directory

`directory` knows what each person is in the business, and which organizations serve which clients.

### Model

| Element | Kind | Holds |
|---|---|---|
| `Organization` | Aggregate root | name, staff memberships |
| `StaffMembership` | Entity | person_id, role (`OWNER`, `ADMIN`, `FRONT_DESK`, `PRACTITIONER`), disciplines practised here (practitioners only) |
| `Provider` | Aggregate root | person_id, qualified disciplines |
| `Client` | Aggregate root | person_id |
| `ClientRelationship` | Aggregate root | org_id, client_id, `TimeRange`, practice lead assignments |
| `PracticeLeadAssignment` | Entity | staff person_id, `TimeRange`, reason |
| `Discipline` | Value object | `TRAINER`, `PHYSIO`, `PHYSICIAN`, `MASSAGE`, `NUTRITION` |

A provider is **independent** if they hold no practitioner membership. A clinic owner who also treats holds two staff memberships at the same org: `OWNER` and `PRACTITIONER`.

### Invariants

1. Whoever creates an organization becomes its `OWNER`. Only an owner or admin may invite staff, practitioners or clients; staff join as admin, front desk or practitioner, never as a second owner.
2. A person holds each role at an org at most once.
3. A practitioner's disciplines at an org are a subset of their provider qualifications.
4. At most one active client relationship per (org, client).
5. While a relationship is active it has exactly one practice lead, who is staff of that org in any role (non-clinical is allowed). Changing the lead closes one assignment and opens the next at the same instant: no gap, no overlap.
6. A staff member cannot leave an org while they are a practice lead there, unless the same command hands the lead off. (Removing staff is not built yet, so this cannot be broken today.)
7. A client is never their own practice lead, for the same reason as care team invariant 7.

Invariants 4 and 5 are also enforced in Postgres with exclusion constraints on `tstzrange(valid_from, valid_to)`, so two admins handing off at the same moment cannot both succeed.

A relationship starts only when the client accepts the org's client invitation. **Rejected, a direct "walk-in" start by an admin:** it would put a client in an org without their say. Ending a relationship arrives with the care team's discharge command, which must close the org's memberships in the same transaction.

### Why client relationships live here, not in the care team

Considered: a `PracticeTeam` entity inside `CareTeam`, one per org, holding the practice lead. Rejected because:

- The brief's client "belongs to a gym" even when no gym provider treats her. That is a business relationship, not care, and an empty practice team would be needed to say it.
- An independent provider would need a practice team of one.
- A non-clinical practice lead is the org running its business. Putting it in the core is the gym-admin leak the rejected boundaries warn about.

What we gave up, and how it is recovered: a practice team could be discharged in one step. Here `care_team` has a **discharge organization** command that ends that org's memberships and the client relationship in the same database transaction (`care_team` may call directory's public module; both run in one request transaction).

## The care team (core)

The team is **of the client**: each client has exactly one `CareTeam`, owned by no organization. Each membership records the org (or none) the provider serves the client on behalf of.

### Why the client

- The client is the only thing that stays the same across every org.
- **Rejected, org-owned case:** it cannot hold the independent physio without the gym "owning" a provider who doesn't work for it.
- **Rejected, episode-of-care aggregate:** the trainer's relationship and the practice lead span episodes. Episodes are a "what's next" item inside this context.

### Aggregate shape

`CareTeam` is the aggregate root. It is small (a handful of members), so it is loaded whole.

| Element | Kind | Holds |
|---|---|---|
| `CareTeam` | Aggregate root | client_id, version, the entities below |
| `Membership` | Entity | provider_id, discipline, org_context_id or null, engagement, reason, `TimeRange` |
| `Coverage` | Entity | covered_membership_id, covering_provider_id, `TimeRange`, reason, cancelled_at |
| `TeamEvent` | Recorded with every command | actor, reason, at, event type |
| `TimeRange` | Value object | half-open `[from, to)` |
| `Engagement` | Value object | `ACTIVE`, `CONSULTING`, `ALUMNI` |
| `Discipline`, `Reason`, `Capability` | Value objects | provider profession; why; an allowed action |

`care_team` keeps its own `Discipline`; the `ProviderDirectory` adapter translates directory's, so a rename there never reaches the core.

### Invariants

Each invariant gets a unit test.

1. One care team per client.
2. A provider never has two overlapping memberships on the same team.
3. Periods are never mutated, only closed and reopened. A change of engagement closes the current period and opens a new one at the same instant; nothing is deleted.
4. Coverage falls inside the covered membership's period; the covering provider is not the covered provider and is qualified in the covered membership's discipline; one membership has no overlapping coverages. Ending a membership closes its running coverage at the same instant and cancels any that have not started.
5. Every command records a `TeamEvent` with actor, reason and time.
6. A membership's org context is an org where the provider is a practitioner in that discipline and which has an active client relationship with the client; with no org context, the provider must be qualified in the discipline. Checked through the `ProviderDirectory` port when the member is added.
7. A client is never a member of, nor a cover on, their own care team. Self-treatment would make the subject of the records also their practitioner, so "who may see and act" turns circular.

Invariant 1 spans aggregates, so a unique constraint enforces it. Invariant 2 is also enforced in Postgres with an exclusion constraint (needs `btree_gist`):

```sql
EXCLUDE USING gist (team_id WITH =, provider_id WITH =, tstzrange(valid_from, valid_to) WITH &&)
```

A `version` column on `care_team` gives optimistic locking, so two concurrent commands on one team cannot both succeed.

### Commands and who may issue them

Add member, change engagement, end membership, schedule coverage, end coverage, discharge an organization. Each org runs its own side of the team, and nobody manages another org's people.

| Who | May |
|---|---|
| The client | Accept org and care invitations (their consent to be served); discharge an org or end a solo provider's membership; always see their own team and its history |
| An org's practice lead for the client | Add, end and change engagement of memberships in their org's context; schedule and end coverage for them; discharge their org |
| A solo provider | Join by care invitation; change their own membership's engagement, schedule cover for it, end it |
| Anyone else, including covering providers and org admins | Nothing on the team |

Members in an org's context join when the practice lead adds them; the client consented to that org by accepting its invitation. Scheduling a coverage is the approval: there is no request-and-review step.

Discharging an organization closes every membership in that org's context at time t and ends the client relationship in the same transaction.

### One face per organization

The brief has one provider as the "face" the client books through, possibly not the one clinically responsible. We give each org its own face: its practice lead, who handles that org's bookings and answers for that org's side of the care. A solo provider is their own face.

**Rejected, team-wide designations (a booking contact and a clinical lead for the whole team):** a gym trainer cannot realistically run a clinic's diary or answer for its clinicians, and an automatically chosen holder would be asked to. The trade-off: a client served by three orgs has three places to book, not one. The brief's scenario still holds per org: the face (the practice lead, often non-clinical) differs from the provider doing the treatment, either can change, and both changes close one period and open the next at the same instant.

### Coverage semantics

During the window, the covering provider gets the covered member's capabilities except managing the team. Access ends because the policy evaluates the window at request time. No background job revokes anything.

The covering provider need not belong to the covered member's org (an independent physio's colleague usually does not). While covering they act under the covered membership's org context, so they see that org's slice and nothing else.

### History

Closed periods plus `TeamEvent` rows keep who was on the team, in what role, when and why. `GET /care-teams/{id}?as_of=<timestamp>` reconstructs the team at any instant, including each org's practice lead at that instant (read through the `ProviderDirectory` port, since lead assignments keep their own periods in `directory`). **Rejected, event sourcing:** too costly for three days; current-state tables, append-only periods and an event table give "keep, don't overwrite" at a fraction of the cost.

### How each scenario is expressed

| Scenario | Expression in the model |
|---|---|
| Trainer, physio and physician at once | Three concurrent `ACTIVE` memberships with different disciplines and org contexts |
| The "face" is not the clinical lead | Per org: the practice lead is the face, the treating provider's membership is separate, and each changes on its own (see "One face per organization") |
| Two-week coverage, then handback | A `Coverage` with a window; access is computed at request time; handback ends the coverage |
| Physio steps back after rehab | `ACTIVE` period closes, `CONSULTING` period opens with a reason; history intact |
| Physician sees, massage therapist doesn't | Discipline decides record categories (Access policy section) |
| Gym client with an independent physio | A `ClientRelationship` says the gym serves her, even with no gym provider on the team; the physio joins by care invitation with no org context; org admins and practice leads see only their org's slice |
| History is kept | Closed periods, `TeamEvent`s, practice lead assignments and the `as_of` query |

### Extra cases found

| Case | Expression in the model |
|---|---|
| Who at the gym is accountable for this client? | The relationship's practice lead, possibly non-clinical |
| The practice lead goes on leave | The org hands the lead to another staff member; history keeps both periods |
| A physio leaves the gym, goes independent and keeps the client | Her gym-context membership closes and a new one opens with no org context; history intact |
| The gym stops serving the client, or the client leaves | Discharge organization, by the gym's practice lead or the client: its memberships and the relationship end at the same instant |
| A provider works at a gym and also sees clients on their own | One membership per team: a gym-context membership on one client's team, a solo one on another's |
| An independent physio's colleague covers | Coverage needs no shared org; the cover acts under the covered membership's org context |
| A clinic owner also treats the client | Two staff memberships at one org (`OWNER`, `PRACTITIONER`); only the practitioner one lets them join a care team on that org's behalf |
| A front desk worker is also a client of the gym | The gym can serve her, but someone else must be her practice lead (directory invariant 7) |
| A physio who is also a client | One person with a Client and a Provider profile. She may treat others but never join her own team (invariant 7) |
| A gym trainer who is also a client of the same gym | The gym has a client relationship with her and a practitioner membership for her. Her own records are visible to her as the client, never through her trainer role |

## Access policy (the `access` context)

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
| Physician, physio | `MEDICAL_HISTORY`, `ASSESSMENT`, `ASSESSMENT_SUMMARY`, `CLINICAL_NOTE`, `SESSION_NOTE`, `TRAINING_PLAN` |
| Trainer | `TRAINING_PLAN`, `SESSION_NOTE`, `ASSESSMENT_SUMMARY` |
| Massage | `MASSAGE_PLAN`, `SESSION_NOTE` |
| Nutrition | `NUTRITION_PLAN`, `SESSION_NOTE` |

`SESSION_NOTE` is non-clinical; `CLINICAL_NOTE` is clinical. Writing a note needs the same category to be visible. The client sees all of their own records and acts on none; a practice lead gets no records from being a lead.

This separates "see" from "act" naturally. The physio stepping back after rehab is only a change from `ACTIVE` to `CONSULTING`, and no table changes.

### One decision point

`decide(principal, action, resource, at) -> Decision(allowed, reason)` lives in `access`, split the standard way:

| Part | What it is | Where |
|---|---|---|
| **PDP** (decision point) | The rules: who may manage a team (see "Commands and who may issue them"), engagement → actions, discipline → record categories, coverage windows | `access.domain`, pure Python |
| **PIP** (information points) | Ports `access` defines for the facts it needs: `TeamFacts` (memberships, engagement, coverage), `PracticeFacts` (practice leads at an instant) | Implemented by `care_team` and `directory`, wired in `main.py` |
| **PEP** (enforcement point) | A FastAPI dependency every protected endpoint goes through; a denial becomes 403 with the reason | `access.public` |

- No other code decides access. A context may check its own aggregate's invariants, never who may see or act.
- `at` comes from an injected `Clock`, so tests can move time ("day 15: the cover is denied").
- Every decision carries a **reason**, such as "denied: coverage ended at 2026-11-17". An `/access/explain` endpoint shows it, which makes a strong walkthrough demo.
- `access` stores nothing. Every decision is computed from current facts at request time, so a revoked membership or an ended coverage never leaves stale access behind.
- `access` owns the policy; `care_team` owns the facts and what they mean (what an engagement is, when a coverage ends).

### Extending it

- **A new context** (scheduling, billing): add its actions to the policy and call the same PEP. No other context changes.
- **A new kind of fact:** add a port to `access`; the owning context implements it.
- **An off-the-shelf engine** (OpenFGA, SpiceDB, Cedar) when the rules outgrow code, e.g. per-tenant custom roles or consent: replace the PDP's insides behind `decide()`. Callers and ports stay as they are; care teams are naturally a graph of relationships, which these engines model well.
- **Contexts as separate services:** facts would arrive as events (membership added, coverage scheduled) and `access` would keep its own copy. Time windows are still checked at request time, so a stale copy never grants access.
- **Migrating any of these:** run old and new side by side in shadow mode, log every disagreement, then switch behind a flag.

### Cross-organization rules

- Memberships carry an `org_context_id` (null for an independent provider). Records do not yet: visibility is decided by discipline and engagement, so nothing would read it (see cuts).
- An org admin sees team membership and records only within their own org's context, never the independent physio's notes.
- A practice lead sees their org's slice of the team's membership and history. Being a lead grants no clinical record access; a lead who also treats the client gets that through their own membership.
- The discipline that decides record categories is the membership's, i.e. what the provider practises for this client, not every discipline they are qualified in.
- The client always sees their own team and its history.

### Principals

The principal is resolved from the session token to `person_id`, then to personas: client profile, provider profile, staff memberships. A person can act as client of their own team and as provider on someone else's. Nothing about who someone is or what they may do comes from the request body.

There is no "switch persona" step. The policy looks at every persona the principal holds and asks which of them relates to the resource: on Maya's own team she is the client; on another client's team she is that team's trainer and only trainer rules apply. The resource decides which relationship counts, never a role the caller picks.

## Stack, persistence, layout and testing

The domain is pure Python; SQLAlchemy lives only in each context's infrastructure layer.

### Decisions

- **SQLAlchemy 2.0, mapped by repositories.** Domain classes are plain dataclasses; repositories map to and from ORM table models. **Rejected:** ORM models as domain models, which is faster but leaks persistence into the domain.
- **Alembic** for migrations, including the `btree_gist` extension and exclusion constraints.
- **One Postgres schema per context** (`identity`, `directory`, `care_team`, `records`). `access` stores nothing, so it has none.
- **Postgres-specific features used on purpose:** `tstzrange`, exclusion constraints and a `version` column for optimistic locking.
- **Tooling:** uv for packages, docker compose for Postgres, plain commands (listed in the README) for migrate, seed, demo and test.

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
  records/
    domain/  application/  infrastructure/  api/
  access/
    domain/             # the PDP: rules, Decision, fact ports
    application/  api/  # gathers facts, the PEP dependency, /access/explain
    public.py           # no infrastructure: facts come through ports others implement
  main.py               # composition root: wires the fact adapters into access
tests/
  unit/                 # pure domain, no database
  scenarios/            # one test per brief scenario, real Postgres
scripts/
  seed.py  demo.py
```

### API surface (thin)

- `POST /auth/signup`, `POST /auth/login`, `POST /auth/refresh`, `POST /auth/logout`, `GET /me`
- `POST /orgs/{id}/invitations`, `POST /invitations/accept` (token in the body)
- `POST /orgs`, `POST /providers`
- `POST /orgs/{id}/clients/{cid}/practice-lead` (hand the lead off), `GET /orgs/{id}/clients/{cid}` (the relationship and its lead history, for the org's staff)
- `POST /care-invitations`, `POST /care-invitations/accept` (a solo provider invites a client)
- Care team, addressed by client (one team per client): `GET /clients/{cid}/care-team` (filtered by the viewer's scope, optional `as_of`), `GET .../care-team/history`
- `POST .../care-team/members`, `POST .../members/{mid}/engagement`, `POST .../members/{mid}/end`
- `POST .../members/{mid}/coverages`, `POST .../members/{mid}/coverages/{cov}/end`
- `POST .../care-team/orgs/{org_id}/discharge` (also ends the org's client relationship, in the same transaction)
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

- [x] Scaffold: docker compose, settings, FastAPI app, Alembic, `/health`
- [x] Shared kernel: `TimeRange` and `Clock`, with tests
- [x] Identity: signup, login, refresh, logout, `/me` (personas arrive with directory)
- [x] Directory: orgs, staff memberships (including practitioners), provider profiles, client profiles, client relationships with practice leads, personas on `/me`
- [x] Invitations: hashed token, returned in the response instead of emailed

### Day 2: the core

- [x] Directory revision: invitations are the only way into an org; signup as a provider
- [x] CareTeam domain model and invariant unit tests, no database
- [x] Persistence: exclusion constraints, optimistic locking, repositories
- [x] `access` context: the policy (PDP) and its fact ports, unit-tested, no endpoints yet
- [x] Commands: directory's public module, the `ProviderDirectory` port, care team service and endpoints behind the PEP, `as_of`, `/access/explain`
- [x] Care invitations: a solo provider invites a client
- [x] Thin `records` context asking `access` for every decision

### Day 3: proof and writing

- [ ] Scenario tests, one per brief bullet plus the extra cases found
- [ ] Seed and demo scripts
- [ ] import-linter contract
- [ ] README: overview, setup, architecture, 3–5 key decisions, cuts and next steps
- [ ] Open questions and the migration write-up

## Migration, cuts and open questions

### Migration from one-provider-per-client (written up, not built)

A strangler migration, no big-bang cutover:

1. Backfill each legacy `client.provider_id` as a one-member care team: a membership in the provider's org context, or a solo one.
2. Translate legacy writes to `provider_id` into end-membership and add-member commands at the same instant (dual-write).
3. Run the new `access` policy in shadow mode and log every decision that disagrees with the old check.
4. Switch reads to the new policy behind a flag, then drop the legacy column.

### What we cut

- Scheduling, billing and messaging. Only the "can X?" decision exists.
- Episodes of care.
- A full consent workflow and client-specific access overrides.
- A client requesting changes to an org's side of their team; today they can only discharge the org.
- Coverage requests with a review step; the practice lead or solo provider schedules a cover directly.
- Accepting a care invitation as a brand-new person; the client signs up first, then accepts signed in.
- An org context on records. It would matter once an org's records should follow it out on discharge (an open question).
- Guardians and proxies, and break-the-glass emergency access.
- Email sending, rate limiting, refresh-token reuse detection (revoking the whole session when an old refresh token is replayed).
- A real event bus; events are dispatched in-process.
- Credential verification: anyone can register as a provider with any discipline.

### Open questions (where the brief was silent)

- Should a practice lead have to be clinical, or is a non-clinical coordinator enough? We allow non-clinical.
- May an org admin or a covering provider manage the team? We say no.
- Is one face per organization enough, or does Kinetic want a single front door across the whole team?
- Must the client approve a covering provider, who gains access to their records for the window? We say no.
- When an org stops serving a client, should its providers' records stay visible to the rest of the team?
- Who verifies a provider's credentials before they can join a care team?
