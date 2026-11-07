"""SQLAlchemy repository for care invitations."""

from sqlalchemy import select, update
from sqlalchemy.orm import Session as DbSession

from kinetic.care_team.domain.facts import Discipline
from kinetic.care_team.domain.invitations import CareInvitation
from kinetic.care_team.infrastructure.tables import CareInvitationRow
from kinetic.shared_kernel import PersonId, ProviderId, TimeRange


class SqlCareInvitationRepository:
    def __init__(self, db: DbSession) -> None:
        self._db = db

    def add(self, invitation: CareInvitation) -> None:
        assert invitation.valid.end is not None  # every invitation expires
        self._db.add(
            CareInvitationRow(
                id=invitation.id,
                provider_id=invitation.provider_id,
                client_email=invitation.client_email,
                discipline=invitation.discipline,
                reason=invitation.reason,
                token_hash=invitation.token_hash,
                created_at=invitation.valid.start,
                expires_at=invitation.valid.end,
            )
        )
        self._db.flush()

    def get_by_token_hash(self, token_hash: str) -> CareInvitation | None:
        row = self._db.scalar(select(CareInvitationRow).where(CareInvitationRow.token_hash == token_hash))
        if row is None:
            return None
        return CareInvitation(
            id=row.id,
            provider_id=ProviderId(row.provider_id),
            client_email=row.client_email,
            discipline=Discipline(row.discipline),
            reason=row.reason,
            token_hash=row.token_hash,
            valid=TimeRange(row.created_at, row.expires_at),
            accepted_at=row.accepted_at,
            accepted_by=PersonId(row.accepted_by) if row.accepted_by else None,
        )

    def mark_accepted(self, invitation: CareInvitation) -> bool:
        # Compare-and-swap: if two requests accept at once, only one row update matches.
        result = self._db.execute(
            update(CareInvitationRow)
            .where(CareInvitationRow.id == invitation.id, CareInvitationRow.accepted_at.is_(None))
            .values(accepted_at=invitation.accepted_at, accepted_by=invitation.accepted_by)
        )
        return result.rowcount == 1
