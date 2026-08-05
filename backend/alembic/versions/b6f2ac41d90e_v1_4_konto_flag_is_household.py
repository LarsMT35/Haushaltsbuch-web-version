"""v1.4: Konto-Flag is_household (Haushalts- vs. Privatkonto)

Revision ID: b6f2ac41d90e
Revises: a1c9de7fb213
Create Date: 2026-08-05 10:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b6f2ac41d90e'
down_revision: Union[str, None] = 'a1c9de7fb213'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # server_default nötig, da die Tabelle in Produktion bereits Zeilen hat
    op.add_column('accounts', sa.Column('is_household', sa.Boolean(),
                                        nullable=False, server_default=sa.false()))
    # Bestand nach der bisherigen Heuristik vorbelegen (mehr als ein Nutzer mit
    # einer Rolle = gemeinsames Konto), damit die Trennung ohne Nacharbeit
    # sofort dem entspricht, was die Seitenleiste bisher angezeigt hat.
    op.execute("""
        UPDATE accounts SET is_household = true
        WHERE id IN (SELECT account_id FROM account_roles
                     GROUP BY account_id HAVING COUNT(*) > 1)
    """)


def downgrade() -> None:
    op.drop_column('accounts', 'is_household')
