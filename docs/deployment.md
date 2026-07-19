# Deploying Carter to Railway

Carter deploys as a **single Railway service** built from the repo `Dockerfile`,
backed by a **Railway Postgres** database and a **persistent volume**. The one
container runs FastAPI (uvicorn), which serves both the `/api` surface and the
built React SPA as static files.

> **Naming note.** The live Railway service, volume, and generated domain are
> named `nocap`/`nocap-production…` from before the rename to Carter; they are
> deliberately left as-is (renaming the service would change the public URL).
> References to `nocap` below that name the *deployed Railway resources* are
> correct; the product itself is Carter.

- **Why one service, not two.** The frontend calls the API on relative `/api`
  paths, so same-origin serving removes CORS entirely. The app needs a single
  durable volume (the DPM/taxonomy/run store) that only the backend touches, and
  a demo is simpler to operate as one deployable. A static-CDN + API split buys
  nothing here and adds a cross-origin surface to configure.

---

## 1. What the deployed app needs, and why

| Concern | Decision |
| --- | --- |
| **Persistent storage** | Railway filesystems are ephemeral. A **20 GB volume** mounted at `/data` holds the converted DPM SQLite, the original DPM upload, taxonomy packages, the Arelle cache, and all run artifacts. One real snapshot is ~0.9 GB; 20 GB leaves headroom for several releases + runs. |
| **Database** | Railway Postgres. The app reads `DATABASE_URL`; it auto-rewrites Railway's `postgresql://…` scheme to the `postgresql+psycopg://` driver it uses, so the provider value works verbatim. |
| **System deps** | `mdbtools` (installed in the image) converts the EBA DPM `.accdb` to SQLite. Arelle runs in-process (Python dep) and fully **offline** — the eurofiling core files are vendored in the repo and shipped in the image. |
| **Arelle writable config** | Arelle creates `~/.config/arelle` on startup. The image sets `XDG_CONFIG_HOME=/data/arelle` (on the volume, writable + persistent) so it never aborts. |
| **Memory** | Arelle loads the full EBA DTS per formula run (~2 min), and an `.accdb` ingest can spike ~0.5–1.5 GB transiently. Provision **8 GB RAM** so neither OOMs. This is a demo-scale budget, not a cost-optimised one. |

### The ~720 MB DPM upload, and the SQLite fallback

The EBA DPM 2.0 database is a ~720 MB Microsoft Access `.accdb`. Uploading it
through the web is memory-heavy (it is buffered in RAM) and slow/timeout-prone
over Railway's HTTP edge. So the DPM slot **also accepts a pre-converted SQLite**
(~80 MB): convert the `.accdb` locally, upload the small file instead. Both
routes produce an identical query database; the release records which form it
came in by (visible under **Audit details** on the release).

**Local conversion command** (needs `mdbtools`):

```bash
# once — install the converter
brew install mdbtools                 # macOS
sudo apt-get install -y mdbtools      # Ubuntu/Debian

# from the repo's backend/ directory, with the virtualenv active:
python -m app.taxonomy.convert "DPM_Database_2.0.accdb" dpm.sqlite
```

This writes `dpm.sqlite` (~80 MB). Upload **that** as the DPM database in the
release wizard, in place of the `.accdb`. The wizard also shows this command
under *"Is the DPM database too large to upload? Convert it first"*.

> Uploading the original `.accdb` still works if you prefer — the image includes
> `mdbtools` and the server converts it. The SQLite route just sidesteps the big
> upload and the server-side conversion spike.

---

## 2. Environment variables (twelve-factor, no secrets in the repo)

Most config is baked into the image as sane production defaults; you only set a
few in Railway. **Nothing here is a secret except the database URL, which comes
from Railway's own Postgres via a reference variable.**

| Variable | Value | Set where |
| --- | --- | --- |
| `DATABASE_URL` | `${{Postgres.DATABASE_URL}}` | **You set** (Railway reference — see step 4) |
| `DATA_DIR` | `/data` | Image default (matches the volume mount) |
| `XDG_CONFIG_HOME` | `/data/arelle` | Image default |
| `STATIC_DIR` | `/app/frontend/dist` | Image default |
| `ARELLE_ENABLED` | `true` | Image default |
| `ENVIRONMENT` | `production` | Image default |
| `PORT` | injected by Railway | Railway (uvicorn binds it automatically) |

