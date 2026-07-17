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

> Placeholder — filled in once the scaffold lands.

```bash
# Backend
cd backend && ...

# Frontend
cd frontend && ...
```

## Documentation

The engineering brief and architecture live in [`CLAUDE.md`](./CLAUDE.md) — start there.
