% Cours — Reprendre un pipeline de collecte de données inachevé
% Support pédagogique complet
% TP Nodalys — Formation WCS

---

# Avant-propos

Ce cours est un **support complet** pour reprendre, auditer et compléter un pipeline de collecte de données existant. Il s'inscrit dans la suite directe du TP Nodalys (réparation d'un pipeline incomplet : sources non collectées, requêtes SQL cassées, table manquante, assistant déconnecté).

Tu peux l'utiliser de trois façons :

1. **Comme support de révision** après le TP, pour ancrer les notions.
2. **Comme kit de reprise** si on te confie un autre projet hérité similaire.
3. **Comme référence rapide** : les templates de la Partie 4 sont copier-coller-adaptables.

Le cours est volontairement **opérationnel** : peu de théorie générique, beaucoup de patterns concrets et de checklists. Tout ce qui est ici a été éprouvé sur un cas réel.

---

# Table des matières

1. [Partie 1 — Les concepts fondamentaux](#partie-1)
   - 1.1 Pipeline ETL : Extract / Transform / Load
   - 1.2 Idempotence : la propriété qui sauve les pipelines batch
   - 1.3 Validation des données avec pydantic
   - 1.4 Migrations Alembic : versionner le schéma BDD
   - 1.5 Agents LLM avec tool calling (LangChain)
   - 1.6 RGPD : minimisation et défense en profondeur
   - 1.7 Observabilité : logs structurés (structlog)
2. [Partie 2 — La démarche de reprise d'un projet inconnu](#partie-2)
   - Phase 1 : Comprendre l'intention
   - Phase 2 : Cartographier l'existant
   - Phase 3 : Confronter à l'exécution
   - Phase 4 : Synthétiser dans une note d'audit
   - Phase 5 : Coder en boucle courte
3. [Partie 3 — Templates réutilisables](#partie-3)
   - 3.1 Squelette de note d'audit (à remplir)
   - 3.2 Squelette d'un collecteur
   - 3.3 Squelette d'une migration Alembic
   - 3.4 Squelette d'une query SQL exposée à un agent
   - 3.5 Squelette d'un outil LangChain
4. [Partie 4 — Anti-patterns à éviter](#partie-4)
5. [Partie 5 — Glossaire](#partie-5)
6. [Annexes](#annexes)
   - A. Commandes utiles
   - B. Convertir ce document en Word ou PDF
   - C. Pour aller plus loin

---

# Partie 1 — Les concepts fondamentaux {#partie-1}

## 1.1 Pipeline ETL : Extract / Transform / Load

Un pipeline de collecte est toujours composé de **trois étapes universelles**, peu importe la techno :

| Étape | Rôle | Outils typiques |
|---|---|---|
| **Extract** | Récupérer la donnée brute depuis une source (API REST, CSV, BDD source, message broker…) | `httpx`, `requests`, `pandas.read_csv`, drivers SQL |
| **Transform** | Nettoyer, valider, normaliser, enrichir | `pandas`, `pydantic`, regex, conversions de types |
| **Load** | Écrire dans le système cible (BDD, datalake, fichier, message broker) | `SQLAlchemy`, `psycopg`, S3, Kafka |

Le pattern qu'on a observé chez Nodalys (`collect/_common.py:3-7`) ajoute une **4ᵉ étape Log** : un résumé final (nombre d'enregistrements lus, insérés, mis à jour, ignorés). C'est devenu un standard en observabilité moderne — un pipeline sans logs structurés est un pipeline qu'on ne peut pas diagnostiquer en prod.

### Pourquoi un collecteur = une fonction `run()`

Convention forte : **un module Python = une source = une fonction `run()`**.

Avantages :
- **Testabilité** : on peut tester chaque collecteur isolément
- **Reprise sur erreur** : si feedbacks plante, sessions a déjà tourné — on relance que feedbacks
- **Orchestration** : un orchestrateur (Makefile, Airflow, Prefect…) appelle les `run()` dans le bon ordre

À l'inverse, mélanger plusieurs sources dans un même module casse cette modularité (cf. le cas borderline de `collect/sessions.py` qui contient aussi `upsert_stagiaires` — fonctionnel mais peu propre).

### Schéma mental

```
┌─────────────┐    ┌──────────────┐    ┌──────────────┐    ┌────────┐
│   SOURCE    │ →  │   EXTRACT    │ →  │  TRANSFORM   │ →  │  LOAD  │
│ API / CSV / │    │ httpx / pd.  │    │  pydantic /  │    │  SQLA  │
│    JSON     │    │   read_csv   │    │   pandas     │    │ upsert │
└─────────────┘    └──────────────┘    └──────────────┘    └───┬────┘
                                                                │
                                                                ▼
                                                        ┌───────────────┐
                                                        │   LOG STATS   │
                                                        │ nb_read / nb_ │
                                                        │ upserted / nb │
                                                        │   _skipped    │
                                                        └───────────────┘
```

## 1.2 Idempotence : la propriété qui sauve les pipelines batch

**Définition** : une opération est **idempotente** si on peut la rejouer plusieurs fois sans changer le résultat final. C'est **la** propriété fondamentale d'un pipeline batch fiable.

### Pourquoi c'est critique

Un pipeline tournera potentiellement :
- Plusieurs fois par jour (cron)
- Après un crash (reprise sur erreur)
- Après une modification de code (re-validation)

Si chaque exécution casse parce qu'il y a déjà des données en base → ton pipeline est inutilisable en prod.

### Le mauvais pattern

```sql
-- ❌ Crash à la 2ᵉ exécution : violation de contrainte PK
INSERT INTO clients (id, raison_sociale)
VALUES (1, 'Atlas Conseil');
```

### Le bon pattern : upsert

```sql
-- ✅ Idempotent : si l'id existe déjà, on met à jour
INSERT INTO clients (id, raison_sociale)
VALUES (1, 'Atlas Conseil')
ON CONFLICT (id) DO UPDATE
  SET raison_sociale = EXCLUDED.raison_sociale;
```

`EXCLUDED` est la pseudo-table Postgres qui contient les valeurs **qu'on aurait insérées** si pas de conflit. Très pratique pour mettre à jour avec les nouvelles données.

### Variantes selon la clé d'unicité

- **Clé technique (id auto-incrémenté)** : `ON CONFLICT (id) DO UPDATE`
- **Clé naturelle (combinaison de colonnes métier)** : déclarer une `UniqueConstraint` dans la migration, puis `ON CONFLICT ON CONSTRAINT nom_de_la_contrainte DO UPDATE`

Exemple Nodalys (feedbacks) :
```sql
ON CONFLICT ON CONSTRAINT uq_feedbacks_session_email_date DO UPDATE
  SET note_globale = EXCLUDED.note_globale,
      commentaire = EXCLUDED.commentaire;
```

### Réflexe à acquérir

Avant de pousser un script en prod, **pose-toi la question** : *"si je le relance demain matin, qu'est-ce qui se passe ?"*

Si la réponse est *"ça plante"* → ton code n'est pas idempotent → tu le rends idempotent.

## 1.3 Validation des données avec pydantic

### Principe

Quand tu lis une source externe (API, CSV, fichier utilisateur…), **tu ne fais jamais confiance**. La donnée peut être malformée, incomplète, hors plage, dans un mauvais encoding. Si tu l'insères telle quelle en base, **tu pourris ta base**.

`pydantic` te permet de déclarer un **schéma** et de **rejeter** tout ce qui ne le respecte pas.

### Exemple commenté

```python
from datetime import date
from pydantic import BaseModel, Field

class FeedbackPayload(BaseModel):
    """Schéma d'une ligne de feedback validée."""

    session_id: int                                   # int strict, refuse "abc"
    stagiaire_email: str | None = None                # peut être None (anonyme)
    date_saisie: date                                 # convertit "2025-09-19" → date
    note_globale: int = Field(ge=1, le=5)             # entier entre 1 et 5 inclus
    commentaire: str | None = None                    # texte libre, peut être vide
    source_csv: str                                   # obligatoire (traçabilité RGPD)
```

Quand tu fais `FeedbackPayload.model_validate(row)`, pydantic :
- Vérifie les **types** (un float au lieu d'un int ? Refus.)
- Applique les **contraintes** (`Field(ge=1, le=5)` : si on lui passe 99, `ValidationError`)
- **Convertit** automatiquement quand c'est sans ambiguïté (`"2025-09-19"` → `date(2025, 9, 19)`)

### Deux stratégies face à un payload invalide

| Stratégie | Action | Quand l'utiliser |
|---|---|---|
| **Fail-fast** | On crashe au premier problème, le pipeline s'arrête | Pipeline temps-réel, intolérance zéro à la pourriture, ou pendant le dev pour spotter les bugs vite |
| **Fail-safe (skip + log)** | On ignore la ligne fautive, on continue, on logge un warning | **Pipeline batch** (notre cas Nodalys) — on ne veut pas qu'une ligne pourrie sur 10 000 bloque toute la collecte |

### Implémentation skip + log

```python
from pydantic import ValidationError

for line_num, row in enumerate(df.to_dict(orient="records"), start=2):
    try:
        payload = MyPayload.model_validate(row)
    except ValidationError as err:
        log.warning(
            "collect.skip_invalid",
            line=line_num,
            reason=err.errors()[0]["msg"],
        )
        skipped += 1
        continue
    items.append(payload)
```

À retenir :
- **`enumerate(..., start=2)`** : la ligne 1 du CSV est l'en-tête, les données commencent à la ligne 2 — ça aide quand on doit ouvrir le CSV pour vérifier
- **`err.errors()[0]["msg"]`** : le 1er message d'erreur, en clair
- On **incrémente un compteur `skipped`** qu'on logge à la fin (visibilité)

## 1.4 Migrations Alembic : versionner le schéma BDD

### Principe

Une **migration** = un script versionné qui décrit une **modification du schéma** (création de table, ajout de colonne, index…). Alembic les chaîne via deux champs : `revision` (id de la migration) et `down_revision` (id de la précédente).

L'avantage : ton schéma de BDD devient **versionné comme ton code**. Tu peux le rejouer sur n'importe quel environnement (dev, staging, prod) avec la garantie d'arriver au même état.

### Structure d'une migration

```python
"""Crée la table contrats.

Revision ID: 004
Revises: 003
"""

from alembic import op
import sqlalchemy as sa


revision = "004"           # id unique de cette migration
down_revision = "003"      # id de la migration précédente
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Appliquée par `alembic upgrade head`."""
    op.create_table(
        "contrats",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("client_id", sa.Integer, sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("session_id", sa.Integer, sa.ForeignKey("sessions.id"), nullable=False),
        sa.Column("statut", sa.String(32), nullable=False),
        sa.Column("montant_ht", sa.Numeric(14, 2), nullable=False),
        sa.Column("date_signature", sa.Date, nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("ix_contrats_client_id", "contrats", ["client_id"])


def downgrade() -> None:
    """Appliquée par `alembic downgrade -1` — défait la migration."""
    op.drop_table("contrats")
```

### Règles cardinales

1. **Chaque migration a un id unique** (par convention `NNN_verbe_objet.py` : `001_create_users.py`, `005_add_email_index.py`).
2. **`down_revision` pointe vers la précédente** dans l'ordre chronologique.
3. **Pas de trou dans la chaîne** (notre anomalie #1 : 005 référence 004 absente → Alembic plante).
4. **Toujours fournir `upgrade()` ET `downgrade()`** — le `downgrade` permet de revenir en arrière si la migration cause un problème en prod.
5. **On ne modifie JAMAIS une migration déjà appliquée en prod**. Si elle a un bug, on crée une **nouvelle migration corrective**.

### Choix des types SQL — règles pragmatiques

| Donnée Python / JSON | Type SQLAlchemy | Notes |
|---|---|---|
| `int` clé primaire | `sa.Integer, primary_key=True` | Auto-incrémenté par Postgres |
| `int` foreign key | `sa.Integer, sa.ForeignKey("table.id"), nullable=False` | `nullable=False` sauf si la relation est optionnelle |
| `str` court (statut, code…) | `sa.String(N)` | Prendre une marge : `String(32)` est un bon défaut |
| `str` long (commentaire) | `sa.Text` | Pas de limite de taille |
| `date` | `sa.Date` | Pour "2025-09-19" |
| `datetime` | `sa.DateTime` | Pour timestamps avec heure |
| **valeur monétaire** | `sa.Numeric(precision, scale)` | **JAMAIS `Float`** (arrondis dégueulasses) — par ex. `Numeric(14, 2)` pour des euros avec 2 décimales |
| timestamp auto | `sa.DateTime, server_default=sa.func.now()` | Convention pour `created_at`, `updated_at` |

### Pourquoi pas `Float` pour de l'argent ?

```python
>>> 0.1 + 0.2
0.30000000000000004  # 😱
```

Les flottants binaires ne représentent pas exactement la base 10. Pour de l'argent, tu utilises **toujours** `Decimal` côté Python et `Numeric(P, S)` côté SQL — c'est exact.

## 1.5 Agents LLM avec tool calling (LangChain)

### Principe

Un **agent LLM** = un LLM + une liste d'**outils** (fonctions Python qu'il peut appeler). Quand l'utilisateur pose une question, le LLM **décide** :
- de répondre directement (s'il a la connaissance)
- d'**appeler un outil** pour récupérer la donnée, puis de formuler la réponse à partir du résultat
- d'enchaîner **plusieurs appels d'outils** dans un même tour

C'est ce qu'on appelle le **tool calling** ou **function calling**.

### Architecture chez Nodalys

```
┌────────────┐
│ Utilisateur│
│ pose une   │
│  question  │
└──────┬─────┘
       │
       ▼
┌──────────────────┐
│  LLM Kimi-K2.6   │
│  (Azure AI)      │  ← "j'ai besoin du résultat d'une query"
└────┬──────────┬──┘
     │          │
     ▼          ▼
┌─────────┐  ┌───────────────────┐
│query_db │  │query_feedbacks    │
│         │  │                   │
│lit .sql │  │SQL paramétré      │
│ Postgres│  │ Postgres          │
└─────────┘  └───────────────────┘
```

### Code minimal

```python
from langchain.agents import create_agent
from langchain_core.tools import tool


@tool
def query_db(query_name: str) -> str:
    """Exécute une requête SQL prédéfinie.

    Le paramètre est le nom du fichier sans extension (ex: 'top_formations').
    Disponibles : top_formations, contrats_actifs, stagiaires_par_session,
    feedbacks_recents.
    """
    # ...lit le fichier .sql, l'exécute, renvoie le résultat...


SYSTEM_PROMPT = """Tu es l'assistant de Nodalys. Réponds à partir des outils.
Réponds en français, cite la requête utilisée."""


def build_agent():
    llm = ...  # initialisation du LLM
    return create_agent(llm, tools=[query_db, query_feedbacks], system_prompt=SYSTEM_PROMPT)
```

### Points critiques (à connaître pour éviter les pièges)

1. **La docstring est obligatoire** sur un `@tool`. Elle est utilisée par le LLM pour décider **quand** appeler le tool. Sans docstring : `ValueError: Function must have a docstring`.
2. **Type hints obligatoires** sur les paramètres : ils servent à générer le schéma JSON que le LLM doit respecter pour appeler le tool.
3. **Le system_prompt** guide le comportement global (style, langue, contraintes — "cite la source", "n'invente pas").
4. **Ne logge jamais les payloads sensibles** que le LLM échange avec les tools — c'est du PII potentiel.

## 1.6 RGPD : minimisation et défense en profondeur

### Les 3 principes à intérioriser

1. **Finalité explicite** : on collecte une donnée parce qu'elle sert un usage défini par contrat (gestion de session, facturation, etc.). **Pas "au cas où"**.
2. **Minimisation** : on collecte **strictement ce qui est nécessaire** à cette finalité.
3. **Durée limitée** : on conserve les données le temps de la finalité + durée légale de prescription, puis on supprime/anonymise.

### Défense en profondeur

Ne te repose **jamais sur un seul filtre** pour empêcher une fuite de données interdites. Chez Nodalys, on a 3 couches qui se renforcent :

| Couche | Filtre | Ce qu'elle bloque |
|---|---|---|
| **1 — Le collecteur** | Sélection explicite des colonnes à insérer (`INSERT INTO stagiaires (id, session_id, prenom, nom, email)` — pas `telephone_personnel`) | La donnée interdite n'arrive pas en base |
| **2 — Le schéma pydantic** | Ne déclare que les champs autorisés → pydantic ignore silencieusement les autres | Si demain quelqu'un fait `**item` pour passer le dict entier, pydantic filtre |
| **3 — Le schéma SQL** | La table n'a pas la colonne interdite | Même si les couches 1 et 2 cèdent, la DB refuse |

**Si une couche cède, les autres protègent**. Si tu n'as qu'une seule couche, un refactor maladroit suffit à provoquer une fuite RGPD (et donc une amende CNIL).

### Cas particuliers fréquents

- **Anonymisation après X jours** : implémenter un job cron qui remplace les emails par un hash SHA-256 tronqué. Pas en place chez Nodalys (documenté comme dette).
- **Logs applicatifs** : un log qui contient un email **est** une collecte au sens RGPD. Vigilance sur ce que tu logges.
- **Réponses du LLM** : si ton agent peut renvoyer du PII (email, nom…) à l'utilisateur, vérifier qui peut interroger l'agent et tracer les accès.

## 1.7 Observabilité : logs structurés (structlog)

### Pourquoi structuré

Un log classique :
```
2025-09-19 14:32:01 INFO Fetched 45 sessions from API
```

Un log structuré (JSON) :
```json
{"timestamp": "2025-09-19T14:32:01Z", "level": "info",
 "event": "collect.sessions.fetched", "count": 45,
 "source": "https://api.nodalys.fr/sessions"}
```

L'avantage : on peut **requêter** les logs en prod (Datadog, Loki, Splunk…) :
- "Combien de sessions on a collecté hier ?" → `count` filtré sur date
- "Quelles lignes ont été skippées ?" → `event:collect.feedbacks.skip_invalid`
- "Quel est le taux d'erreur sur 24h ?" → agrégation par `level:error`

### Convention chez Nodalys

```python
import structlog
log = structlog.get_logger()

log.info("collect.sessions.start")
log.info("collect.sessions.fetched", count=45)
log.warning("collect.feedbacks.skip_invalid", path="feedbacks_T3.csv", line=83, reason="note > 5")
log.info("collect.sessions.done", clients=8, sessions=45, stagiaires=25)
```

Format de l'`event_name` : `module.action[.detail]`. C'est ce qui permet de filtrer/agréger.

---

# Partie 2 — La démarche de reprise d'un projet inconnu {#partie-2}

Voici la **méthode reproductible** que tu peux appliquer à tout projet hérité similaire au TP Nodalys.

## Phase 1 — Comprendre l'intention (15-30 min)

Avant de regarder une ligne de code, comprends **ce que le projet est censé faire**.

**Checklist** :
- [ ] Lire le `README.md` en entier
- [ ] Lire les fichiers dans `docs/` (memo métier, RGPD, ADR…)
- [ ] Repérer les **commandes principales** (`Makefile`, `package.json` scripts, etc.)
- [ ] Identifier les **sources de données** et les **cibles**

**Questions à se poser** :
1. À quoi sert ce projet en 1 phrase ?
2. Qui l'utilise (humains, autres systèmes) ?
3. Quelles sont les commandes pour le lancer ?
4. Quelles sources de données sont en jeu ?

## Phase 2 — Cartographier l'existant (30-60 min)

**Checklist** :
- [ ] Faire un `tree` de l'arborescence (ou Glob `**/*` filtré)
- [ ] Ouvrir le **point d'entrée** (`Makefile`, `main.py`, `index.ts`)
- [ ] Ouvrir le fichier de **conventions partagées** (`_common.py`, `base.py`, `utils.py`)
- [ ] Ouvrir **un fichier de référence** par dossier (le plus gros, ou celui marqué "exemple" dans les commentaires)
- [ ] Noter les **conventions** : nommage, docstrings, gestion des erreurs, logs, structure des modules

**Questions à se poser** :
1. Quels sont les grands modules et leurs rôles ?
2. Y a-t-il un pattern de référence à imiter pour les nouveaux ajouts ?
3. Quelles libs sont utilisées (regarde `pyproject.toml` / `package.json`) ?

## Phase 3 — Confronter à l'exécution (15-30 min)

**Checklist** :
- [ ] Faire tourner le projet en suivant le README
- [ ] **Lire chaque message d'erreur intégralement** (les solutions sont souvent dedans)
- [ ] Distinguer **bug du projet** vs **bug d'environnement** (Docker pas lancé, `.env` manquant, paquet non installé…)
- [ ] Noter chaque crash : où, message, hypothèse

**Règle d'or** : tu ne touches **pas encore au code**. Tu observes.

### Comment lire une stack trace efficacement

Une stack trace longue contient deux infos critiques :

1. **En haut** : les warnings et le résumé en français (parfois).
2. **Tout en bas** : la ligne `XxxError: message`.

Le **milieu** (chemins de fichiers `File "..." line N, in ...`) est rarement utile s'il pointe dans `.venv/site-packages/` — c'est juste le chemin que Python a suivi pour arriver au crash.

Exemple :
```
[80 lignes de stack...]
File ".../alembic/script/revision.py", line 245, in _revision_map
    down_revision = map_[downrev]
                    ~~~~^^^^^^^^^
KeyError: '004'
```

→ Le `KeyError: '004'` te dit que la révision `004` est cherchée mais introuvable. Le reste est secondaire.

## Phase 4 — Synthétiser dans une note d'audit (30-45 min)

Rédige une note structurée autour de **5 questions universelles** :

1. **Comment c'est organisé ?** (étapes du pipeline, ordre, modules)
2. **Ce qui fonctionne** (à préserver, à ne pas casser)
3. **Ce qui manque ou est cassé** (avec localisation précise et comment tu l'as repéré)
4. **Les conventions à respecter** (style du prédécesseur)
5. **Les enjeux transverses** (RGPD, sécurité, performance, dette technique)

Ajoute un **schéma de flux annoté** OK / cassé / manquant avec des emojis (✅ 🟠 🔴 ❌).

Ajoute un **plan d'attaque** dans l'ordre des dépendances (les bloquants d'abord).

**Garde le format à 1 page** : ça force la concision et c'est ce que les managers lisent vraiment.

## Phase 5 — Coder en boucle courte

**Checklist** :
- [ ] **Un bug à la fois** — pas de big bang
- [ ] **Re-lancer après chaque fix** pour vérifier qu'on avance d'un cran
- [ ] **Commit après chaque succès** (filet de sécurité)
- [ ] **Test d'intégration** après chaque gros changement (chez Nodalys : `make ingest`)
- [ ] **Documenter ce qu'on découvre** au fur et à mesure (nouvelles anomalies, choix faits)

**Anti-pattern** à éviter : fixer 5 bugs d'un coup puis tout commiter ensemble. Si un seul casse quelque chose, tu ne sais pas lequel.

---

# Partie 3 — Templates réutilisables {#partie-3}

## 3.1 Squelette de note d'audit (à remplir pour un autre brief)

```markdown
# Note d'audit — [Nom du projet]

**Auteur :** [toi] · **Date :** [YYYY-MM-DD] · **Périmètre :** état des lieux avant modifications.

## 1. Organisation actuelle du pipeline

[Orchestration : qui appelle quoi, dans quel ordre]

```
[diagramme ASCII : étape1 → étape2 → étape3]
```

[Sources de données] - [Entités cibles] - [Composants principaux]

## 2. Ce qui fonctionne (à ne pas casser)

[Liste des modules / fichiers / commandes qui marchent et qu'il ne faut pas toucher sauf nécessité]

## 3. Ce qui manque ou est cassé

[Tableau d'anomalies]

| # | Anomalie | Localisation | Sévérité |
|---|---|---|---|
| 1 | ... | `chemin/fichier:ligne` | 🔴 Bloquant |
| 2 | ... | `chemin/fichier:ligne` | 🟠 Cassé |
| 3 | ... | `chemin/fichier:ligne` | 🟡 Branchement |

## 4. Conventions à respecter

[Style du prédécesseur : nommage, structure, gestion d'erreurs, logs]

## 5. Enjeux transverses

[RGPD / Sécurité / Performance / Dette technique]

## Schéma de flux annoté

```
[Diagramme ASCII avec ✅ / 🟠 / 🔴 / ❌ sur chaque composant]
```

## Plan d'attaque proposé (à valider)

1. [Fix bloquant 1]
2. [Fix bloquant 2]
3. [Fixes non-bloquants]
4. [Vérification end-to-end]
```

## 3.2 Squelette d'un collecteur

```python
"""Collecteur — [nom de la source].

Source : [d'où ça vient]
Cible  : table ``[nom_table]``

Lancement :
    uv run python -m collect.[nom]
"""

from __future__ import annotations

from datetime import date  # ou autres imports selon besoin
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import text

from collect._common import db_session, log


class [Nom]Payload(BaseModel):
    """Schéma d'une ligne après lecture + validation."""
    # ...déclarer chaque champ avec son type et ses contraintes


def fetch_[nom]() -> list[[Nom]Payload]:
    """Étape 1 — Extract : récupération brute + validation pydantic."""
    items: list[[Nom]Payload] = []
    skipped = 0
    # ...lecture de la source (API / CSV / fichier)
    for raw_row in raw_data:
        try:
            items.append([Nom]Payload.model_validate(raw_row))
        except ValidationError as err:
            log.warning("collect.[nom].skip_invalid", reason=err.errors()[0]["msg"])
            skipped += 1
    log.info("collect.[nom].fetched", count=len(items), skipped=skipped)
    return items


def upsert_[nom](session, payloads: list[[Nom]Payload]) -> int:
    """Étape 2 — Load : upsert idempotent."""
    inserted = 0
    for p in payloads:
        result = session.execute(
            text("""
                INSERT INTO [table] (...)
                VALUES (:..., :...)
                ON CONFLICT (...) DO UPDATE SET ...
            """),
            p.model_dump(),
        )
        inserted += result.rowcount or 0
    return inserted


def run() -> None:
    """Étape 3 — Orchestration + log final."""
    log.info("collect.[nom].start")
    payloads = fetch_[nom]()
    with db_session() as session:
        nb = upsert_[nom](session, payloads)
    log.info("collect.[nom].done", inserted_or_updated=nb)


if __name__ == "__main__":
    run()
```

## 3.3 Squelette d'une migration Alembic

```python
"""[Description de la migration en 1 ligne].

Revision ID: NNN
Revises: NNN-1
"""

from alembic import op
import sqlalchemy as sa


revision = "NNN"
down_revision = "NNN-1"   # id de la migration précédente
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Applique la migration."""
    op.create_table(
        "ma_table",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("autre_table_id", sa.Integer, sa.ForeignKey("autre_table.id"), nullable=False),
        sa.Column("nom", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("ix_ma_table_autre_table_id", "ma_table", ["autre_table_id"])


def downgrade() -> None:
    """Défait la migration (en sens inverse)."""
    op.drop_table("ma_table")
```

## 3.4 Squelette d'une query SQL exposée à un agent

```sql
-- [Description en français — finalité métier]
-- Appelée par l'assistant pour répondre à « ... ».
--
-- Tables référencées : [liste]

SELECT
    col1,
    col2,
    AGG_FUNC(col3) AS alias
FROM table1 t1
JOIN table2 t2 ON t2.fk = t1.id
WHERE condition
GROUP BY col1, col2          -- TOUTES les colonnes non agrégées du SELECT
ORDER BY alias DESC
LIMIT N;
```

**Règles** :
- Commentaire d'en-tête en français explicitant la **finalité métier**
- Indentation : 4 espaces (ou la convention du projet)
- Alias courts (`t1`, `c`, `s`) — lisibilité
- **Toute colonne du SELECT non agrégée doit apparaître dans GROUP BY**
- **`NOW() - INTERVAL '7 days'`** et pas `NOW() - '7 days'` en Postgres

## 3.5 Squelette d'un outil LangChain

```python
from langchain_core.tools import tool


@tool
def mon_outil(parametre: str) -> str:
    """Description claire de ce que fait l'outil — UTILISÉE PAR LE LLM.

    Précise quand l'appeler, le format attendu du paramètre, et le format
    de retour. Plus la docstring est précise, mieux le LLM choisira.

    Args:
        parametre: description du paramètre.

    Returns:
        Description de ce qui est retourné.
    """
    # ... logique métier ...
    return resultat_str
```

**À retenir** :
- **Docstring obligatoire** (sans elle : `ValueError` au boot)
- **Type hints obligatoires** sur les paramètres
- **Retour en string** (le LLM consomme du texte)
- Si la donnée est sensible, **filtrer/anonymiser avant le `return`**

---

# Partie 4 — Anti-patterns à éviter {#partie-4}

À garder sous la main comme **memo permanent**.

| Piège | Symptôme | Réflexe correct |
|---|---|---|
| **Projet Python sous OneDrive** | `os error 396` sur hardlink, `Access denied` au reinstall, `.venv` corrompu | `mkdir C:\dev\` et y mettre tous tes repos. JAMAIS sous OneDrive/Dropbox/iCloud |
| **Ne pas lire le message d'erreur** | "Je tourne en rond" | Lire le 1er warning + la dernière exception. La solution y est souvent. |
| **Conclure sur la structure de fichiers seule** | "Il manque `X.py`" alors que le code est dans `Y.py` | Toujours ouvrir le code avant de conclure |
| **Mauvais dossier git** | `git status` qui liste tout le HOME | Vérifier le path dans le prompt avant chaque `git`. `cd` dans le bon repo. |
| **Copier-coller la sortie comme commande** | "The term 'Installed' is not recognized" | Une commande à la fois, on relit avant Entrée |
| **`sa.String("8")` au lieu de `sa.String(8)`** | TypeError au boot | Un nombre = pas de guillemets en Python |
| **`nullable=True` par défaut** | Données vides en base | Question métier : "un X sans valeur, ça a un sens ?" Si non → `nullable=False` |
| **`Float` pour de l'argent** | Arrondis foireux (`0.1 + 0.2 = 0.300...004`) | Toujours `Numeric(precision, scale)` |
| **`NOW() - '7 days'`** | Syntaxe Postgres invalide | `NOW() - INTERVAL '7 days'` |
| **`NaN` pandas → pydantic** | ValidationError sur champs Optional | `df.astype(object).where(df.notna(), None)` |
| **Pipeline non idempotent** | Crash à la 2ᵉ exécution | `INSERT ... ON CONFLICT DO UPDATE` |
| **Trou de révision Alembic** | `KeyError: 'NNN'` au `upgrade` | Pas de saut dans la chaîne `down_revision` |
| **Tool LangChain sans docstring** | `ValueError: Function must have a docstring` | Docstring **obligatoire** sur `@tool` |
| **Fix de 5 bugs avant le 1er test** | "Plus rien ne marche, je sais pas lequel" | 1 fix → 1 test → 1 commit |
| **`.env` oublié** | `RuntimeError: VAR n'est pas définie` | `cp .env.example .env` dès le clonage |
| **Pas de filtrage RGPD côté collecteur** | Champ interdit dans la base | Triple filtre : sélection explicite + pydantic + schéma SQL |

---

# Partie 5 — Glossaire {#partie-5}

| Terme | Définition |
|---|---|
| **ETL** | Extract, Transform, Load : les 3 étapes universelles d'un pipeline de données |
| **Idempotence** | Propriété d'une opération qu'on peut rejouer sans changement de résultat |
| **Upsert** | Opération `INSERT OR UPDATE` selon que la clé existe ou non (`INSERT ... ON CONFLICT DO UPDATE`) |
| **Migration** | Script versionné modifiant le schéma BDD (Alembic, Flyway, Liquibase…) |
| **Foreign Key (FK)** | Contrainte référentielle : une colonne pointe vers la PK d'une autre table |
| **Validation** | Vérification qu'une donnée respecte un schéma attendu (pydantic, JSON Schema, Zod…) |
| **Fail-fast** | Stratégie qui fait crasher au 1er problème (utile en temps-réel) |
| **Fail-safe (skip+log)** | Stratégie qui ignore les erreurs unitaires et continue (utile en batch) |
| **Agent LLM** | Un LLM augmenté d'outils qu'il peut décider d'appeler |
| **Tool calling** | Mécanisme par lequel un LLM appelle des fonctions Python définies |
| **System prompt** | Instructions globales données au LLM (style, contraintes, langue) |
| **RGPD** | Règlement européen sur la protection des données (UE 2016/679) |
| **PII** | Personally Identifiable Information : donnée qui identifie une personne (email, tel…) |
| **Minimisation (RGPD)** | Principe : collecter strictement ce qui est nécessaire |
| **Défense en profondeur** | Empiler plusieurs filtres pour qu'aucun trou unique ne crée une faille |
| **Anonymisation** | Remplacer un identifiant (email) par un hash irréversible |
| **Observabilité** | Capacité à diagnostiquer un système en prod (logs, métriques, traces) |
| **structlog** | Lib Python de logs structurés (JSON-friendly) |
| **Stack trace** | Suite des appels qui ont mené à une exception Python |
| **Venv** | Environnement Python isolé (`.venv/`) — un par projet |

---

# Annexes {#annexes}

## A. Commandes utiles

### Git
```bash
git status                            # voir l'état
git log --oneline                     # historique condensé
git diff                              # voir ses modifs non-commitées
git add <fichier>                     # stager un fichier
git commit -m "message"               # créer un commit
git commit -am "msg"                  # add + commit pour les fichiers déjà trackés
git checkout -- <fichier>             # annuler les modifs d'un fichier (⚠️ destructif)
```

### Docker
```bash
docker compose up -d                  # lancer les services en arrière-plan
docker compose down                   # arrêter les services
docker compose logs -f                # suivre les logs en live
docker exec -it <container> bash      # entrer dans un container
docker ps                             # lister les containers actifs
```

### uv (gestionnaire Python moderne)
```bash
uv sync                               # installer les deps du projet
uv sync --reinstall                   # tout réinstaller proprement
uv sync --reinstall-package X         # réinstaller juste X
uv run <commande>                     # exécuter dans l'env du projet
uv add <package>                      # ajouter une dep au projet
```

### Postgres
```bash
docker exec -it <db_container> psql -U user -d dbname
\dt                                   # lister les tables
\d nom_table                          # voir le schéma d'une table
\q                                    # quitter
```

### Alembic
```bash
uv run alembic upgrade head           # appliquer toutes les migrations
uv run alembic downgrade -1           # revenir d'une migration
uv run alembic current                # voir la révision courante
uv run alembic history                # historique des migrations
uv run alembic revision -m "msg"      # créer un nouveau fichier de migration
```

## B. Convertir ce document en Word ou PDF

### Option 1 — Avec Pandoc (recommandé)

Installer Pandoc : <https://pandoc.org/installing.html>

```bash
# Vers Word
pandoc docs/COURS_PIPELINE_DATA.md -o cours.docx

# Vers PDF (nécessite aussi LaTeX, par ex. MiKTeX sous Windows)
pandoc docs/COURS_PIPELINE_DATA.md -o cours.pdf

# Vers PDF via Chrome/Edge (plus simple, pas besoin de LaTeX)
pandoc docs/COURS_PIPELINE_DATA.md -o cours.html
# puis ouvrir cours.html dans Chrome → Imprimer → Enregistrer en PDF
```

### Option 2 — Sans Pandoc

- **Word** peut ouvrir directement un `.md` (Fichier → Ouvrir → choisir le `.md`)
- **VS Code** : preview Markdown intégrée → copier-coller dans Word avec mise en forme
- **Convertisseur en ligne** : <https://www.markdowntopdf.com/> ou similaire (attention RGPD si le document contient des éléments sensibles)

### Option 3 — Imprimer le rendu Markdown

Sur GitHub, GitLab, Notion ou tout outil qui rend le markdown : ouvrir → Imprimer → Enregistrer en PDF.

## C. Pour aller plus loin

### Sujets directement utiles (non couverts dans le TP)

1. **Pagination cursor des API** : pattern `while next_cursor: page = api.get(cursor=next_cursor)`. Très répandu (Stripe, GitHub, Slack, Atlassian).
2. **Retry exponentiel** : `tenacity` (déjà utilisé dans `_common.py:http_get_json`) — `@retry(stop=stop_after_attempt(3), wait=wait_exponential())`.
3. **Jobs cron pour RGPD** : APScheduler (Python), Celery beat, ou directement `pg_cron` dans Postgres.
4. **Orchestration au-delà du Makefile** : Airflow, Prefect, Dagster pour les pipelines complexes avec dépendances et retries.
5. **Observabilité avancée** : OpenTelemetry pour le tracing distribué, Prometheus pour les métriques.

### Ressources externes

- **pydantic** : <https://docs.pydantic.dev/>
- **SQLAlchemy 2** : <https://docs.sqlalchemy.org/en/20/>
- **Alembic** : <https://alembic.sqlalchemy.org/>
- **LangChain agents** : <https://python.langchain.com/docs/concepts/agents/>
- **structlog** : <https://www.structlog.org/>
- **RGPD officiel (CNIL)** : <https://www.cnil.fr/fr/reglement-europeen-protection-donnees>

---

*Fin du cours. Bon courage pour la suite — tu as maintenant une méthode et un toolkit pour aborder n'importe quel pipeline hérité.*
