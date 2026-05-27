"""Crée la table stagiaires.

Revision ID: 002
Revises: 001
"""

from alembic import op
import sqlalchemy as sa


revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "stagiaires",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("session_id", sa.Integer, sa.ForeignKey("sessions.id"), nullable=False),
        sa.Column("prenom", sa.String(128), nullable=False),
        sa.Column("nom", sa.String(128), nullable=False),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("ix_stagiaires_session_id", "stagiaires", ["session_id"])
    op.create_index("ix_stagiaires_email", "stagiaires", ["email"])


def downgrade() -> None:
    op.drop_table("stagiaires")
