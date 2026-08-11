#!/bin/bash
# Start/stopp av serverns nio com.saman-tjänster. All logik ligger i
# spelkompisen_tjanster.py, som menyraden också går genom.
#
#   ./tjanster.sh status
#   ./tjanster.sh omstart backend
#   ./tjanster.sh stopp charter --permanent
set -e
ROOT="$(cd "$(dirname "$0")" && pwd)"

# Systemets python3 är 3.9 här; den användarlokala runtimen är 3.13.
PY=/Users/saman/.local/spelkompisen-runtime/bin/python3
[ -x "$PY" ] || PY=/usr/bin/python3

exec "$PY" "$ROOT/spelkompisen_tjanster.py" "$@"
