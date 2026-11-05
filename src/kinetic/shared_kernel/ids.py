"""Identifiers shared across contexts.

PersonId is the one thing identity publishes to everyone else. Other contexts
store it and accept it as-is; they never look inside identity to resolve it.
OrganizationId, ProviderId and ClientId are published by directory the same way,
so care_team can hold them without importing directory's model.
"""

from typing import NewType
from uuid import UUID, uuid4

PersonId = NewType("PersonId", UUID)
OrganizationId = NewType("OrganizationId", UUID)
ProviderId = NewType("ProviderId", UUID)
ClientId = NewType("ClientId", UUID)


def new_person_id() -> PersonId:
    return PersonId(uuid4())
