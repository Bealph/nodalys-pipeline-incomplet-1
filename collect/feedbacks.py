"""Collecteur — feedbacks de fin de session (CSV).

Source : fichiers CSV dans ``data/feedbacks/*.csv``.
Cible  : table ``feedbacks``.

WIP — laissé en plan en attendant le passage à l'API exports v2.
À reprendre.
"""

from __future__ import annotations

from collect._common import log


def run() -> None:
    # TODO: brancher la lecture des CSV → upsert feedbacks.
    log.error("collect.feedbacks.not_wired")
    raise NotImplementedError("collect.feedbacks.run() : pas branché.")


if __name__ == "__main__":
    run()
