"""Request-scoped FastAPI dependencies shared by every context's API. Tests override them."""

from collections.abc import Iterator

from sqlalchemy.orm import Session as DbSession

from kinetic.db import get_session_factory
from kinetic.shared_kernel import Clock, SystemClock

_system_clock = SystemClock()


def get_db() -> Iterator[DbSession]:
    """One transaction per request: committed if the handler succeeds, rolled back if it raises."""
    with get_session_factory().begin() as db:
        yield db


def get_clock() -> Clock:
    return _system_clock
