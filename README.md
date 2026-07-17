# NoCap

NoCap is a web application for producing EBA regulatory submissions. It ingests EBA DPM
taxonomy releases as immutable versioned snapshots, accepts fact data as XLSX, and
generates submission-ready xBRL-CSV packages (zip) with a validation report — replacing an
external vendor for the EBA filing workflow (v1 target: COREP LCR, end to end).

## Stack

- **Backend:** Python 3.12, FastAPI, SQLAlchemy 2.x, Alembic, Postgres
- **Frontend:** React + Vite, TypeScript, Tailwind
- **Hosting:** Railway (web service + Postgres); twelve-factor config via env vars

## Local development

Prerequisites: Python 3.12, Node 20+, and a local Postgres (a Docker container
is fine).

**Postgres** — any local instance works; the backend defaults to
`postgresql+psycopg://postgres:postgres@localhost:5432/nocap`. With Docker:

```bash
docker run -d --name nocap-pg -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=nocap -p 5432:5432 postgres:16
```

**Backend** (FastAPI, from `backend/`):

```bash
cd backend
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env            # adjust DATABASE_URL if needed
alembic upgrade head            # wires Alembic against Postgres
uvicorn app.main:app --reload   # http://127.0.0.1:8000
# verify: curl http://127.0.0.1:8000/health  -> {"status":"ok",...}
pytest                          # run the test suite
```

**Frontend** (React + Vite, from `frontend/`):

```bash
cd frontend
npm install
npm run dev                     # http://localhost:5173
```

## Documentation

The engineering brief and architecture live in [`CLAUDE.md`](./CLAUDE.md) — start there.
