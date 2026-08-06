"""v1.7.1: Abrechnungsmonat je Nutzer

Der Starttag war bis hierher eine app-weite Einstellung, die nur ein
Administrator aendern durfte. Der Zahltag ist aber nichts Gemeinsames: im
selben Haushalt kann eine Person am 27. Gehalt bekommen und die andere am 1.
Jeder waehlt ihn deshalb fuer die EIGENEN Auswertungen.

NULL bedeutet "noch nichts gewaehlt" - dann gilt weiter die app-weite
Voreinstellung aus app_settings ('period'). Bestehende Installationen aendern
sich dadurch nicht: wer bisher 27 eingestellt hatte, sieht weiter 27, bis er
selbst etwas anderes waehlt.

Revision ID: e7c2f5a91b40
Revises: d4a81c62f7e5
Create Date: 2026-08-06 21:50:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e7c2f5a91b40'
down_revision: Union[str, None] = 'd4a81c62f7e5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # nullable -> kein server_default noetig, unkritisch auf gefuellter Tabelle
    op.add_column('user_settings', sa.Column('period_start_day', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('user_settings', 'period_start_day')
