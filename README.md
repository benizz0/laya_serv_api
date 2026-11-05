# laya_serv_api

Serveur HTTP Docker pour un checkpoint [Laya](https://huggingface.co/convaiinnovations/laya) fine-tuné,
basé sur le serveur intégré de laya (`laya.serve`, protocole `/v1/systemone`).

- Le modèle **n'est pas dans l'image** : il est monté en volume read-only sur `/models/laya`.
- 100 % local : aucun modèle téléchargé depuis le Hub (`HF_HUB_OFFLINE=1`), poids chargés une seule fois.
- Authentification Bearer obligatoire : le serveur refuse de démarrer sans `LAYA_API_KEY`.

## Fichiers

| Fichier | Rôle |
|---|---|
| `Dockerfile` | python 3.12 + torch CPU + `laya[serve]==0.4.24` (sans modèle) |
| `.dockerignore` | contexte de build limité à `app.py` |
| `app.py` | vérifie la config (clé API, volume), Router limité au checkpoint local, `laya.serve.create_app` |
| `docker-compose.yml` | build + run, port 8000, volume du modèle |
| `.env.example` | variables à copier dans `.env` |

## Pré-requis : le checkpoint

Un dossier produit par l'entraînement Laya (`laya.train.save_checkpoint`) :

```
models/laya/
├── model.safetensors
├── rl_agent_config.json
├── encoder/config.json
└── tokenizer/
    ├── tokenizer.json
    └── tokenizer_config.json
```

Par défaut, compose monte `./models/laya`. Pour un autre dossier : `LAYA_MODEL_HOST_DIR` dans `.env`.
`models/` est ignoré par git.

## Image

Publiée sur GitHub Container Registry par GitHub Actions (`.github/workflows/docker-publish.yml`)
à chaque push sur `main` et à chaque tag `v*` :

```bash
docker pull ghcr.io/benizz0/laya_serv_api:latest
```

Tags : `latest` (main), `sha-<commit>`, `X.Y.Z` / `X.Y` (tags git `vX.Y.Z`). linux/amd64, CPU.

## Lancer

```powershell
Copy-Item .env.example .env      # Linux/macOS : cp .env.example .env
# générer une clé et la mettre dans LAYA_API_KEY :
[Convert]::ToBase64String([Security.Cryptography.RandomNumberGenerator]::GetBytes(32))   # ou : openssl rand -base64 32
docker compose up -d             # tire l'image ghcr ; --build pour construire localement
docker compose logs -f
```

Changer de modèle = changer `LAYA_MODEL_HOST_DIR` puis `docker compose up -d` (pas de rebuild).

Sans compose :

```bash
docker run -d -p 8000:8000 -e LAYA_API_KEY=<clé> \
  -v /chemin/vers/checkpoint:/models/laya:ro ghcr.io/benizz0/laya_serv_api:latest
```

Build local : `docker build -t laya-server .`

## Authentification

- Vérification faite par laya (`laya.serve.create_app`) : header `Authorization: Bearer <LAYA_API_KEY>`
  comparé en temps constant (`hmac.compare_digest`), 401 sinon, sur toutes les routes.
  `/docs` et `/openapi.json` sont désactivés quand une clé est définie.
- laya démarrerait **sans auth** si la clé est vide : `app.py` refuse de démarrer dans ce cas.
  `LAYA_ALLOW_NO_AUTH=1` force le mode ouvert (tests locaux uniquement).
- `/health` sans clé répond seulement `{"status":"ok"}` (healthcheck) ; le détail exige la clé.
- Le serveur parle HTTP en clair : exposé sur Internet, le placer derrière un reverse proxy HTTPS
  (Caddy, Traefik, nginx).

## Appeler

```bash
curl -s http://localhost:8000/v1/systemone \
  -H "Authorization: Bearer $LAYA_API_KEY" -H 'content-type: application/json' -d '{
  "state": {"customer_message": "charged twice, refund please"},
  "questions": {
    "dept": {"type": "choice", "instructions": "Which team?",
             "criteria": {"billing": "payments, refunds", "tech": "bugs, login"}},
    "urgency": {"type": "score", "instructions": "How urgent?",
                "criteria": ["can wait", "normal", "urgent"]}
  }
}'
```

- `POST /v1/systemone` : un `state` + `questions`
- `POST /v1/systemone/batch` : `states` (max 64) + `questions`
- `GET /health`

Question `score` : `criteria` est une **liste** de niveaux, index 0 en premier.

## Variables

| Variable | Défaut | |
|---|---|---|
| `LAYA_API_KEY` | — | **Obligatoire.** Bearer token. |
| `LAYA_MODEL_HOST_DIR` | `./models/laya` | dossier du checkpoint sur l'hôte (compose) |
| `LAYA_DEVICE` | `cpu` | `cpu`, `cuda`, `auto` |
| `LAYA_THREADS` | `4` | threads torch CPU, ≤ cœurs physiques |
| `LAYA_MAX_CONCURRENT` | `16` | requêtes simultanées, excédent = 503 |
| `LAYA_MODEL_NAME` | `laya-local` | nom accepté dans le champ `model` |
| `LAYA_ALLOW_NO_AUTH` | `0` | `1` = démarrer sans clé (tests) |

Les autres variables de `laya.serve` (`LAYA_PORT`, `LAYA_LOG_LEVEL`, `LAYA_MAX_BATCH_TOKENS`, …) restent valables.

## GPU

Décommenter dans `docker-compose.yml` le `build.args` (`cu126`) et le bloc `deploy`, mettre
`LAYA_DEVICE=cuda`. Nécessite le NVIDIA Container Toolkit (ou Docker Desktop WSL2) et un driver récent.

## Mesures indicatives (CPU, 4 threads, checkpoint mmBERT-base)

Image ~1,3 Go · RAM ~1,6 Go · démarrage ~6 s · ~430 ms pour 1 état + 2 questions.
