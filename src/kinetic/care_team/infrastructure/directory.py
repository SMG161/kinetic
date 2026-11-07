"""The ProviderDirectory port, answered by identity's and directory's public modules.

This is the anti-corruption layer: directory's ProviderInfo and Discipline become
care_team's ProviderFacts and Discipline here, so changes in directory stop at this file.
"""

from collections.abc import Mapping
from datetime import datetime

from kinetic.care_team.domain.facts import ClientFacts, Discipline, ProviderFacts
from kinetic.directory.public import DirectoryLookup
from kinetic.identity.public import IdentityService
from kinetic.shared_kernel import ClientId, OrganizationId, PersonId


class DirectoryProviders:
    def __init__(self, lookup: DirectoryLookup, identity: IdentityService) -> None:
        self._lookup = lookup
        self._identity = identity

    def provider_by_email(self, email: str) -> ProviderFacts | None:
        person = self._identity.find_person_by_email(email)
        info = self._lookup.provider_by_person(person.id) if person else None
        if info is None:
            return None
        return ProviderFacts(
            provider_id=info.provider_id,
            person_id=info.person_id,
            qualifications=frozenset(Discipline(q.value) for q in info.qualifications),
            practises_at={
                org: frozenset(Discipline(d.value) for d in disciplines) for org, disciplines in info.practises_at.items()
            },
        )

    def client(self, client_id: ClientId, at: datetime) -> ClientFacts | None:
        info = self._lookup.client(client_id, at)
        return ClientFacts(info.client_id, info.person_id, info.served_by) if info else None

    def practice_leads(self, client_id: ClientId, at: datetime) -> Mapping[OrganizationId, PersonId]:
        return self._lookup.practice_leads(client_id, at)

    def end_relationship(self, org_id: OrganizationId, client_id: ClientId, at: datetime) -> None:
        self._lookup.end_relationship(org_id, client_id, at)
