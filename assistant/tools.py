"""Outils LangChain exposés à l'assistant Nodalys.

Chaque outil ouvre sa propre connexion : c'est l'assistant qui décide
quand interroger la base.
"""

from __future__ import annotations

import os
from pathlib import Path

from langchain_core.tools import tool
from sqlalchemy import create_engine, text

QUERIES_DIR = Path(__file__).parent.parent / "queries"


def _engine_from_env(env_var: str = "DB_URL"):
    url = os.environ.get(env_var)
    if not url:
        raise RuntimeError(f"Variable d'environnement {env_var!r} non définie.")
    return create_engine(url, future=True)


@tool
def query_db(query_name: str) -> str:
    sql_path = QUERIES_DIR / f"{query_name}.sql"
    if not sql_path.exists():
        return f"Requête inconnue : {query_name}. Disponibles : " + ", ".join(
            p.stem for p in QUERIES_DIR.glob("*.sql")
        )
    sql = sql_path.read_text(encoding="utf-8")
    engine = _engine_from_env("DB_URL")
    with engine.connect() as conn:
        result = conn.execute(text(sql))
        rows = result.fetchall()
    return str(rows)


@tool
def query_feedbacks(note_min: int = 1, note_max: int = 5) -> str:
    """Renvoie les feedbacks dont la note est dans [note_min, note_max].

    Utile pour répondre à des questions comme « quels sont les retours
    négatifs des dernières sessions ? ».
    """
    engine = _engine_from_env("DB_URL")
    with engine.connect() as conn:
        result = conn.execute(
            text(
                """
                SELECT f.session_id, f.note_globale, f.commentaire, f.source_csv
                FROM feedbacks f
                WHERE f.note_globale BETWEEN :note_min AND :note_max
                ORDER BY f.note_globale ASC, f.date_saisie DESC
                LIMIT 50
                """
            ),
            {"note_min": note_min, "note_max": note_max},
        )
        rows = [dict(r._mapping) for r in result.fetchall()]
    if not rows:
        return "Aucun feedback dans cette plage."
    return "\n".join(
        f"session={r['session_id']} note={r['note_globale']} | {r['commentaire']} "
        f"(source: {r['source_csv']})"
        for r in rows
    )
