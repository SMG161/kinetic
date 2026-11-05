"""Alembic entry point. Migrations are written by hand: exclusion constraints and
tstzrange columns are beyond what autogenerate can produce reliably."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine

from kinetic.settings import get_settings

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def run_migrations_offline() -> None:
    """Emit SQL to stdout instead of running it (alembic upgrade --sql)."""
    context.configure(url=get_settings().database_url, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(get_settings().database_url)
    with engine.connect() as connection:
        context.configure(connection=connection)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
