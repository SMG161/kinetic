"""Identifiers shared across contexts.

PersonId is the one thing identity publishes to everyone else. Other contexts
store it and accept it as-is; they never look inside identity to resolve it.
"""

from typing import NewType
from uuid import UUID, uuid4

PersonId = NewType("PersonId", UUID)


def new_person_id() -> PersonId:
    return PersonId(uuid4())
