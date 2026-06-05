"""Liten .env-loader (utan beroenden).

Läser backend/.env och lägger nycklar i os.environ om de inte redan finns.
Importeras tidigt i main.py så att t.ex. ODDS_API_KEY är tillgänglig.
"""
from __future__ import annotations

import os
from pathlib import Path

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"


def load_env(path: Path = ENV_PATH) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip().strip('"').strip("'")
        os.environ.setdefault(key, val)


load_env()
