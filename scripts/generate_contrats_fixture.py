"""Génère data/contrats.json — fixtures importées par seed.py.

Les contrats lient ``clients`` (id 1..8) à des ``sessions`` (id 1..N),
avec un statut ``actif`` ou ``solde``. Aucun lien direct à ``stagiaires`` :
c'est précisément ce qui rend la requête ``contrats_actifs.sql`` cassée.
"""

import json
import random
from datetime import date, timedelta
from pathlib import Path

random.seed(11)

NB_CONTRATS = 60
SESSION_IDS = list(range(1, 46))  # aligné sur ce que mock_api expose

contrats = []
for i in range(1, NB_CONTRATS + 1):
    client_id = random.randint(1, 8)
    contrats.append(
        {
            "id": i,
            "client_id": client_id,
            "session_id": random.choice(SESSION_IDS),
            "statut": random.choice(["actif", "actif", "actif", "solde"]),
            "montant_ht": round(random.uniform(2000, 25000), 2),
            "date_signature": (
                date(2024, 1, 1) + timedelta(days=random.randint(0, 600))
            ).isoformat(),
        }
    )

out = Path(__file__).parent.parent / "data" / "contrats.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(contrats, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"Wrote {out} — {len(contrats)} contrats")
