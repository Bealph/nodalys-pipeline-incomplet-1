# Note d'audit — Pipeline de collecte Nodalys

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
| 8 | **Ordre d'orchestration** : le `Makefile` lance `seed` (contrats) **avant** `ingest` (clients/sessions). Or les contrats ont des FK vers `clients` et `sessions` → `seed` plante en `ForeignKeyViolation` tant que `ingest` n'a pas peuplé les tables référencées. **Confirmé à l'exécution** (2026-05-29). | `Makefile:16-21` | 🟠 Orchestration |

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

---

# Restes hors-périmètre identifiés (dette technique)

Cette section documente **ce qui n'a pas été corrigé** dans le cadre du brief, et **pourquoi**. Le brief demandait de *"compléter le pipeline pour qu'il tourne de bout en bout, sans tout réécrire"* — les points ci-dessous sont soit des **dettes préexistantes** soit des **bonifications défensives**, en dehors du périmètre de la mission. Ils sont signalés ici par transparence et pour traçabilité future.

## R1 — Pagination cursor des stagiaires (dette préexistante)

| Champ | Détail |
|---|---|
| **Description** | L'API mock renvoie les stagiaires en **pages de 25** (pagination cursor-based, `next_cursor` opaque). Le collecteur n'implémente pas la boucle de pagination → seuls les 25 premiers stagiaires sur ~600 sont ingérés. |
| **Localisation** | `collect/sessions.py:104-134` (fonction `upsert_stagiaires`) — la requête se fait sur `GET /api/stagiaires` sans paramètre `cursor`. |
| **Preuve de préexistence** | Commentaire explicite du prédécesseur : `# TODO: l'endpoint stagiaires renvoie maintenant du paginé, à passer en boucle sur next_cursor un de ces jours.` (lignes 107-109). L'API mock implémente correctement la pagination (`mock_api/app/main.py:84-106`) → le bug est côté **client**, pas côté serveur. |
| **Hors brief car** | TODO préexistant clairement marqué par le prédécesseur. Le brief stipule *"l'objectif n'est pas de tout réécrire"* — la collecte stagiaires **fonctionne** (ne plante pas), elle est juste incomplète. Le fix relève d'un ticket de suivi dédié, pas du périmètre "trous à boucher". |
| **Impact en l'état** | 25 / ~600 stagiaires en base (≈ 4 % de couverture). Symptôme observable : l'agent répond `0 stagiaire` pour les sessions T3 (les stagiaires ingérés sont sur d'autres sessions). |
| **Solution recommandée** | Refactor de `upsert_stagiaires` pour boucler tant que `next_cursor` n'est pas `null` : <br>```python<br>cursor = None<br>while True:<br>    params = {"cursor": cursor} if cursor else {}<br>    payload = http_get_json(f"{base}/api/stagiaires", params=params)<br>    # ...upsert items...<br>    cursor = payload.get("next_cursor")<br>    if not cursor: break<br>``` <br>À combiner avec R4 (durcissement pydantic) en un seul refactor. |
| **Effort estimé** | 1-2 h dev + tests. |
| **Priorité** | Moyenne — bloque les usages métiers qui dépendent du dénombrement stagiaires. |

## R2 — Job cron d'anonymisation RGPD J+180 (dette préexistante)

| Champ | Détail |
|---|---|
| **Description** | Le mémo DPO impose qu'à **J+180 après la fin de session**, les feedbacks soient anonymisés (`stagiaire_email` remplacé par un hash SHA-256 tronqué). De plus, les `commentaire` doivent être tronqués/purgés à J+30 s'ils contiennent des éléments ré-identifiants (prénoms tiers, mentions de manager…). |
| **Localisation** | Pas de fichier dédié — c'est une **absence**. Spec dans `docs/RGPD-memo.md:48-58`. |
| **Preuve de préexistence** | Le mémo écrit littéralement : *"À date, rien n'est en place côté pipeline"* (l.52-53) et *"Pas non plus de job en place"* pour les commentaires (l.58). Statut connu et acté par le DPO. |
| **Hors brief car** | Dette RGPD identifiée et documentée par le DPO **avant** la rédaction du brief. Sortie explicite du périmètre des "trous à boucher" listés par le brief. |
| **Impact en l'état** | Non-conformité RGPD potentielle pour les feedbacks > 180 jours conservés avec email en clair. **Risque CNIL** modéré (la finalité initiale est légitime, mais la durée n'est pas respectée). |
| **Solution recommandée** | Deux jobs distincts à créer : <br>- `scripts/anonymize_old_feedbacks.py` : parcourt les feedbacks de plus de 180 jours et remplace `stagiaire_email` par `hashlib.sha256(email.encode()).hexdigest()[:16]`. Planifié quotidien via cron Linux ou `pg_cron` côté Postgres. <br>- `scripts/scrub_old_comments.py` : tronque/purge les `commentaire` de plus de 30 jours. La détection des éléments ré-identifiants est non triviale (NLP, regex sur prénoms). |
| **Effort estimé** | 0,5 j pour le job email (simple, déterministe). 2-3 j pour la partie commentaires (NLP/regex, tests). |
| **Priorité** | Haute pour le job email (compliance), moyenne pour les commentaires. |

