#!/usr/bin/env bash
# Launch NLQ on DEV (DCL :8104 + aos-dev glmeqbn).
#
# Why this exists (aam_deferred_work.md #45): a bare `pm2 restart nlq-backend`, or a
# launch that does `source .env`, boots the process with PROD env (DCL :8104→:8004,
# AOS_NLQ yuxrdo). src/nlq/env_guard.py overrides os.environ to dev at runtime, but
# modules that read os.environ at import time can capture the prod values first. This
# launcher sources .env.development BEFORE python starts, so the process env is all-dev
# from the outset; load_and_guard_env() then confirms DEV (and still fail-louds on a
# mixed or unguarded-prod config). To run PROD, launch with AOS_ENV=prod and .env only.
set -euo pipefail
cd "$(dirname "$0")/.." || exit 1
set -a
# shellcheck disable=SC1091
source .env 2>/dev/null || true            # prod base (DB creds, shared keys)
source .env.development 2>/dev/null || true # dev overlay WINS — DCL :8104 + aos-dev
set +a
# shellcheck disable=SC1091
source .venv/bin/activate 2>/dev/null || true
exec python3 -m uvicorn src.nlq.main:app --host 0.0.0.0 --port 8005 --reload
