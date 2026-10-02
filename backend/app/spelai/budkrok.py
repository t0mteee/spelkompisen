"""PreToolUse-krok för chattbudet (`app/spelai/chattbud.py`).

Budet får bara skicka till EN mottagare: den chattsession som facitsidan valt
och lämnat som argument. Allt annat stoppas med exit 2, vad texten eller
modellen än säger. Kroken läser bara stdin och skriver bara stderr; den körs
som fristående skript (`python -B budkrok.py <mottagare>`) och använder bara
standardbiblioteket.
"""
from __future__ import annotations

import json
import sys


def prova(data, mal: str) -> tuple[int, str]:
    """(0, "") = tillåt, (2, orsak) = stoppa."""
    if not isinstance(data, dict):
        return 2, "budkrok: ogiltig krokindata"
    if data.get("tool_name") != "SendMessage":
        return 2, f"budet får bara använda SendMessage, inte {data.get('tool_name')!r}"
    inp = data.get("tool_input")
    if not isinstance(inp, dict):
        return 2, "budkrok: tool_input saknas"
    if inp.get("to") != mal:
        return 2, f"budet får bara skicka till {mal!r}, inte {inp.get('to')!r}"
    if inp.get("notify_when_idle"):
        return 2, "budet prenumererar aldrig på andra sessioner"
    return 0, ""


def main(argv=None, stdin=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1 or not argv[0]:
        print("budkrok: mottagaren saknas", file=sys.stderr)
        return 2
    try:
        data = json.load(stdin or sys.stdin)
    except ValueError:
        data = None
    code, orsak = prova(data, argv[0])
    if orsak:
        print(orsak, file=sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main())
