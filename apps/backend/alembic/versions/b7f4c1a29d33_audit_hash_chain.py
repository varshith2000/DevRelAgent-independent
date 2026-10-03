"""audit hash chain

Revision ID: b7f4c1a29d33
Revises: c39c1f26e2e7
Create Date: 2026-10-02 20:12:00.000000

Adds the tamper-evident hash chain to ``audit_records``. Existing rows keep
``sequence=0`` (reported as legacy) so an unbackfilled database does not read
as tampered.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b7f4c1a29d33"
down_revision: Union[str, Sequence[str], None] = "c39c1f26e2e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("audit_records", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("chain_scope", sa.String(length=80), nullable=False, server_default="global")
        )
        batch_op.add_column(sa.Column("sequence", sa.Integer(), nullable=False, server_default="0"))
        batch_op.add_column(
            sa.Column("prev_hash", sa.String(length=64), nullable=False, server_default="")
        )
        batch_op.add_column(
            sa.Column("entry_hash", sa.String(length=64), nullable=False, server_default="")
        )
        batch_op.create_index(
            batch_op.f("ix_audit_records_chain_scope"), ["chain_scope"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_audit_records_sequence"), ["sequence"], unique=False)
        batch_op.create_index(
            batch_op.f("ix_audit_records_entry_hash"), ["entry_hash"], unique=False
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("audit_records", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_audit_records_entry_hash"))
        batch_op.drop_index(batch_op.f("ix_audit_records_sequence"))
        batch_op.drop_index(batch_op.f("ix_audit_records_chain_scope"))
        batch_op.drop_column("entry_hash")
        batch_op.drop_column("prev_hash")
        batch_op.drop_column("sequence")
        batch_op.drop_column("chain_scope")