You normally only add **`DATABASE_URL`**. Set the others in Railway only to
override a default.

---

## 3. Manual steps in the Railway UI

Do these once. (You are logged in as `paul_broome@icloud.com`; the Railway CLI
is also authenticated on this machine for the migration/verification steps.)

### Step A — Create the project + Postgres
1. Railway dashboard → **New Project** → **Deploy PostgreSQL** (or *Empty
   Project*, then **+ New → Database → PostgreSQL**).
2. Name the project e.g. **nocap**. You now have a `Postgres` service.

### Step B — Add the app service from the repo
3. In the project → **+ New → GitHub Repo** → select the Carter repo →
   branch **`feat/deployment`**.
4. Railway detects the root `Dockerfile` and `railway.json` and starts a build.
   Let the first build finish (it may fail to boot until the volume + DB are set
   — that's expected; finish the next steps then redeploy).

### Step C — Attach the volume
5. Select the **app service** → **Settings → Volumes → + New Volume**.
6. **Mount path:** `/data` — **Size:** `20 GB`.

### Step D — Set the environment variable
7. App service → **Variables → + New Variable**:
   - **Name:** `DATABASE_URL`
   - **Value:** `${{Postgres.DATABASE_URL}}`  ← this references the Postgres
     service; Railway substitutes the real URL at deploy time. (If your Postgres
     service is named other than `Postgres`, use that name.)
8. (Optional) confirm the image defaults are present; add any only to override.

### Step E — Generate a public URL
9. App service → **Settings → Networking → Generate Domain** (port **8000**).
   This is your public URL, e.g. `https://nocap-production.up.railway.app`.

### Step F — Redeploy
10. **Deploy** the app service. On boot the container runs migrations + seeds
    automatically (see §4), then serves. Watch **Deploy Logs** for
    `applying database migrations…` → `starting uvicorn…`, and the healthcheck
    on `/health` going green.

### Resource sizing
11. App service → **Settings → Resources** (Pro plan): allow up to **8 GB RAM**
    so Arelle formula runs and any `.accdb` conversion don't OOM.

---

## 4. Migrations and seed against Railway Postgres

The container **auto-runs migrations and seeds on every boot** (idempotent), via
`docker-entrypoint.sh`:

```
alembic upgrade head
python -m app.taxonomy.seed        # regulators (EBA)
python -m app.workflows.seed       # workflow configs + demo entities
```

You do **not** need to run these by hand. If you ever want to (e.g. to inspect),
the Railway CLI can run them against the deployed Postgres:

```bash
railway link                       # pick the nocap project + app service
railway run alembic upgrade head   # runs locally against Railway's DATABASE_URL
```

The app also **fails fast** if the schema isn't at head (a clear startup error
rather than per-request 500s), so a boot that gets past the healthcheck has a
correctly-migrated database.

---

## 5. End-to-end verification checklist

On the public URL:

1. **App loads** — the SPA renders; `GET /health` returns
   `{"status":"ok"}`.
2. **Create a release** — Taxonomies → EBA → *New release*. Upload the three EBA
   files: DPM database (`.accdb`, or the converted `dpm.sqlite`), taxonomy
   package `.zip`, validation-rules `.xlsx`. All three verify on arrival; the
   release then converts in the background to **ready**.
3. **Configure an entity** — Reference Data → an entity (seeded: Meridian Group,
   Nordbank, Thistle) → set its workflow config if desired.
4. **Run a submission** — Reporting → a suite (e.g. LCR) → new run: pick the
   release, reference date, entity; upload the fact XLSX; **Run**.
5. **Confirm outputs** — the run produces the **xBRL-CSV package** (downloadable
   zip), a **structural validation** report, and **formula validation** executes
   (Arelle, ~1–2 min; findings appear with rule statements). The taxonomy
   package slot must be filled for formula validation to run.

---

## 6. Running the image locally (optional smoke test)

```bash
docker build -t carter:local .
docker run --rm -p 8000:8000 \
  -e DATABASE_URL="postgresql://user:pass@host:5432/carter" \
  -v carter-data:/data \
  carter:local
# open http://localhost:8000
```

The container needs a reachable Postgres; point `DATABASE_URL` at one (the app
rewrites the scheme to the psycopg driver automatically).
