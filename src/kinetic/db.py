"""Database engine and session factory, shared by every context's infrastructure layer.

Domain code never imports this module.
"""

from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from kinetic.settings import get_settings


@lru_cache
def get_engine() -> Engine:
    return create_engine(get_settings().database_url)


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False)
