#!/usr/bin/env bash
#
# run-carter.sh — one-command local launcher for Carter on macOS.
#
# Starts Postgres (in Docker) if it isn't already running, applies migrations,
# seeds reference data, starts the backend and frontend, waits until both are
# healthy, opens the browser at the app, and streams both logs into this
# terminal. Press Ctrl-C to shut everything down cleanly.
#
# Usage:  ./run-carter.sh
# Env:    KEEP_DB=1   leave the Postgres container running after Ctrl-C
#
set -u -o pipefail

# --- where the repo is (this script lives at its root) ----------------------
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# --- configuration (ports are fixed: the Vite dev proxy targets :8000) ------
BACKEND_PORT=8000
FRONTEND_PORT=5173
PG_CONTAINER=carter-postgres
PG_IMAGE=postgres:16
# Carter runs its own isolated Postgres on a dedicated host port so it never
# collides with any other Postgres you already run on the default 5432. Override
# with CARTER_PG_PORT if 55432 is taken.
PG_PORT="${CARTER_PG_PORT:-55432}"
PG_USER=postgres
PG_PASSWORD=postgres
PG_DB=carter
PG_VOLUME=carter-pgdata
APP_URL="http://localhost:${FRONTEND_PORT}"

# The backend defaults to exactly this URL, but set it explicitly so a stray
# shell environment can't point us at the wrong database.
export DATABASE_URL="postgresql+psycopg://${PG_USER}:${PG_PASSWORD}@localhost:${PG_PORT}/${PG_DB}"

LOG_DIR="${REPO_DIR}/.carter/logs"
BACKEND_LOG="${LOG_DIR}/backend.log"
FRONTEND_LOG="${LOG_DIR}/frontend.log"

# --- colours ----------------------------------------------------------------
BOLD=$'\033[1m'; DIM=$'\033[2m'; RESET=$'\033[0m'
RED=$'\033[31m'; GREEN=$'\033[32m'; YELLOW=$'\033[33m'
CYAN=$'\033[36m'; MAGENTA=$'\033[35m'

say()   { printf '%s\n' "${BOLD}${CYAN}▸${RESET} $*"; }
ok()    { printf '%s\n' "${GREEN}✓${RESET} $*"; }
warn()  { printf '%s\n' "${YELLOW}!${RESET} $*"; }
die()   { printf '\n%s\n\n' "${RED}${BOLD}✗ $*${RESET}" >&2; exit 1; }

# --- process/pid tracking + clean shutdown ----------------------------------
BACKEND_PID=""; FRONTEND_PID=""; TAIL_B_PID=""; TAIL_F_PID=""
CLEANED=0

port_pids() { lsof -ti "tcp:$1" 2>/dev/null; }

cleanup() {
  [ "$CLEANED" = 1 ] && return
  CLEANED=1
  printf '\n%s\n' "${BOLD}${CYAN}▸${RESET} Shutting Carter down…"

  # Stop the log streamers first so their output doesn't outlive the services.
  for pid in "$TAIL_B_PID" "$TAIL_F_PID"; do
    [ -n "$pid" ] && kill "$pid" 2>/dev/null
  done
  # Stop the app processes (and, as a backstop, whatever holds their ports).
  for pid in "$BACKEND_PID" "$FRONTEND_PID"; do
    [ -n "$pid" ] && kill "$pid" 2>/dev/null
  done
  for port in "$BACKEND_PORT" "$FRONTEND_PORT"; do
    for p in $(port_pids "$port"); do kill "$p" 2>/dev/null; done
  done
  ok "Backend and frontend stopped."

  if [ "${KEEP_DB:-0}" = 1 ]; then
    warn "Leaving the Postgres container '${PG_CONTAINER}' running (KEEP_DB=1)."
  else
    docker stop "$PG_CONTAINER" >/dev/null 2>&1 \
      && ok "Postgres container '${PG_CONTAINER}' stopped (data kept in volume '${PG_VOLUME}')."
  fi
  printf '%s\n' "${DIM}Logs from this run: ${LOG_DIR}${RESET}"
  exit 0
}
trap cleanup INT TERM

