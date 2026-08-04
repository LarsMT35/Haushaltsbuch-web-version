"""v1.3b: Kategorie-Feld transfer_target_account_id

Revision ID: a1c9de7fb213
Revises: f8812dff0959
Create Date: 2026-08-04 21:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1c9de7fb213'
down_revision: Union[str, None] = 'f8812dff0959'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Optionales Zielkonto (z.B. ein manuell angelegtes Depot ohne Bank-Feed)
    # für Kategorien mit "wie Umbuchung behandeln" (4.4/4.9) – nullable, daher
    # kein server_default nötig, auch auf bereits gefüllten Tabellen unkritisch.
    op.add_column('categories', sa.Column('transfer_target_account_id', sa.Integer(), nullable=True))
    with op.batch_alter_table('categories') as batch_op:
        batch_op.create_foreign_key(
            'fk_categories_transfer_target_account_id', 'accounts',
            ['transfer_target_account_id'], ['id'])


def downgrade() -> None:
    with op.batch_alter_table('categories') as batch_op:
        batch_op.drop_constraint('fk_categories_transfer_target_account_id', type_='foreignkey')
    op.drop_column('categories', 'transfer_target_account_id')
