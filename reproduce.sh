#!/usr/bin/env bash
# Reproduce the SARAI benchmark on a clean machine.
#
#   ./reproduce.sh              full: start services, load data, verify federation
#   ./reproduce.sh --analysis   only the 16 published-value assertions (no services)
#
# What this proves, and what it does not, is set out in REPRODUCIBILITY.md.
set -euo pipefail

cd "$(dirname "$0")"
PY="${PYTHON:-python3}"
ANALYSIS_ONLY=0
[ "${1:-}" = "--analysis" ] && ANALYSIS_ONLY=1

say() { printf '\n\033[1m== %s\033[0m\n' "$*"; }

# ---------------------------------------------------------------- analysis half
# Runs anywhere: reads the one committed benchmark run and asserts that the
# scripts still print the manuscript's published numbers.
say "analysis: asserting published values"
"$PY" tools/assert_published_values.py

if [ "$ANALYSIS_ONLY" = "1" ]; then
  say "done (analysis only)"
  exit 0
fi

# ---------------------------------------------------------------- data half
# Needs the federated stack. PrestoDB 0.284 is the engine the patent names.
say "fetching the frozen datasets (release asset; no Kaggle token needed)"
"$PY" tools/fetch_datasets.py --only release || {
  echo "The release asset could not be fetched. Set GH_TOKEN (or GITHUB_TOKEN) to a"
  echo "token with access to the repository, or fetch the sources individually with"
  echo "  python3 tools/fetch_datasets.py"
  exit 2
}

say "starting postgres, mariadb and the federation engine"
if ! command -v docker >/dev/null 2>&1; then
  echo "docker not found. Either install it, or run: ./reproduce.sh --analysis"
  exit 1
fi
docker compose up -d

say "waiting for the federation engine to accept queries"
for i in $(seq 1 60); do
  if curl -fsS http://localhost:8080/v1/info >/dev/null 2>&1; then break; fi
  [ "$i" = 60 ] && { echo "engine did not come up"; docker compose logs presto | tail -30; exit 1; }
  sleep 5
done
curl -fsS http://localhost:8080/v1/info | head -c 200; echo

# The engine is the one product the manuscript and the patent disagree on, so
# record which one actually ran. PrestoDB and Trino report different values here.
say "recording the engine identity"
curl -fsS http://localhost:8080/v1/info | "$PY" -c \
  'import json,sys; d=json.load(sys.stdin); print("  nodeVersion:", d.get("nodeVersion",{}).get("version"), "| environment:", d.get("environment"))' \
  2>/dev/null || true

say "loading the five domains"
"$PY" framework/load_federated_tables.py

say "verifying every gold query executes and satisfies its validator"
"$PY" tools/verify_gold_queries.py

say "done"
cat <<'EOF'

  Analysis: verified (16 published values).
  Data:     verified (all 50 gold queries, cross-engine joins included).

  Not covered here, by design: the hosted model accuracies, the dashboard, and
  the orchestration layer. See REPRODUCIBILITY.md for why each one is out of
  scope and what evidence exists for it instead.
EOF
