"""Crée les tables clients et sessions.

Revision ID: 001
Revises:
"""

from alembic import op
import sqlalchemy as sa


revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "clients",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("siret", sa.String(14), nullable=False, unique=True),
        sa.Column("raison_sociale", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("ix_clients_raison_sociale", "clients", ["raison_sociale"])

    op.create_table(
        "sessions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("code", sa.String(64), nullable=False, unique=True),
        sa.Column("titre", sa.String(255), nullable=False),
        sa.Column("client_id", sa.Integer, sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("date_debut", sa.Date, nullable=False),
        sa.Column("date_fin", sa.Date, nullable=False),
        sa.Column("duree_heures", sa.Integer, nullable=False),
        sa.Column("places_max", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("ix_sessions_client_id", "sessions", ["client_id"])
    op.create_index("ix_sessions_date_debut", "sessions", ["date_debut"])


def downgrade() -> None:
    op.drop_table("sessions")
    op.drop_table("clients")
