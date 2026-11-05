"""create one schema per bounded context

Revision ID: bc95080155ab
Revises:
Create Date: 2026-11-03 18:02:58.851037

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'bc95080155ab'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CONTEXT_SCHEMAS = ("identity", "directory", "care_team", "records")


def upgrade() -> None:
    for schema in CONTEXT_SCHEMAS:
        op.execute(f"CREATE SCHEMA {schema}")


def downgrade() -> None:
    for schema in reversed(CONTEXT_SCHEMAS):
        op.execute(f"DROP SCHEMA {schema}")
