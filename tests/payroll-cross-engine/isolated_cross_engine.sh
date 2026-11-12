#!/usr/bin/env bash
set -euo pipefail
P="$1"; M="$2"; X="$3"; E="$4"; O="$X/evidence"
ip -j address > "$O/net-address.json"
ip -j route > "$O/net-route.json"
python3 -I "$P/harness/supervise.py" --out "$O/supervisor" --timeout 900 -- python3 -I "$X/cross_engine_runner.py" --engine "$E" --candidate-root "$P/candidate" --harness-dir "$P/harness" --migration-runner "$M/migration_runner.py" --output "$O/results"
