# Note d'audit — Pipeline de collecte Nodalys

**Auteur :** dev IA junior (reprise) · **Date :** 2026-05-28 · **Périmètre :** état des lieux *avant modifications*.

## 1. Organisation actuelle du pipeline

Orchestration via `Makefile`, 5 étapes séquentielles :

```
up → migrate → seed → ingest → chat
```

- **`up`** : `docker compose up -d` (Postgres + mock API FastAPI)
- **`migrate`** : `alembic upgrade head` (création du schéma)
- **`seed`** : `seed.py` charge `data/contrats.json` → table `contrats`
- **`ingest`** : `python -m collect.sessions` (API mock → `clients`/`sessions`/`stagiaires`) puis `python -m collect.feedbacks` (CSV `data/feedbacks/*.csv` → `feedbacks`)
- **`chat`** : REPL LangChain (agent + tools `query_db`, `query_feedbacks`) → LLM Kimi-K2.6 (Azure AI)

**3 sources** : API mock Nodalys, JSON contrats, CSV feedbacks trimestriels. **5 entités cibles** : clients, sessions, stagiaires, feedbacks, contrats.

## 2. Ce qui fonctionne (à ne pas casser)

`collect/_common.py` (utilitaires partagés : `db_session`, `http_get_json` avec retry, `log` structlog) · `collect/sessions.py` (pattern de référence, collecte aussi les stagiaires via `upsert_stagiaires`) · migrations 001/002/003 (`clients`, `sessions`, `stagiaires`, `feedbacks`) · `seed.py` (logique d'upsert idempotent) · `queries/top_formations.sql` (seule query opérationnelle) · `mock_api/` (rate-limit 10 req/s) · `assistant/agent.py` + `assistant/tools.py:query_db` (squelette LangChain).

## 3. Ce qui manque ou est cassé

Repéré par **lecture statique** (à confirmer par exécution).

| # | Anomalie | Localisation | Sévérité |
|---|---|---|---|
| 1 | Migration `004_create_contrats.py` **absente** → table `contrats` jamais créée, alors que la 005 ajoute un index dessus. `make migrate` plante. | `migrations/versions/` (trou entre 003 et 005) | 🔴 Bloquant |
| 2 | `collect.feedbacks.run()` lève `NotImplementedError` (CSV non branchés). `make ingest` plante. | `collect/feedbacks.py:16-18` | 🔴 Bloquant |
| 3 | Query référence `c.stagiaire_id` qui n'existe pas (la table `contrats` a `client_id` + `session_id`). Incohérence métier. | `queries/contrats_actifs.sql:9` | 🟠 Cassé |
| 4 | `GROUP BY s.titre` mais SELECT `cl.raison_sociale` non agrégé → erreur Postgres. | `queries/stagiaires_par_session.sql:11` | 🟠 Cassé |
| 5 | `NOW() - '7 days'` sans mot-clé `INTERVAL` → syntaxe Postgres invalide. | `queries/feedbacks_recents.sql:10` | 🟠 Cassé |
| 6 | `query_feedbacks` lit `DB_FEEDBACK_URL` (inexistante) au lieu de `DB_URL`. | `assistant/tools.py:47` | 🟠 Cassé |
| 7 | `query_feedbacks` n'est plus exposé à l'agent (ligne commentée TODO). | `assistant/agent.py:38-40` | 🟡 Branchement |

Hors scope (à signaler) : `upsert_stagiaires` ne gère pas la pagination cursor de l'API → seuls 25 stagiaires récupérés (`sessions.py:107-109`, marqué `TODO`).

## 4. Conventions à respecter

- **Collecteurs** : un module par source, fonction `run()` en 4 étapes (fetch → validation pydantic → upsert idempotent `INSERT ... ON CONFLICT DO UPDATE` → log structlog `module.action.done`).
- **Style Python** : `from __future__ import annotations`, type hints, docstring de module en tête, helpers d'environnement (`get_db_url`, `get_api_base_url`).
- **Migrations Alembic** : `NNN_verbe_objet.py` (3 chiffres), `revision`/`down_revision` cohérents, `downgrade()` toujours présent.
- **SQL** : commentaire en tête expliquant la finalité métier, indentation 4 espaces, alias courts.
- **Logs** : structlog, event names `collect.X.start` / `collect.X.done` avec compteurs.

## 5. Données personnelles (RGPD)

L'API mock renvoie `telephone_personnel` (`mock_api/app/seed.py:91`), champ **classé interdit** par le mémo DPO (`docs/RGPD-memo.md:43`). **État actuel** : `upsert_stagiaires` ne sélectionne que `id, session_id, prenom, nom, email` — le téléphone n'arrive **pas** en base. ✅

Mais le filtrage est **implicite** (énumération manuelle), contrairement à `SessionPayload` qui filtre via pydantic (`sessions.py:28-39`). **Recommandation** : introduire un `StagiairePayload(BaseModel)` qui ne déclare pas `telephone_personnel`, par cohérence avec la convention du prédécesseur et en défense en profondeur (un futur refactor "passons l'item en kwargs" ferait fuiter le champ).

**Hors scope** : pas de job d'anonymisation J+180 sur feedbacks (documenté dans le mémo comme connu, à traiter ultérieurement).

## Schéma de flux annoté

```
                      ┌────────────────────────────┐
                      │   MAKEFILE (orchestrateur) │
                      └─────────────┬──────────────┘
        ┌──────┬───────────┬────────┴──────────┬────────────┐
        ▼      ▼           ▼                   ▼            ▼
      ┌────┐ ┌─────────┐ ┌──────┐         ┌────────┐   ┌──────┐
      │ up │ │ migrate │ │ seed │         │ ingest │   │ chat │
      │ ✅ │ │ 🔴 (#1) │ │🔴(#1)│         │ 🔴 (#2)│   │ 🟡   │
      └────┘ └────┬────┘ └──┬───┘         └───┬────┘   └──┬───┘
                  │         │                 │           │
                  ▼         ▼                 │           ▼
           migrations/  seed.py               │   assistant/agent.py
           001 ✅       data/contrats.json    │   ├── query_db ✅
           002 ✅                              │   │   └→ queries/
           003 ✅                              │   │      top_formations.sql ✅
           004 ❌ MANQUE                      │   │      stagiaires_par_session.sql 🟠 (#4)
           005 🔴 index sur table inexistante │   │      contrats_actifs.sql 🟠 (#3)
                                              │   │      feedbacks_recents.sql 🟠 (#5)
                                              │   └── query_feedbacks 🟠 (#6, #7)
                                              │
                  ┌───────────────────────────┴───┐
                  ▼                               ▼
          collect.sessions ✅              collect.feedbacks 🔴 (#2)
          ├ fetch_sessions ✅               NotImplementedError
          ├ upsert_clients ✅               (doit lire data/feedbacks/*.csv
          ├ upsert_sessions ✅              et upsert dans feedbacks)
          └ upsert_stagiaires ⚠ (pagination)
            (RGPD: filtrage implicite, à durcir via pydantic)
```

**Légende :** ✅ OK · 🟡 branchement manquant · 🟠 cassé non-bloquant · 🔴 cassé bloquant · ❌ absent

## Plan d'attaque proposé (à valider)

1. Migration `004_create_contrats.py` → débloque `migrate` + `seed`.
2. `collect/feedbacks.py` : implémenter `run()` sur le pattern de `collect/sessions.py`.
3. Réparer les 3 queries SQL.
4. Réparer `query_feedbacks` (`DB_URL`) et le ré-exposer dans `agent.py`.
5. Durcir `upsert_stagiaires` (pydantic) pour la défense RGPD.
6. Vérification end-to-end : `make up && make migrate && make seed && make ingest && make chat`.
