"""The care team repository against real Postgres: a team round-trips whole, one team
per client, a stale copy cannot overwrite a newer one, and the database itself refuses
the overlaps the domain forbids.

Lives with the scenario tests because they own the test database setup."""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from kinetic import db
from kinetic.care_team.domain.errors import ConcurrentChange, TeamAlreadyExists
from kinetic.care_team.domain.facts import ClientFacts, Discipline, ProviderFacts
from kinetic.care_team.domain.model import CareTeam, Engagement
from kinetic.care_team.infrastructure.repositories import SqlCareTeamRepository
from kinetic.shared_kernel import ClientId, OrganizationId, PersonId, ProviderId, TimeRange, new_person_id
from tests.scenarios.conftest import T0
from tests.scenarios.helpers import bearer, signup

DAY = timedelta(days=1)
GYM = OrganizationId(uuid4())
MAYA = ClientFacts(ClientId(uuid4()), new_person_id(), served_by=frozenset({GYM}))
TOM = ProviderFacts(ProviderId(uuid4()), new_person_id(), frozenset({Discipline.TRAINER}), {GYM: frozenset({Discipline.TRAINER})})
PIA = ProviderFacts(ProviderId(uuid4()), new_person_id(), frozenset({Discipline.PHYSIO}))
SAM = ProviderFacts(ProviderId(uuid4()), new_person_id(), frozenset({Discipline.PHYSIO}))


@contextmanager
def request() -> Iterator[SqlCareTeamRepository]:
    """One transaction, like one HTTP request: committed at the end, rolled back on error."""
    with db.get_session_factory().begin() as session:
        yield SqlCareTeamRepository(session)


@pytest.fixture
def ada(client) -> PersonId:
    """A real person to act in commands: team events reference identity.person."""
    headers = bearer(signup(client, "Ada Admin", "ada@ironworks.example"))
    return PersonId(UUID(client.get("/me", headers=headers).json()["id"]))


@pytest.fixture
def team(ada) -> CareTeam:
    team = CareTeam.for_client(MAYA)
    team.add_member(ada, TOM, MAYA, Discipline.TRAINER, GYM, Engagement.ACTIVE, "gym trainer", T0)
    pia = team.add_member(ada, PIA, MAYA, Discipline.PHYSIO, None, Engagement.ACTIVE, "shoulder rehab", T0)
    team.schedule_coverage(ada, pia.id, SAM, MAYA, TimeRange(T0 + 10 * DAY, T0 + 24 * DAY), "Pia on leave", T0)
    with request() as repo:
        repo.add(team)
    return team


def by_id(items: list) -> list:
    return sorted(items, key=lambda item: item.id)


def test_a_team_round_trips_whole(team):
    with request() as repo:
        loaded = repo.get_by_client(MAYA.client_id)
    assert loaded is not None
    assert (loaded.id, loaded.client_id, loaded.version) == (team.id, MAYA.client_id, 0)
    assert by_id(loaded.memberships) == by_id(team.memberships)
    assert loaded.coverages == team.coverages
    assert loaded.events == team.events  # in the order they happened


def test_changes_are_saved_and_the_version_moves_on(team, ada):
    with request() as repo:
        loaded = repo.get(team.id)
        pia = next(m for m in loaded.memberships if m.provider_id == PIA.provider_id)
        loaded.change_engagement(ada, pia.id, Engagement.CONSULTING, "rehab finished", T0 + 5 * DAY)
        repo.save(loaded)

    with request() as repo:
        reloaded = repo.get(team.id)
    assert reloaded.version == 1
    pias = sorted((m for m in reloaded.memberships if m.provider_id == PIA.provider_id), key=lambda m: m.period.start)
    assert [(m.engagement, m.period.end) for m in pias] == [
        (Engagement.ACTIVE, T0 + 5 * DAY),  # closed, not deleted
        (Engagement.CONSULTING, None),
    ]
    (coverage,) = reloaded.coverages
    assert coverage.cancelled_at == T0 + 5 * DAY  # it had not started when Pia's period closed
    assert reloaded.events == loaded.events


def test_one_team_per_client(team):
    with pytest.raises(TeamAlreadyExists):
        with request() as repo:
            repo.add(CareTeam.for_client(MAYA))


def test_a_stale_copy_cannot_overwrite_a_newer_one(team, ada):
    """Two people load the team, both change it. The first save wins; the second is refused
    instead of silently overwriting the first."""
    with request() as repo:
        first = repo.get(team.id)
    with request() as repo:
        second = repo.get(team.id)
    tom_id = next(m.id for m in first.memberships if m.provider_id == TOM.provider_id)

    first.end_membership(ada, tom_id, "Maya stopped training", T0 + 3 * DAY)
    with request() as repo:
        repo.save(first)

    second.change_engagement(ada, tom_id, Engagement.CONSULTING, "lighter plan", T0 + 4 * DAY)
    with pytest.raises(ConcurrentChange):
        with request() as repo:
            repo.save(second)

    with request() as repo:
        assert repo.get(team.id).version == 1


def insert(sql: str, **params) -> None:
    with db.get_engine().begin() as conn:
        conn.execute(text(sql), params)


def test_the_database_refuses_overlapping_memberships(team):
    """The safety net if two requests both add Pia: Postgres rejects the second period."""
    with pytest.raises(IntegrityError, match="one_membership_per_provider_at_a_time"):
        insert(
            "INSERT INTO care_team.membership"
            " (id, team_id, provider_id, discipline, engagement, reason, valid_from)"
            " VALUES (:id, :team, :provider, 'PHYSIO', 'ACTIVE', 'again', :at)",
            id=uuid4(), team=team.id, provider=PIA.provider_id, at=T0 + DAY,
        )


def test_the_database_refuses_overlapping_live_coverages_but_not_cancelled_ones(team):
    (coverage,) = team.coverages
    sql = (
        "INSERT INTO care_team.coverage"
        " (id, covered_membership_id, covering_provider_id, reason, valid_from, valid_to, cancelled_at)"
        " VALUES (:id, :membership, :provider, 'overlap', :start, :end, :cancelled)"
    )
    window = {"membership": coverage.covered_membership_id, "provider": uuid4(), "start": T0 + 12 * DAY, "end": T0 + 15 * DAY}
    with pytest.raises(IntegrityError, match="one_live_coverage_at_a_time"):
        insert(sql, id=uuid4(), cancelled=None, **window)
    insert(sql, id=uuid4(), cancelled=T0, **window)  # a cancelled coverage does not count
