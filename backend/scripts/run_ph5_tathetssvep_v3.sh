#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "Användning: $0 SNAPSHOT_DB OUTPUT_DIR" >&2
  exit 2
fi

db_path=$1
output_dir=$2
python_bin=${PH5_PYTHON:-.venv/bin/python}
backend_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)

cd "$backend_dir"

if [[ ! -r "$db_path" ]]; then
  echo "Databassnapshoten kan inte läsas: $db_path" >&2
  exit 2
fi
if [[ ! -x "$python_bin" ]]; then
  echo "Pythonmiljön saknas eller kan inte köras: $python_bin" >&2
  exit 2
fi

mkdir -p "$output_dir"

run_one() {
  local product=$1
  local budget=$2
  local output="$output_dir/ph5-v3-${product}-${budget}.json"
  echo "$(date -Iseconds) startar ${product} ${budget} rader"
  "$python_bin" -B scripts/ph5_radvalsablation.py \
    --db "$db_path" \
    --fixed-payout-cohort \
    --skip-hamming \
    --bootstrap-iters 2000 \
    --product "$product" \
    --budget "$budget" \
    --json "$output"
  echo "$(date -Iseconds) klar ${product} ${budget} rader: ${output}"
}

run_one stryktipset 4096
run_one stryktipset 5000
run_one europatipset 4096
run_one europatipset 5000
