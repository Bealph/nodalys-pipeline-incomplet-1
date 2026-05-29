"""Crée la table contrats.

Revision ID: 004
Revises: 003
"""

from alembic import op
import sqlalchemy as sa


revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "contrats",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("client_id", sa.Integer, sa.ForeignKey("clients.id"), nullable=False),
        sa.Column(
            "session_id", sa.Integer, sa.ForeignKey("sessions.id"), nullable=False
        ),
        sa.Column("statut", sa.String(8), nullable=False),
        sa.Column("montant_ht", sa.Numeric(14, 2), nullable=False),
        sa.Column("date_signature", sa.Date, nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("ix_contrats_client_id", "contrats", ["client_id"])
    op.create_index("ix_contrats_session_id", "contrats", ["session_id"])


def downgrade() -> None:
    op.drop_table("contrats")