# --- preflight checks -------------------------------------------------------
preflight() {
  say "Checking prerequisites…"

  command -v docker >/dev/null 2>&1 || die \
    "Docker isn't installed. Install Docker Desktop from
   https://www.docker.com/products/docker-desktop , start it, then re-run."

  if ! docker info >/dev/null 2>&1; then
    die "Docker Desktop isn't running. Open Docker Desktop, wait for the whale
   icon to stop animating, then re-run this script."
  fi

  [ -x "${REPO_DIR}/backend/.venv/bin/uvicorn" ] && \
  [ -x "${REPO_DIR}/backend/.venv/bin/alembic" ] || die \
    "Backend dependencies aren't installed. Run:
     cd ${REPO_DIR}/backend
     python3.12 -m venv .venv && source .venv/bin/activate
     pip install -e \".[dev]\""

  command -v node >/dev/null 2>&1 || die \
    "Node.js isn't installed. Install Node 20+ (e.g. 'brew install node'), then re-run."

  [ -x "${REPO_DIR}/frontend/node_modules/.bin/vite" ] || die \
    "Frontend dependencies aren't installed. Run:
     cd ${REPO_DIR}/frontend && npm install"

  # The two app ports must be free. (Postgres' port is handled separately, since
  # we may already own the container on it.)
  for port in "$BACKEND_PORT" "$FRONTEND_PORT"; do
    local pids; pids="$(port_pids "$port")"
    if [ -n "$pids" ]; then
      local who; who="$(ps -o comm= -p "$(echo "$pids" | head -1)" 2>/dev/null)"
      die "Port ${port} is already in use (PID $(echo "$pids" | tr '\n' ' ')${who:+, ${who}}).
   Carter needs it. Stop that process — for example:
     kill $(echo "$pids" | head -1)
   — or quit the app using it, then re-run."
    fi
  done

  command -v mdb-schema >/dev/null 2>&1 || warn \
    "mdbtools not found — uploading a DPM .accdb will fail to convert.
   Install it with 'brew install mdbtools' (pre-converted .sqlite DPMs work without it)."

  ok "Prerequisites look good."
}

# --- Postgres ---------------------------------------------------------------
start_postgres() {
  say "Starting Postgres…"
  local state
  state="$(docker inspect -f '{{.State.Running}}' "$PG_CONTAINER" 2>/dev/null || echo "absent")"

  if [ "$state" = "true" ]; then
    ok "Postgres container '${PG_CONTAINER}' already running."
  elif [ "$state" = "false" ]; then
    docker start "$PG_CONTAINER" >/dev/null || die "Could not start the existing '${PG_CONTAINER}' container."
    ok "Started existing Postgres container '${PG_CONTAINER}'."
  else
    # No container yet — make sure the dedicated host port is free before binding.
    if [ -n "$(port_pids "$PG_PORT")" ]; then
      die "Port ${PG_PORT} (used for Carter's database) is already in use.
   Free it, or re-run with a different port:  CARTER_PG_PORT=<port> ./run-carter.sh"
    fi
    docker run -d --name "$PG_CONTAINER" \
      -e POSTGRES_USER="$PG_USER" \
      -e POSTGRES_PASSWORD="$PG_PASSWORD" \
      -e POSTGRES_DB="$PG_DB" \
      -p "${PG_PORT}:5432" \
      -v "${PG_VOLUME}:/var/lib/postgresql/data" \
      "$PG_IMAGE" >/dev/null || die "Could not start a Postgres container."
    ok "Created Postgres container '${PG_CONTAINER}' (image ${PG_IMAGE})."
  fi

  printf '%s' "  waiting for Postgres to accept connections"
  for _ in $(seq 1 60); do
    if docker exec "$PG_CONTAINER" pg_isready -U "$PG_USER" >/dev/null 2>&1; then
      printf '\n'; ok "Postgres is ready."
      # POSTGRES_DB only creates the database on a *fresh* container init. If the
      # container predates this database name (e.g. after a rename), create it
      # once here so migrations have something to connect to.
      if ! docker exec "$PG_CONTAINER" psql -U "$PG_USER" -tAc \
           "SELECT 1 FROM pg_database WHERE datname='${PG_DB}'" | grep -q 1; then
        docker exec "$PG_CONTAINER" createdb -U "$PG_USER" "$PG_DB" \
          && ok "Created database '${PG_DB}'."
      fi
      return 0
    fi
    printf '.'; sleep 1
  done
  printf '\n'; die "Postgres did not become ready in time. Check: docker logs ${PG_CONTAINER}"
}

