"""KAPPA finns i två exemplar: `builder.KAPPA` (backend, radval + PH3) och
`const KAPPA` i frontend/src/lib/poolEv.js (`evalRows`). CLAUDE.md kräver att de
hålls identiska, men fram till nu var den meningen det enda som höll dem
samman. Det här testet gör kravet körbart — det körs i `tools/kontroll.sh`
och stoppar en push där bara ena sidan ändrats.
"""
import re
import unittest
from pathlib import Path

from app.builder import KAPPA

APP_JSX = Path(__file__).resolve().parents[2] / "frontend" / "src" / "lib" / "poolEv.js"


def frontend_kappa() -> dict[str, dict[int, float]]:
    src = APP_JSX.read_text(encoding="utf-8")
    m = re.search(r"^(?:export )?const KAPPA = \{(.*?)^\}", src, re.S | re.M)
    assert m, "const KAPPA = { ... } hittades inte i lib/poolEv.js"
    table: dict[str, dict[int, float]] = {}
    for prod, body in re.findall(r"(\w+):\s*\{([^}]*)\}", m.group(1)):
        table[prod] = {int(c): float(v)
                       for c, v in re.findall(r"(\d+):\s*([\d.]+)", body)}
    return table


class KappaSynkTests(unittest.TestCase):
    def test_frontend_och_backend_har_samma_kappa(self) -> None:
        fe = frontend_kappa()
        self.assertEqual(set(KAPPA), set(fe), "olika produkter i de två tabellerna")
        for prod, tiers in KAPPA.items():
            self.assertEqual(tiers, fe[prod], f"KAPPA[{prod}] skiljer sig")

    def test_tabellen_ar_inte_tom(self) -> None:
        # Skydd mot att regexen tyst matchar fel block och jämför tomt mot tomt.
        self.assertGreaterEqual(len(frontend_kappa()), 5)
        self.assertIn(13, frontend_kappa()["stryktipset"])
