"""Ta bort skotska matcher som football-data levererade som La Liga.

Upptäckt 2026-08-07 under namnkartläggningen inför xG-bakfyllningen: La Ligas
kanoniska lagnamn innehöll arbroath, ayr, morton, partick, raith rvs m.fl.

Orsak: `https://www.football-data.co.uk/mmz4281/2627/SP1.csv` serverar just nu
SKOTSK CHAMPIONSHIP. Filens egen `Div`-kolumn säger `SC1`, alltså avslöjar
källan felet själv — vi läste bara aldrig kolumnen. Fem matcher spelade
2026-08-01 hamnade därmed i `oddset_results` som `la_liga`.

Framtida skydd finns i `_fd_result_rows(..., div=...)`: rader vars `Div` inte
matchar den förväntade koden hoppas över. Det här skriptet städar det som redan
hann skrivas.

Radering är rätt åtgärd här (inte omflaggning): raderna är inte La Liga, och
de finns redan korrekt i `scotland`-sammanhang endast om vi någon gång följer
den ligan — vilket vi inte gör. De bär ingen statistik och ingen prediktion.

Körning:
    .venv/bin/python -B scripts/stada_fel_division_laliga.py [--skarpt]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.storage import Storage                               # noqa: E402

# Klubbarna är skotska och kan aldrig förekomma i La Liga. Listan är
# HÅRDKODAD i skriptet i stället för härledd: ett engångsskript ska beskriva
# ett historiskt tillstånd, inte läsa dagens data och råka städa något annat
# om tabellen ändras. (Samma lärdom som migrera_v22_research_identitet.py.)
SKOTSKA = {
    "arbroath", "ayr", "dunfermline", "inverness c", "livingston",
    "morton", "partick", "queens park", "raith rvs", "stenhousemuir",
}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--skarpt", action="store_true",
                   help="utan flaggan visas bara vad som skulle tas bort")
    args = p.parse_args()

    store = Storage()
    try:
        rows = [dict(r) for r in store.conn.execute(
            "SELECT * FROM oddset_results WHERE league='la_liga'")]
        bad = [r for r in rows
               if r["home"] in SKOTSKA or r["away"] in SKOTSKA]
        print(f"la_liga: {len(rows)} rader, {len(bad)} med skotska lag")
        for r in sorted(bad, key=lambda r: r["date"]):
            print(f"  {r['date']}  {r['home_raw']} - {r['away_raw']}  "
                  f"{r['hg']}-{r['ag']}  ({r['source']})")
        if not bad:
            print("inget att göra")
            return 0
        # Statistikrader ska följa med om någon hunnit skrivas.
        stats = store.conn.execute(
            "SELECT COUNT(*) FROM oddset_result_stats WHERE league='la_liga' "
            f"AND (home IN ({','.join('?' * len(SKOTSKA))}) "
            f"  OR away IN ({','.join('?' * len(SKOTSKA))}))",
            (*sorted(SKOTSKA), *sorted(SKOTSKA))).fetchone()[0]
        print(f"tillhörande statistikrader: {stats}")

        if not args.skarpt:
            print("\nTORRKÖRNING — kör om med --skarpt för att radera")
            return 0
        with store.conn:
            for table in ("oddset_result_stats", "oddset_results"):
                store.conn.execute(
                    f"DELETE FROM {table} WHERE league='la_liga' "
                    f"AND (home IN ({','.join('?' * len(SKOTSKA))}) "
                    f"  OR away IN ({','.join('?' * len(SKOTSKA))}))",
                    (*sorted(SKOTSKA), *sorted(SKOTSKA)))
        kvar = store.conn.execute(
            "SELECT COUNT(*) FROM oddset_results WHERE league='la_liga'"
        ).fetchone()[0]
        print(f"\nKLART — la_liga har nu {kvar} rader")
        return 0
    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())
