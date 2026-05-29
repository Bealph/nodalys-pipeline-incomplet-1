"""Collecteur — feedbacks de fin de session (CSV).

Source : fichiers CSV dans ``data/feedbacks/*.csv``.
Cible  : table ``feedbacks``.

Lancement :
    uv run python -m collect.feedbacks
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import text

from collect._common import db_session, log


FEEDBACKS_DIR = Path(__file__).parent.parent / "data" / "feedbacks"


class FeedbackPayload(BaseModel):
    """Schéma d'une ligne de feedback après lecture CSV + ajout source."""

    session_id: int
    stagiaire_email: str | None = None
    date_saisie: date
    note_globale: int = Field(ge=1, le=5)
    commentaire: str | None = None
    source_csv: str


def read_csv_files() -> list[FeedbackPayload]:
    """Lit tous les CSV de ``data/feedbacks/`` et valide chaque ligne via pydantic.

    Les lignes invalides (note hors plage, types incorrects…) sont **skippées**
    avec un log warning, plutôt que de faire planter toute la collecte.
    """
    items: list[FeedbackPayload] = []
    skipped = 0
    csv_paths = sorted(FEEDBACKS_DIR.glob("*.csv"))
    for path in csv_paths:
        df = pd.read_csv(path, sep=";")
        # pandas représente les cellules vides par NaN (float) ; pydantic veut None.
        df = df.astype(object).where(df.notna(), None)
        for line_num, row in enumerate(df.to_dict(orient="records"), start=2):
            try:
                payload = FeedbackPayload.model_validate(
                    {**row, "source_csv": path.name}
                )
            except ValidationError as err:
                log.warning(
                    "collect.feedbacks.skip_invalid",
                    path=path.name,
                    line=line_num,
                    reason=err.errors()[0]["msg"],
                )
                skipped += 1
                continue
            items.append(payload)
        log.info("collect.feedbacks.csv_read", path=path.name, rows=len(df))
    log.info("collect.feedbacks.fetched", count=len(items), skipped=skipped)
    return items


def upsert_feedbacks(session, payloads: list[FeedbackPayload]) -> int:
    """Upsert idempotent sur la contrainte (session_id, stagiaire_email, date_saisie)."""
    inserted = 0
    for fb in payloads:
        result = session.execute(
            text(
                """
                INSERT INTO feedbacks (
                    session_id, stagiaire_email, date_saisie,
                    note_globale, commentaire, source_csv
                )
                VALUES (
                    :session_id, :stagiaire_email, :date_saisie,
                    :note_globale, :commentaire, :source_csv
                )
                ON CONFLICT ON CONSTRAINT uq_feedbacks_session_email_date DO UPDATE
                  SET note_globale = EXCLUDED.note_globale,
                      commentaire = EXCLUDED.commentaire,
                      source_csv = EXCLUDED.source_csv
                """
            ),
            fb.model_dump(),
        )
        inserted += result.rowcount or 0
    return inserted


def run() -> None:
    log.info("collect.feedbacks.start")
    payloads = read_csv_files()
    with db_session() as session:
        nb = upsert_feedbacks(session, payloads)
    log.info("collect.feedbacks.done", inserted_or_updated=nb)


if __name__ == "__main__":
    run()
