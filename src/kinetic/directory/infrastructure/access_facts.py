"""directory's side of access's PracticeFacts port: who leads a client for each org, at an instant.

access defines the port and imports nothing from here; main.py wires this in.
"""

from collections.abc import Mapping
from datetime import datetime

from kinetic.directory.application.lookup import DirectoryLookup
from kinetic.shared_kernel import ClientId, OrganizationId, PersonId


class DirectoryPracticeFacts:
    def __init__(self, lookup: DirectoryLookup) -> None:
        self._lookup = lookup

    def leads(self, client_id: ClientId, at: datetime) -> Mapping[OrganizationId, PersonId]:
        return self._lookup.practice_leads(client_id, at)
