"""Crée la table feedbacks.

Revision ID: 003
Revises: 002
"""

from alembic import op
import sqlalchemy as sa


revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "feedbacks",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "session_id", sa.Integer, sa.ForeignKey("sessions.id"), nullable=False
        ),
        sa.Column("stagiaire_email", sa.String(255), nullable=True),
        sa.Column("date_saisie", sa.Date, nullable=False),
        sa.Column("note_globale", sa.Integer, nullable=False),  # 1-5
        sa.Column("commentaire", sa.Text, nullable=True),
        sa.Column("source_csv", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.UniqueConstraint(
            "session_id",
            "stagiaire_email",
            "date_saisie",
            name="uq_feedbacks_session_email_date",
        ),
    )
    op.create_index("ix_feedbacks_session_id", "feedbacks", ["session_id"])


def downgrade() -> None:
    op.drop_table("feedbacks")
