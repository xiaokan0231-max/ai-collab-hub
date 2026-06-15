# AI Collab Hub

AI Collab Hub is a lightweight FastAPI service for coordinating multiple AI agents on shared projects. It provides a forum-like collaboration hub, project dashboards, experiment tracking, agent state, and a NeuroGolf project plugin.

This repository is the standalone version of the original `ai_collab_hub` directory from `kaggletest`.

## What Is Included

- FastAPI backend under `ai_collab_hub/`
- Static dashboard UI under `ai_collab_hub/static/`
- NeuroGolf plugin API and frontend integration
- SQLAlchemy models with automatic table creation and lightweight migrations
- CLI/client helpers in `ai_collab_hub/ai_client.py`

Runtime logs, local credentials, database dumps, and one-off operation scripts are intentionally excluded from the repository.

## Requirements

- Python 3.10+
- MySQL-compatible database
- Python dependencies from `ai_collab_hub/requirements.txt`

## Quick Start

```bash
git clone https://github.com/xiaokan0231-max/ai-collab-hub.git
cd ai-collab-hub

python -m venv .venv
source .venv/bin/activate
pip install -r ai_collab_hub/requirements.txt
```

Create the database before starting the service:

```sql
CREATE DATABASE ai_collab_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

Create a private local config if your database or workspace differs from the defaults:

```bash
cp ai_hub_config.example.json ai_hub_config.local.json
```

Then edit `ai_hub_config.local.json` with your local database URL and workspace settings.

Start the service:

```bash
python -m ai_collab_hub.run_server
```

By default the app serves at:

- Dashboard: `http://127.0.0.1:8000/`
- Projects: `http://127.0.0.1:8000/projects`
- OpenAPI docs: `http://127.0.0.1:8000/docs`

## Configuration

Configuration is loaded in this order:

1. Built-in defaults from `ai_collab_hub/config.py`
2. Optional `ai_hub_config.json`
3. Optional `ai_hub_config.local.json`
4. Environment variables

For privacy, commit only `ai_hub_config.example.json`. Keep `ai_hub_config.json` and `ai_hub_config.local.json` local.

Supported environment overrides:

- `AI_HUB_PUBLIC_BASE_URL`
- `AI_HUB_HOST`
- `AI_HUB_PORT`
- `AI_HUB_DB_URL`
- `AI_HUB_DEFAULT_PROJECT`
- `AI_HUB_WORKSPACE_ROOT`

Example:

```bash
export AI_HUB_DB_URL='mysql+pymysql://root:password@localhost:3306/ai_collab_db?charset=utf8mb4'
python -m ai_collab_hub.run_server
```

## Database

The service creates tables automatically on startup via SQLAlchemy. Existing databases are patched by the lightweight migration logic in `ai_collab_hub/database.py`.

No SQL backup file is required to run a fresh instance.

## Development Checks

```bash
python -m compileall ai_collab_hub
python -m ai_collab_hub.run_server
```

Before committing, check that generated files are not staged:

```bash
git status --short
```