# --- migrations + seed ------------------------------------------------------
migrate_and_seed() {
  say "Applying database migrations…"
  ( cd "${REPO_DIR}/backend" && .venv/bin/alembic upgrade head ) \
    || die "Migrations failed. See the output above."
  ok "Database schema is at head."

  say "Seeding reference data…"
  ( cd "${REPO_DIR}/backend" \
      && .venv/bin/python -m app.taxonomy.seed \
      && .venv/bin/python -m app.workflows.seed ) \
    || die "Seeding failed. See the output above."
  ok "Reference data seeded."
}

# --- start services + stream logs -------------------------------------------
stream_log() { # file  label  colour
  tail -n +1 -F "$1" 2>/dev/null \
    | awk -v p="$3$2${RESET} " '{ print p $0; fflush() }' &
}

start_services() {
  mkdir -p "$LOG_DIR"
  : > "$BACKEND_LOG"; : > "$FRONTEND_LOG"

  say "Starting the backend (uvicorn) on :${BACKEND_PORT}…"
  ( cd "${REPO_DIR}/backend" \
      && exec .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port "$BACKEND_PORT" \
  ) >>"$BACKEND_LOG" 2>&1 &
  BACKEND_PID=$!

  say "Starting the frontend (vite) on :${FRONTEND_PORT}…"
  ( cd "${REPO_DIR}/frontend" \
      && exec ./node_modules/.bin/vite --port "$FRONTEND_PORT" --strictPort \
  ) >>"$FRONTEND_LOG" 2>&1 &
  FRONTEND_PID=$!

  stream_log "$BACKEND_LOG"  "[backend] " "$CYAN";    TAIL_B_PID=$!
  stream_log "$FRONTEND_LOG" "[frontend]" "$MAGENTA"; TAIL_F_PID=$!
}

# --- health waits -----------------------------------------------------------
wait_healthy() { # url  name  pid
  local url="$1" name="$2" pid="$3"
  for _ in $(seq 1 90); do
    if ! kill -0 "$pid" 2>/dev/null; then
      warn "The ${name} exited during startup. Recent log:"
      tail -n 25 "$([ "$name" = backend ] && echo "$BACKEND_LOG" || echo "$FRONTEND_LOG")" >&2
      die "The ${name} failed to start (see the log above)."
    fi
    if curl -fsS --max-time 3 "$url" >/dev/null 2>&1; then
      ok "The ${name} is healthy (${url})."
      return 0
    fi
    sleep 1
  done
  die "The ${name} did not become healthy in time (${url})."
}

# --- main -------------------------------------------------------------------
printf '%s\n' "${BOLD}Carter — local launcher${RESET}"
preflight
start_postgres
migrate_and_seed
start_services

say "Waiting for both services to come up…"
# Backend binds 127.0.0.1; Vite binds IPv6 localhost (::1), so probe each on the
# host it actually listens on.
wait_healthy "http://127.0.0.1:${BACKEND_PORT}/health" "backend"  "$BACKEND_PID"
wait_healthy "http://localhost:${FRONTEND_PORT}/"      "frontend" "$FRONTEND_PID"

printf '\n%s\n' "${GREEN}${BOLD}✓ Carter is running.${RESET}  ${BOLD}${APP_URL}${RESET}"
printf '%s\n\n' "${DIM}Streaming logs below. Press Ctrl-C to stop everything.${RESET}"
open "$APP_URL" >/dev/null 2>&1 || warn "Could not open the browser automatically — visit ${APP_URL}"

# Poll for either service exiting. We deliberately do NOT `wait "$PID"`: macOS
# ships bash 3.2, which does not interrupt a `wait <pid>` when a trapped signal
# (Ctrl-C) arrives — it would swallow the shutdown. Sleeping in a loop lets the
# INT/TERM trap fire within ~1s.
while kill -0 "$BACKEND_PID" 2>/dev/null && kill -0 "$FRONTEND_PID" 2>/dev/null; do
  sleep 1
done
# A service exited on its own — tear the rest down.
warn "A service exited unexpectedly — shutting the rest down."
cleanup
