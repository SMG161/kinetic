"""SQLAlchemy repository for the care team: maps rows to the domain and back.

The team is loaded and saved whole. Saving bumps the team's version only if it still
matches the version that was loaded (compare-and-swap), so two people changing the
same team at once cannot both succeed: the second gets ConcurrentChange.
"""

from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from kinetic.care_team.domain.errors import ConcurrentChange, TeamAlreadyExists
from kinetic.care_team.domain.facts import Discipline
from kinetic.care_team.domain.model import CareTeam, Coverage, Engagement, Membership, TeamEvent, TeamEventType
from kinetic.care_team.infrastructure.tables import CareTeamRow, CoverageRow, MembershipRow, TeamEventRow
from kinetic.shared_kernel import ClientId, OrganizationId, PersonId, ProviderId, TimeRange


class SqlCareTeamRepository:
    def __init__(self, db: DbSession) -> None:
        self._db = db

    def add(self, team: CareTeam) -> None:
        self._db.add(CareTeamRow(id=team.id, client_id=team.client_id, version=team.version))
        try:
            self._db.flush()  # the team row must exist before its children reference it
        except IntegrityError as error:
            # The unique client_id: another request created this client's team first.
            raise TeamAlreadyExists("this client already has a care team") from error
        self._write_children(team)

    def get(self, team_id: UUID) -> CareTeam | None:
        row = self._db.get(CareTeamRow, team_id)
        return self._load(row) if row else None

    def get_by_client(self, client_id: ClientId) -> CareTeam | None:
        row = self._db.scalar(select(CareTeamRow).where(CareTeamRow.client_id == client_id))
        return self._load(row) if row else None

    def save(self, team: CareTeam) -> None:
        bumped = self._db.execute(
            update(CareTeamRow)
            .where(CareTeamRow.id == team.id, CareTeamRow.version == team.version)
            .values(version=team.version + 1)
            .execution_options(synchronize_session=False)
        )
        if bumped.rowcount != 1:
            raise ConcurrentChange("someone else changed this care team; reload and try again")
        self._write_children(team)
        team.version += 1

    # ---- Writing ----

    def _write_children(self, team: CareTeam) -> None:
        """Close what was closed first, then add what is new, so a period closed at t and
        its successor opened at t never overlap, even for a moment."""
        try:
            new_memberships = self._close_memberships(team)
            new_coverages = self._close_coverages(team)
            self._db.flush()
            self._db.add_all(new_memberships)
            self._db.flush()
            self._db.add_all(new_coverages)
            self._db.add_all(self._new_events(team))
            self._db.flush()
        except IntegrityError as error:
            # An exclusion constraint caught an overlap two concurrent requests both missed.
            raise ConcurrentChange("the care team changed at the same time; reload and try again") from error

    def _close_memberships(self, team: CareTeam) -> list[MembershipRow]:
        new = []
        for m in team.memberships:
            row = self._db.get(MembershipRow, m.id)
            if row is None:
                new.append(
                    MembershipRow(
                        id=m.id,
                        team_id=team.id,
                        provider_id=m.provider_id,
                        discipline=m.discipline,
                        org_context_id=m.org_context,
                        engagement=m.engagement,
                        reason=m.reason,
                        valid_from=m.period.start,
                        valid_to=m.period.end,
                    )
                )
            else:
                row.valid_to = m.period.end  # the only thing a stored membership can change
        return new

    def _close_coverages(self, team: CareTeam) -> list[CoverageRow]:
        new = []
        for c in team.coverages:
            assert c.window.end is not None  # every coverage has an end
            row = self._db.get(CoverageRow, c.id)
            if row is None:
                new.append(
                    CoverageRow(
                        id=c.id,
                        covered_membership_id=c.covered_membership_id,
                        covering_provider_id=c.covering_provider_id,
                        reason=c.reason,
                        valid_from=c.window.start,
                        valid_to=c.window.end,
                        cancelled_at=c.cancelled_at,
                    )
                )
            else:
                row.valid_to, row.cancelled_at = c.window.end, c.cancelled_at  # ended early, or cancelled
        return new

    def _new_events(self, team: CareTeam) -> list[TeamEventRow]:
        stored = set(self._db.scalars(select(TeamEventRow.id).where(TeamEventRow.team_id == team.id)))
        return [
            TeamEventRow(
                id=e.id,
                team_id=team.id,
                type=e.type,
                actor_id=e.actor,
                reason=e.reason,
                at=e.at,
                subject_id=e.subject_id,
            )
            for e in team.events
            if e.id not in stored
        ]

    # ---- Reading ----

    def _load(self, row: CareTeamRow) -> CareTeam:
        membership_rows = self._db.scalars(
            select(MembershipRow).where(MembershipRow.team_id == row.id).order_by(MembershipRow.valid_from)
        ).all()
        coverage_rows = self._db.scalars(
            select(CoverageRow)
            .join(MembershipRow, CoverageRow.covered_membership_id == MembershipRow.id)
            .where(MembershipRow.team_id == row.id)
            .order_by(CoverageRow.valid_from)
        ).all()
        event_rows = self._db.scalars(
            select(TeamEventRow).where(TeamEventRow.team_id == row.id).order_by(TeamEventRow.seq)
        ).all()
        return CareTeam(
            id=row.id,
            client_id=ClientId(row.client_id),
            memberships=[_membership(m) for m in membership_rows],
            coverages=[_coverage(c) for c in coverage_rows],
            events=[_event(e) for e in event_rows],
            version=row.version,
        )


def _membership(row: MembershipRow) -> Membership:
    return Membership(
        id=row.id,
        provider_id=ProviderId(row.provider_id),
        discipline=Discipline(row.discipline),
        org_context=OrganizationId(row.org_context_id) if row.org_context_id else None,
        engagement=Engagement(row.engagement),
        reason=row.reason,
        period=TimeRange(row.valid_from, row.valid_to),
    )


def _coverage(row: CoverageRow) -> Coverage:
    return Coverage(
        id=row.id,
        covered_membership_id=row.covered_membership_id,
        covering_provider_id=ProviderId(row.covering_provider_id),
        window=TimeRange(row.valid_from, row.valid_to),
        reason=row.reason,
        cancelled_at=row.cancelled_at,
    )


def _event(row: TeamEventRow) -> TeamEvent:
    return TeamEvent(
        id=row.id,
        type=TeamEventType(row.type),
        actor=PersonId(row.actor_id),
        reason=row.reason,
        at=row.at,
        subject_id=row.subject_id,
    )
