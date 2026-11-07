# Kinetic Care Team

A backend for a client served by a team of providers across organizations: who is on the team, in what role, who may see and do what, and how all of that changes over time without losing history.

The full design, including every rule below in more detail, is in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Project overview

**What I built:** working identity and authentication, a directory of organizations, providers and clients, and a client-owned care team, with a single access decision point that everything else asks. A thin records context exists so that "who can see" and "who can act" can be exercised on real data.

**The scope I chose:** depth on the care team and access. Scheduling, billing, messaging, documents and wearables are not built; they appear only on the context map, to justify the boundaries. All data is synthetic.

**Stack:** Python 3.13, FastAPI, Pydantic, PostgreSQL 17, SQLAlchemy 2.0, hand-written Alembic migrations, pytest, uv. I chose an ORM mapped by repositories so that domain classes stay plain dataclasses, and used Postgres directly for what it does best: exclusion constraints on time ranges.

## Setup

You need Docker and [uv](https://docs.astral.sh/uv/).

```bash
cp .env.example .env
uv sync
docker compose up -d --wait
uv run python -m alembic upgrade head
```

`.env.example` holds a placeholder JWT secret for local use only. Anywhere else, generate your own:

```bash
uv run python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Postgres runs on host port 5433, so it does not clash with a local install.

On Windows, keep the `python -m` form shown here: `uv run <tool>` can fail with "uv trampoline failed to canonicalize script path".

### Exercising it

```bash
uv run python -m pytest                                  # all tests; scenarios need Postgres running
uv run python scripts/seed.py --reset                    # empties the dev database and fills it with synthetic data
uv run python -m uvicorn kinetic.main:app --port 8000    # serve
```

Then open:

- **http://localhost:8000/demo/** for a plain page over the real API: one-click sign-in as each seeded person, the care team, records, and an Explain box showing any access decision with its reason. It is the quickest way to see the system.
- **http://localhost:8000/docs** for the generated API docs.

Invitation tokens are returned in the API response rather than emailed. Sending email is stubbed out.

## Architecture overview

### Bounded contexts

| Context | Owns | Language |
|---|---|---|
| `identity` (generic) | Who someone is, and signing in | Person, Account, Session |
| `directory` (supporting) | What someone is in the business | Organization, Staff Membership, Provider, Client, Client Relationship, Practice Lead, Invitation |
| `care_team` (core) | Several providers serving one client | Care Team, Membership, Engagement, Coverage, Care Invitation, Team Event |
| `records` (supporting, thin) | Notes about a client | Clinical Record, Record Category, Author |
| `access` (generic) | Who may see or do what | Principal, Action, Target, Decision, Policy |

Words deliberately mean different things per context: a **Provider** in `directory` is a professional with credentials, while in `care_team` the same person is a **Member** with a discipline and an engagement level. An **Organization** in `directory` has staff; in `care_team` it is only an org context stamped on a membership.

```
 identity ──person_id──▶ directory ──ProviderDirectory port──▶ care_team        records
    │                        │                                     │               │
    │                  PracticeFacts                           TeamFacts       decide()
    │                 (implements port)                     (implements port)      │
    │                        ▼                                     ▼               ▼
    └─── person_id ────────────────────▶  access: the policy decision point  ◀─────┘
                                                     ▲
                                                 decide()
                            ┌╌ Scheduling, Billing, Messaging (not built) ╌┐
```

Each context has its own Postgres schema, with no foreign keys between schemas except to `identity.person`. Contexts reach each other only through a `public` module or a port. This is enforced, not just intended: ten [import-linter](pyproject.toml) contracts run as a test, so a boundary violation fails the build.

### The care team

`CareTeam` is the aggregate root, one per client, loaded whole.

| Element | Kind | Holds |
|---|---|---|
| `CareTeam` | Aggregate root | client, version, and the entities below |
| `Membership` | Entity | provider, discipline, org context (empty for a solo provider), engagement, reason, period |
| `Coverage` | Entity | covered membership, covering provider, window, reason |
| `TeamEvent` | Entity | who did what, when and why |
| `TimeRange`, `Engagement`, `Discipline` | Value objects | half-open `[from, to)`; `ACTIVE`, `CONSULTING`, `ALUMNI`; a profession |

**Invariants:**

1. One care team per client (a unique constraint).
2. A provider never has two overlapping memberships on a team (domain, and a Postgres exclusion constraint).
3. Periods are never edited, only closed and reopened. Changing engagement closes one period and opens the next at the same instant.
4. A coverage falls inside the covered membership; the cover is someone else, qualified in that discipline; one membership has no overlapping live coverages (domain, and an exclusion constraint). Ending a membership ends its running coverage and cancels later ones.
5. Every command records a `TeamEvent`.
6. A membership's org must employ the provider in that discipline and must serve the client; with no org, the provider must be qualified.
7. A client is never a member of, nor a cover on, their own team.

**Lifecycle:** an org member joins when that org's practice lead adds them; the client consented to the org by accepting its invitation. A solo provider joins by care invitation, which the client accepts. A member moves between `ACTIVE`, `CONSULTING` and `ALUMNI`, each move closing one period and opening the next. A membership ends on its own, or with every other membership of that org when the org is discharged, which also ends the org's client relationship in the same transaction. Saves are a compare-and-swap on the team's version, so a stale copy is refused, not silently overwritten.

**Who runs the team:** each org runs its own side and nobody manages another org's people.

| Who | May |
|---|---|
| The client | Accept invitations (their consent); discharge an org; end a solo provider's membership; see their whole team |
| An org's practice lead | Add, change, end and cover memberships in their org's context; discharge their org; see their org's slice |
| A solo provider | Change, cover and end their own membership |
| Everyone else | Nothing on the team. Owning an org grants nothing on a client's team |

### Access

Access combines two small tables instead of one permissions matrix: **engagement** decides the action, and **discipline** decides the record categories. Allowed means both say yes.

| Engagement | View | Write | Run session | Message | Bill |
|---|---|---|---|---|---|
| `ACTIVE` | yes | yes | yes | yes | yes |
| `CONSULTING` | yes | no | no | yes | no |
| `ALUMNI` | own notes only | no | no | no | no |

`access` is split the standard way. The **decision point** is pure rules. The **information points** are ports it defines, which `care_team` and `directory` implement and `main.py` wires in. The **enforcement point** is a helper every protected endpoint calls, which turns a denial into a 403 carrying the reason. `access` stores nothing: each decision is computed at request time from current facts, so a cover loses access when the window ends, with no job to revoke anything.

A person's rights come from their relationship to the thing they are asking about, not a role they claim. The token holds only who they are, so nothing goes stale. A trainer who is also a client has client rights on their own team and trainer rights on someone else's.

### How the brief's scenarios are met

| Scenario | How | Test |
|---|---|---|
| Trainer, physio and physician at once | Three concurrent memberships across orgs | `test_care_team.py::test_trainer_physio_and_physician_at_once_across_orgs` |
| The "face" is not the one clinically responsible | Per org: the practice lead is the face, the treating provider's membership is separate, and each changes on its own (decision 2) | `test_client_relationships.py::TestHandingOffTheLead`, `test_extra_cases.py::test_a_physio_leaves_the_gym_goes_independent_and_keeps_the_client` |
| Two-week coverage, then handback | A coverage window, checked at request time | `test_care_team.py::test_two_week_coverage_then_handback`, `test_records.py::test_a_cover_writes_during_the_window_and_sees_nothing_after` |
| The physio steps back | `ACTIVE` closes, `CONSULTING` opens, history intact | `test_care_team.py::test_the_physio_steps_back_and_history_keeps_both_periods` |
| Physician sees, massage therapist doesn't; see vs act | The two tables, on real records | `test_records.py` |
| Gym client with an independent physio | A solo membership beside org ones; the gym's lead sees only the gym's slice | `test_care_invitations.py::test_maya_has_a_gym_trainer_and_an_independent_physio` |
| History is kept | Closed periods, team events, and `as_of` on the team view | `test_care_team.py::test_the_physio_steps_back_and_history_keeps_both_periods` |

### Extra cases found

The brief left these out, but the model has to answer them:

| Case | How | Test |
|---|---|---|
| Who at the gym is accountable for this client? | The relationship's practice lead, who may be non-clinical | `test_client_relationships.py::TestStartingARelationship::test_the_gym_serves_maya_with_a_non_clinical_practice_lead` |
| The practice lead goes on leave | The org hands the lead to another staff member; both periods are kept | `test_client_relationships.py::TestHandingOffTheLead::test_handoff_is_clean_and_history_is_kept` |
| A physio leaves the gym, goes independent and keeps the client | The gym membership closes and a solo one opens at the same instant | `test_extra_cases.py::test_a_physio_leaves_the_gym_goes_independent_and_keeps_the_client` |
| The gym stops serving the client, or the client leaves | Discharge, by the gym's lead or the client: its memberships and the relationship end together | `test_care_team.py::test_maya_discharges_the_gym` |
| A provider works at a gym and also sees clients solo | One membership per team: gym-run on one client's team, self-run on another's | `test_extra_cases.py::test_a_provider_works_at_a_gym_and_also_sees_clients_on_their_own` |
| An independent physio's colleague covers | Coverage needs no shared org | `test_extra_cases.py::test_an_independent_physios_colleague_covers_with_no_shared_org` |
| A clinic owner also treats the client | Two staff memberships at one org, `OWNER` and `PRACTITIONER` | `test_directory.py::TestPractitioners::test_a_clinic_owner_who_also_treats_invites_themselves` |
| A front desk worker is also a client of the gym | The gym can serve them, but someone else must be their practice lead | `test_client_relationships.py::TestStartingARelationship::test_a_client_cannot_be_their_own_practice_lead` |
| A physio who is also a client | One person with both profiles, who may treat others but never join their own team | `test_care_invitations.py::test_a_physio_who_is_also_a_client_cannot_join_her_own_team` |
| A gym trainer who is also a client of the same gym | Their own records are visible to them as the client, never through the trainer role | `test_extra_cases.py::test_a_gym_trainer_who_is_also_a_client_of_the_gym` |

## Key decisions and trade-offs

**1. The team belongs to the client, not to an organization or an episode.** The client is the only thing that stays the same across every org. An org-owned case cannot hold an independent physio without the gym "owning" someone who does not work for it. An episode-of-care aggregate does not fit either: a trainer relationship spans episodes. *Trade-off:* no org sees a whole team of its own, so each gets a slice, and the discharge of an org has to span two contexts in one transaction.

**2. One face per organization, not one for the whole team.** This is a deliberate departure from the brief's wording, which has one provider as the face the client books through. I started with team-wide designations for a booking contact and a clinical lead, and dropped them: a gym trainer cannot realistically run a clinic's diary or answer for its clinicians. Instead each org's practice lead is its face, and a solo provider is their own. The scenario still holds per org: the face (often non-clinical) differs from the provider treating, and either changes cleanly. *Trade-off:* a client served by three orgs has three places to book. It is the first thing I would confirm with you (see open questions).

**3. Authorization is its own context, reached through ports.** I first designed it inside `care_team`, since access rules come from team facts, but then every future context would depend on the core just to ask a question. The usual objection to a separate context is that it needs facts from everywhere and ends up knowing everything. Ports answer that: `access` declares the facts it needs and the owning contexts supply them, so it imports none of them. A new context adds rules, not a mechanism, and an engine like OpenFGA or Cedar could replace the rules behind `decide()` with callers untouched. *Trade-off:* a rule like "consulting members cannot write notes" lives away from the care team model. `access` owns the policy; `care_team` owns the facts and what they mean.

**4. Periods are closed, never edited, with an event log beside them.** "Keep, don't overwrite" is the brief's requirement. Half-open time ranges make a handoff exact: one period ends at the instant the next begins, so the answer is unambiguous at every moment, and Postgres enforces it under concurrency. *Rejected:* event sourcing, which gives the same history at far greater cost for three days of work. *Trade-off:* `TeamEvent`s are a record, not the source of truth, so they can in principle disagree with the tables, though both are written in one transaction.

**5. Short-lived JWTs that carry only identity.** A 15-minute access token holds who you are; a rotating, hashed refresh token keeps you signed in; rights are looked up per request. Roles in a token go stale: a cover would keep access after the window. *Trade-off:* logging out cannot recall an access token already issued, for up to 15 minutes. Opaque session tokens would revoke instantly, but JWT is what an external identity provider would issue, which keeps a later move to one cheap.

## What I cut and what's next

**Cut on purpose:**

- Scheduling, billing and messaging: only the "may they?" decision exists.
- A full consent workflow, client-specific access overrides, guardians, and break-the-glass access.
- A client requesting changes to an org's side of their team; today they can only discharge the org. Coverage requests with a review step; the lead schedules a cover directly.
- Accepting a care invitation as a brand-new person: the client signs up first.
- An org context on records: nothing reads it yet.
- Credential verification, email sending, rate limiting, and refresh-token reuse detection.
- Publishing events. `TeamEvent`s are recorded, but nothing consumes them.

**With more time, in order:**

1. Directory's "only an owner or admin manages the org" check is still an invariant inside the `Organization` aggregate. It could move into `access`, now that doing so creates no cycle.
2. Publish team events for scheduling and billing to consume.
3. Decide record visibility after discharge, which would bring org context onto records.
4. A consent context, which real healthcare would need.
5. Removing staff from an org, which is not built yet.

## Open questions

Where the brief was silent, these are what I would have asked, and what I assumed:

1. **Is one face per organization acceptable, or does Kinetic need a single front door across the whole team?** I assumed per org. A team-wide face could return later as a pointer to one of the existing practice leads.
2. **Who is clinically responsible across orgs?** The model has no team-wide clinical lead. Each treating provider answers for their own discipline.
3. **Must a practice lead be clinical?** I assumed not: a front desk coordinator can be one.
4. **Must the client approve a covering provider, who gains access to their records for the window?** I assumed not; the practice lead or solo provider decides.
5. **May an org admin or a covering provider manage the team?** I assumed not. Only the practice lead acts for the org, and owning an org grants nothing on a client's team.
6. **When an org stops serving a client, should its providers' records stay visible to the rest of the team?** They stay visible today.
7. **Who verifies a provider's credentials before they join a care team?** Nobody yet: anyone can claim a discipline.
8. **May a client walk in to an org without an invitation?** I assumed not: every join is by invitation, so consent is always recorded.

## Migrating from one-provider-per-client

Not built, but this is how I would move a live system onto this model without a big-bang cutover, using the strangler pattern:

1. **Backfill.** Turn each `client.provider_id` into a one-member care team: a membership in the provider's org context, or a solo one. Old and new now agree.
2. **Dual-write.** Keep the old column working, and translate each write to it into ending one membership and adding another at the same instant. History starts accruing.
3. **Shadow.** Run the new `access` policy beside the old check, serving the old answer and logging every disagreement. Each one is either a bug or a rule to decide on.
4. **Switch.** When disagreements are explained, move reads to the new policy behind a flag, one surface at a time. Then stop writing the column and drop it.

Each step can be rolled back on its own, and multi-provider teams only become possible once step 4 is complete.
