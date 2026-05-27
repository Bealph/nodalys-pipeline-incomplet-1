"""Index de performance sur contrats.statut + date_signature.

Revision ID: 005
Revises: 004
"""

from alembic import op


revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_contrats_statut_date",
        "contrats",
        ["statut", "date_signature"],
    )


def downgrade() -> None:
    op.drop_index("ix_contrats_statut_date", table_name="contrats")
