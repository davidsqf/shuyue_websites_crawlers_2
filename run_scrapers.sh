#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

run_job() {
  local name="$1"
  local script="$2"

  (
    cd "$ROOT"
    python -u "$script"
  ) | sed -e "s/^/[$name] /"
}

declare -a pids=()
declare -a names=()
echo "[META] launching APRA scraper"
run_job "APRA" "src/correct_apra.py" &
pids+=($!)
names+=("APRA")
echo "[META] launching RBA scraper"
run_job "RBA" "src/correct_rba_3.py" &
pids+=($!)
names+=("RBA")
echo "[META] launching FMA scraper"
run_job "FMA" "src/correct_fma_govt_nz_2.py" &
pids+=($!)
names+=("FMA")

status=0
for idx in "${!pids[@]}"; do
  pid="${pids[$idx]}"
  name="${names[$idx]}"
  if ! wait "$pid"; then
    exit_code=$?
    status=1
    echo "[META] ${name} scraper failed (exit ${exit_code})"
  fi
done

if [ "$status" -eq 0 ]; then
  echo "[META] all scrapers finished successfully"
else
  echo "[META] one or more scrapers failed"
fi

exit $status
