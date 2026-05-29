"""Génère les CSV de feedbacks dans data/feedbacks/.

Sortie déterministe (seed=7). Représente plusieurs trimestres d'export
manuel — un fichier par trimestre. Inclut quelques doublons et lignes
invalides qui reflètent la réalité des exports actuels.
"""

import csv
import random
from pathlib import Path
from datetime import date, timedelta

random.seed(7)

OUT = Path(__file__).parent.parent / "data" / "feedbacks"
OUT.mkdir(parents=True, exist_ok=True)

# Le mock_api expose ~ N sessions ; on s'aligne sur des session_id
# probables (1..120) et stagiaire_email plausibles.
SESSION_IDS = list(range(1, 46))  # aligné sur ce que mock_api expose
PRENOMS = [
    "amine",
    "lea",
    "marc",
    "nadia",
    "pauline",
    "rachid",
    "sophie",
    "yasmine",
    "zoe",
    "olivier",
    "quentin",
    "theo",
]
NOMS = ["martin", "dubois", "bernard", "petit", "robert", "richard", "durand"]

COMMENTAIRES_OK = [
    "Très bonne formation, formateur clair.",
    "Contenu dense mais accessible.",
    "Plateforme un peu lente le matin.",
    "Aurait aimé plus d'exercices pratiques.",
    "Top, je recommande.",
    "Rythme soutenu, à anticiper.",
    "Bon équilibre théorie/pratique.",
    "Salle inconfortable.",
    "Excellente animation de groupe.",
    "",
]

FILES = [
    ("feedbacks_2024_T3.csv", date(2024, 7, 1), date(2024, 9, 30), 90),
    ("feedbacks_2024_T4.csv", date(2024, 10, 1), date(2024, 12, 31), 100),
    ("feedbacks_2025_T1.csv", date(2025, 1, 1), date(2025, 3, 31), 95),
    ("feedbacks_2025_T2.csv", date(2025, 4, 1), date(2025, 6, 30), 80),
    ("feedbacks_2025_T3.csv", date(2025, 7, 1), date(2025, 9, 30), 70),
]


def random_date(start: date, end: date) -> date:
    delta = (end - start).days
    return start + timedelta(days=random.randint(0, delta))


for filename, start, end, count in FILES:
    rows = []
    for _ in range(count):
        prenom = random.choice(PRENOMS)
        nom = random.choice(NOMS)
        email = f"{prenom}.{nom}@example.org" if random.random() > 0.05 else ""
        note = random.choice([1, 2, 3, 4, 4, 4, 5, 5, 5])
        # Quelques notes invalides
        if random.random() < 0.03:
            note = 99
        rows.append(
            {
                "session_id": random.choice(SESSION_IDS),
                "stagiaire_email": email,
                "date_saisie": random_date(start, end).isoformat(),
                "note_globale": note,
                "commentaire": random.choice(COMMENTAIRES_OK),
            }
        )
    # Doublons (5%)
    duplicates = random.sample(rows, max(1, len(rows) // 20))
    rows.extend(duplicates)
    random.shuffle(rows)

    with (OUT / filename).open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "session_id",
                "stagiaire_email",
                "date_saisie",
                "note_globale",
                "commentaire",
            ],
            delimiter=";",
        )
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {filename} — {len(rows)} lines")
