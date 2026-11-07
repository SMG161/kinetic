"""directory's public module: the only part of directory other contexts may import.

Everything else under kinetic.directory is internal and can change freely.
"""

from sqlalchemy.orm import Session as DbSession

from kinetic.directory.application.lookup import DirectoryLookup
from kinetic.directory.infrastructure.access_facts import DirectoryPracticeFacts
from kinetic.directory.infrastructure.repositories import (
    SqlClientRelationshipRepository,
    SqlClientRepository,
    SqlProviderRepository,
)


def directory_lookup(db: DbSession) -> DirectoryLookup:
    """Read-only directory facts, inside the caller's transaction."""
    return DirectoryLookup(SqlProviderRepository(db), SqlClientRepository(db), SqlClientRelationshipRepository(db))


def practice_facts(db: DbSession) -> DirectoryPracticeFacts:
    """directory's implementation of access's PracticeFacts port."""
    return DirectoryPracticeFacts(directory_lookup(db))


__all__ = ["DirectoryLookup", "directory_lookup", "practice_facts"]
