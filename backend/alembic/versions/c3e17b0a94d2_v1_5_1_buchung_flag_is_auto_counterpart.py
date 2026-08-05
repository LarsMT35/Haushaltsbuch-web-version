"""v1.5.1: Buchungs-Flag is_auto_counterpart

Markiert automatisch erzeugte Gegenbuchungen (Kategorie mit Umbuchungs-
Zielkonto, v1.3b). Ohne den Marker liessen sich diese Buchungen beim
Rollback/Loeschen nicht sicher wiedererkennen und blieben als Saldo-Phantom
im Zielkonto zurueck.

Revision ID: c3e17b0a94d2
Revises: b6f2ac41d90e
Create Date: 2026-08-05 12:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c3e17b0a94d2'
down_revision: Union[str, None] = 'b6f2ac41d90e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('transactions', sa.Column('is_auto_counterpart', sa.Boolean(),
                                            nullable=False, server_default=sa.false()))
    # Bestand nachziehen: so wurden die Gegenbuchungen in v1.3b angelegt.
    # Auch bereits verwaiste Exemplare bekommen den Marker – sie lassen sich
    # danach ueber "Umbuchungen erkennen" aufraeumen.
    op.execute("""
        UPDATE transactions SET is_auto_counterpart = true
        WHERE is_manual = true AND purpose LIKE 'Automatische Gegenbuchung:%'
    """)


def downgrade() -> None:
    op.drop_column('transactions', 'is_auto_counterpart')