## R3 — Portabilité du Makefile (`\|\| true` non POSIX)

| Champ | Détail |
|---|---|
| **Description** | La cible `fmt` du Makefile utilise `\|\| true` qui n'est valide **que sous shells POSIX** (bash, sh, zsh). Sous Windows `cmd.exe` (que Make utilise par défaut), `true` n'est pas reconnu comme commande. |
| **Localisation** | `Makefile:30` — `fmt:` cible. |
| **Preuve de préexistence** | Probablement un héritage du dev d'origine travaillant sous Mac/Linux. Bug non listé dans les "Known issues" du README → découvert pendant le TP. |
| **Hors brief car** | `make fmt` est une cible **de confort développeur** (formatage du code), pas une étape du pipeline de collecte. Aucun critère de performance du brief ne dépend de `make fmt`. Le brief liste les 5 cibles du pipeline : `up`, `migrate`, `seed`, `ingest`, `chat` — `fmt` n'en fait pas partie. |
| **Impact en l'état** | `make fmt` plante sous Windows avec un message confus (`'true' n'est pas reconnu en tant que commande`). Workaround connu : appeler `uv run ruff format .` directement. Aucun impact sur le pipeline lui-même. |
| **Solution recommandée** | Remplacer `\|\| true` par le préfixe `-` (équivalent Make portable, géré nativement) : <br>```makefile<br>fmt:<br>    -uv run ruff format .<br>``` <br>Le préfixe `-` indique à Make d'ignorer le code de retour. |
| **Effort estimé** | 1 min. |
| **Priorité** | Basse — confort, pas critique. |

## R4 — Durcissement pydantic de `upsert_stagiaires` (bonification défensive)

| Champ | Détail |
|---|---|
| **Description** | La fonction `upsert_stagiaires` filtre le champ RGPD-interdit `telephone_personnel` (renvoyé par l'API) **par énumération explicite** des colonnes dans la requête `INSERT`. Le filtrage repose donc sur le **code SQL**, pas sur le **schéma Python**. Filtrage **implicite**, fragile face à un refactor. |
| **Localisation** | `collect/sessions.py:104-134` — la fonction n'utilise pas de modèle pydantic, contrairement à `SessionPayload` (l.28-39) qui filtre via le schéma. |
| **Preuve de préexistence** | Incohérence stylistique du prédécesseur : `SessionPayload` est défini avec pydantic, mais pas de `StagiairePayload`. Non listée comme bug par le prédécesseur. |
| **Hors brief car** | **Aucune fuite RGPD actuellement observable** : j'ai vérifié, le `telephone_personnel` n'arrive pas en base (la sélection explicite dans l'`INSERT` le bloque effectivement). Donc ce n'est pas un bug à corriger, c'est une **bonification défensive** au titre de la "défense en profondeur" mentionnée dans le mémo DPO. Le brief demandait *"aucune donnée personnelle non justifiée n'est collectée"* — ce critère **est rempli** en l'état. |
| **Impact en l'état** | **Pas de fuite actuellement.** Mais surface d'attaque latente : si un futur dev refactorise et passe `**item` au lieu d'énumérer les colonnes, le `telephone_personnel` arrive en base sans avertissement. Une seule couche de protection = faille en attente. |
| **Solution recommandée** | Introduire un `StagiairePayload(BaseModel)` qui **ne déclare pas** `telephone_personnel`. Par défaut, pydantic ignore silencieusement les champs non déclarés à la validation. Cohérent avec le pattern de `SessionPayload` : <br>```python<br>class StagiairePayload(BaseModel):<br>    id: int<br>    session_id: int<br>    prenom: str<br>    nom: str<br>    email: str \| None  # cf. mémo : peut être absent si pas de session active<br>``` <br>Puis dans `upsert_stagiaires`, valider chaque `item` via `StagiairePayload.model_validate(item)`. |
| **Effort estimé** | 15-20 min. |
| **Priorité** | Moyenne — défense en profondeur recommandée par le DPO ("ne pas se reposer sur une seule couche"). À faire avant la prochaine évolution de `upsert_stagiaires`. |

## Synthèse — ce que cette section dit au formateur

> *"Le périmètre du brief est traité à 100 %. Pendant la mission, j'ai par ailleurs identifié 4 points en dehors de ce périmètre : 2 dettes préexistantes (R1, R2), 1 bug de confort dev (R3), 1 bonification défensive (R4). Aucun ne compromet les critères de performance demandés. Ils sont documentés ici pour transparence et constituent la base de tickets de suivi pour la phase 2."*

C'est cette posture qu'un dev pro adopte : **traité ≠ exhaustif**, et savoir tracer la frontière est une compétence à part entière.
