"""care_team's side of access's TeamFacts port: the client's team, in access's vocabulary.

Translates as it goes: provider ids become person ids (the principal is a person), and
care_team's Discipline and Engagement become access's. Cancelled coverages are left out.
"""

from kinetic.access.public import AccessDiscipline, AccessEngagement, CoverView, MemberView, TeamView
from kinetic.care_team.domain.repositories import CareTeamRepository
from kinetic.directory.public import DirectoryLookup
from kinetic.shared_kernel import ClientId, PersonId, ProviderId


class CareTeamAccessFacts:
    def __init__(self, teams: CareTeamRepository, directory: DirectoryLookup) -> None:
        self._teams = teams
        self._directory = directory

    def team(self, client_id: ClientId) -> TeamView | None:
        client_person = self._directory.person_of_client(client_id)
        if client_person is None:
            return None
        team = self._teams.get_by_client(client_id)
        if team is None:
            return TeamView(client_id, client_person, members=(), covers=())
        members = tuple(
            MemberView(
                membership_id=m.id,
                person_id=self._person(m.provider_id),
                discipline=AccessDiscipline(m.discipline.value),
                org_context=m.org_context,
                engagement=AccessEngagement(m.engagement.value),
                period=m.period,
            )
            for m in team.memberships
        )
        covers = tuple(
            CoverView(c.covered_membership_id, self._person(c.covering_provider_id), c.window)
            for c in team.coverages
            if c.is_live
        )
        return TeamView(client_id, client_person, members, covers)

    def _person(self, provider_id: ProviderId) -> PersonId:
        person = self._directory.person_of_provider(provider_id)
        if person is None:  # provider profiles are never deleted, so this is a broken invariant
            raise LookupError(f"provider {provider_id} has no profile in directory")
        return person
