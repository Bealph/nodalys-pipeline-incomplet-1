"""Données fictives Nodalys — sessions + stagiaires sur 2024-2025.

Générées de manière déterministe (seed=42) pour avoir une base
reproductible entre environnements de dev.
"""

import random
from datetime import date, timedelta

random.seed(42)

FORMATIONS = [
    ("DEV-WEB", "Développeur Web Full-Stack"),
    ("DATA", "Data Analyst — Python & SQL"),
    ("CYBER", "Cybersécurité défensive"),
    ("DEVOPS", "DevOps & Cloud"),
    ("IA", "Dev IA Agentique"),
    ("UX", "UX/UI Designer"),
    ("PROD", "Chef de projet digital"),
    ("MARKETING", "Marketing digital"),
]

CLIENTS = [
    ("FR12345678901", "Atlas Conseil"),
    ("FR98765432109", "Bordeaux Métropole"),
    ("FR55544433322", "CIO Industries"),
    ("FR11122233344", "Datalab Solutions"),
    ("FR77788899900", "Énergie Verte SA"),
    ("FR33344455566", "France Travail Nouvelle-Aquitaine"),
    ("FR22233344455", "Groupe Médian"),
    ("FR66677788899", "Helios Tech"),
]

PRENOMS = [
    "Amine",
    "Léa",
    "Marc",
    "Nadia",
    "Olivier",
    "Pauline",
    "Quentin",
    "Rachid",
    "Sophie",
    "Théo",
    "Ugo",
    "Valérie",
    "Wassila",
    "Xavier",
    "Yasmine",
    "Zoé",
    "Aïcha",
    "Bastien",
    "Clara",
    "Damien",
]
NOMS = [
    "Martin",
    "Dubois",
    "Bernard",
    "Petit",
    "Robert",
    "Richard",
    "Durand",
    "Moreau",
    "Laurent",
    "Simon",
    "Michel",
    "Lefebvre",
    "Leroy",
    "Roux",
    "David",
    "Bertrand",
    "Morel",
    "Fournier",
    "Girard",
    "Bonnet",
]


def _build_clients():
    return [
        {"id": i + 1, "siret": siret, "raison_sociale": nom}
        for i, (siret, nom) in enumerate(CLIENTS)
    ]


def _build_sessions():
    sessions = []
    sid = 1
    for year in (2024, 2025):
        for q, month_start in enumerate((1, 4, 7, 10), start=1):
            for code, titre in FORMATIONS:
                if random.random() < 0.25:
                    continue  # toutes les formations ne tournent pas chaque trim.
                date_debut = date(year, month_start, random.randint(1, 15))
                duree_jours = random.choice([10, 15, 20, 30, 40])
                date_fin = date_debut + timedelta(days=duree_jours * 7 // 5)
                client = random.choice(_build_clients())
                sessions.append(
                    {
                        "id": sid,
                        "code": f"{code}-{year}T{q}",
                        "titre": f"{titre} — {year} T{q}",
                        "client_id": client["id"],
                        "client_raison_sociale": client["raison_sociale"],
                        "date_debut": date_debut.isoformat(),
                        "date_fin": date_fin.isoformat(),
                        "duree_heures": duree_jours * 7,
                        "places_max": random.choice([8, 10, 12, 15]),
                    }
                )
                sid += 1
    return sessions


def _build_stagiaires(sessions):
    stagiaires = []
    stid = 1
    for s in sessions:
        nb = random.randint(3, s["places_max"])
        for _ in range(nb):
            prenom = random.choice(PRENOMS)
            nom = random.choice(NOMS)
            stagiaires.append(
                {
                    "id": stid,
                    "session_id": s["id"],
                    "prenom": prenom,
                    "nom": nom,
                    "email": f"{prenom.lower()}.{nom.lower()}@example.org",
                    # Champ qu'on N'A PAS le droit de collecter (mémo RGPD)
                    "telephone_personnel": f"06{random.randint(10000000, 99999999)}",
                }
            )
            stid += 1
    return stagiaires


CLIENTS_DATA = _build_clients()
SESSIONS_DATA = _build_sessions()
STAGIAIRES_DATA = _build_stagiaires(SESSIONS_DATA)
