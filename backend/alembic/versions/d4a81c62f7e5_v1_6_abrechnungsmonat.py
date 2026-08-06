"""v1.6: Abrechnungsmonat (Finanzmonat)

Fuegt das Feld fuer die manuelle Zuordnung einer Buchung zu einem
Abrechnungsmonat hinzu. Leer = es gilt die Regel aus dem Starttag
(app_settings, Schluessel 'period'). Wirkt nur auf Auswertungen.

Revision ID: d4a81c62f7e5
Revises: c3e17b0a94d2
Create Date: 2026-08-06 09:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd4a81c62f7e5'
down_revision: Union[str, None] = 'c3e17b0a94d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # nullable -> kein server_default noetig, unkritisch auf gefuellter Tabelle
    op.add_column('transactions', sa.Column('financial_month', sa.String(length=7), nullable=True))


def downgrade() -> None:
    op.drop_column('transactions', 'financial_month')
