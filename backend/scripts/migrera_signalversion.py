"""Engångsmigration 2026-07-16: git-hash → semantisk signal_version i facitet.

Bakgrund (granskningen runda 2, punkt 5): model_version innehöll repots
HEAD-hash — en docs/CSS-commit skulle fragmentera facitet. Nu gäller:
  - model_version = signal-fingeravtryck per tier (oddset_value.signal_versions)
  - git_hash      = exakt kodversion (ny kolumn, reproducerbarhet)

Denna migration mappar de befintliga raderna:
  - rader stämplade '5cfe78f' (2026-07-13 → 2026-07-16) loggades under EXAKT de
    parametrar dagens fingeravtryck beskriver (ingen algoritm-, parameter-,
    kalibrerings- eller dataändring sedan ffc6d04/b11a7e8) → de FÖRS IN i
    nuvarande fingeravtryck så n bevaras utan att regimer blandas;
    git-hashen flyttas till git_hash-kolumnen.
  - rader med NULL (loggade före versionsstämplingen OCH före identitetsfixen,
    dvs. annan dataregim) lämnas som legacy ('-' i rapporten).

Körning (idempotent — andra körningen ändrar 0 rader):
    cd backend && .venv/bin/python scripts/migrera_signalversion.py
Kräver att backup finns i data/backups/ (processregeln: skript + backup +
rapport, se docs/db-atgarder.md).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.storage import Storage            # noqa: E402
from app.oddset_value import signal_versions  # noqa: E402

OLD_GIT = "5cfe78f"
BACKUP = Path(__file__).resolve().parent.parent / "data" / "backups" \
    / "stryktips-2026-07-16-fore-versionsmigration.db"


def main() -> None:
    if not BACKUP.exists():
        sys.exit(f"AVBRYTER: backup saknas ({BACKUP}) — ta backup först.")
    store = Storage()
    try:
        vers = signal_versions(store)
        print(f"fingeravtryck: sharp={vers['sharp']} model={vers['model']}")
        n_git = store.conn.execute(
            "UPDATE oddset_value_log SET git_hash=? "
            "WHERE model_version=? AND git_hash IS NULL",
            (OLD_GIT, OLD_GIT)).rowcount
        n_sharp = store.conn.execute(
            "UPDATE oddset_value_log SET model_version=? "
            "WHERE tier='sharp' AND model_version=?",
            (vers["sharp"], OLD_GIT)).rowcount
        n_model = store.conn.execute(
            "UPDATE oddset_value_log SET model_version=? "
            "WHERE tier='model' AND model_version=?",
            (vers["model"], OLD_GIT)).rowcount
        store.conn.commit()
        legacy = store.conn.execute(
            "SELECT COUNT(*) FROM oddset_value_log WHERE model_version IS NULL"
        ).fetchone()[0]
        print(f"git_hash satt: {n_git} rader · sharp→{vers['sharp']}: {n_sharp}"
              f" · model→{vers['model']}: {n_model} · legacy (NULL): {legacy}")
    finally:
        store.close()


if __name__ == "__main__":
    main()
