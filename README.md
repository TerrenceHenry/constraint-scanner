# Constraint Scanner v1

Initial repository scaffold for a Python 3.11+ service built around FastAPI,
SQLAlchemy, Alembic, PostgreSQL, and typed configuration.

## What is included

- FastAPI application scaffold with a minimal `/health` route
- typed settings loader with YAML + environment variable overrides
- local PostgreSQL stack via Docker Compose
- Alembic configuration and migration directory scaffold
- source-first package layout under `src/`
- minimal pytest coverage for configuration loading

## Quick start

1. Copy the environment template and adjust local values as needed.

```powershell
Copy-Item .env.example .env
```

2. Start PostgreSQL.

```powershell
docker compose up -d postgres
```

3. Install the project in a virtual environment.

```powershell
uv python install 3.11
uv venv --python 3.11 .venv
.venv\Scripts\Activate.ps1
pip install -e .[dev]
```

If you already have a system Python 3.11+ install, this also works:

```powershell
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .[dev]
```

4. Run the API locally.

```powershell
uvicorn constraint_scanner.main:app --reload
```

5. Run the tests.

```powershell
pytest -q
```

## Configuration

- Non-secret defaults live in `config/settings.local.yaml`.
- Example config shape is documented in `config/settings.example.yaml`.
- Secrets must come from environment variables only.
- To point at a different YAML file, set `CONSTRAINT_SCANNER_SETTINGS_FILE`.
- Public Polymarket reads do not require credentials.
- Authenticated Polymarket CLOB trading needs the `CONSTRAINT_SCANNER_POLYMARKET_*` credentials in `.env`.

## Database

- Docker Compose starts PostgreSQL on `localhost:5432`.
- Alembic is configured with `migrations/` as the script location.
- Database models are intentionally not implemented yet.
