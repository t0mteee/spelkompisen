# Överlämning till Codex — 2026-07-16

Från Claude (Anthropic), som byggt projektet t.o.m. i dag. Saman är projektägare
och enda användare. Syftet här: du ska kunna fortsätta utan att fråga om
historiken. Sanningskällor i ordning: `docs/plan.md` (STATUS överst) →
`docs/granskning-2026-07-13.md` (evidens + acceptanskriterier) →
`docs/db-atgarder.md` (databas-åtgärder) → git-loggen (svenska, per arbetspaket).

## 1. Vad som är gjort (kronologiskt, allt verifierat och committat)

**2026-07-13 fm — A1 + ChatGPT-paket** (`617e8df`, `2430bd6`)
- `cli.py smart` = launchd-passet: fullt varv + snabbvarv var 4:e min när någon
  match startar inom 3 h (endast Pinnacle + böckernas 1X2, bara berörda ligor),
  poolspels-tätläget invävt i samma ~25-min-budget. OBS: backloggen sa "<36 h" —
  medvetet ändrat till 3 h (Pinnacle IP-blockrisk); justeras i `FAST_WITHIN_H`.
- `docs/chatgpt.md` + `backend/scripts/chatgpt_paket.sh` (granskarpaket av
  git-spårade filer — `.env` kan aldrig läcka).

**2026-07-13 em — Granskningsrunda 1 utförd** (`b11a7e8`, `ffc6d04`, `5cfe78f`)
Extern granskning (dina punkter) verifierades mot kod + databas; 8/10 områden
bekräftade, allt dokumenterat med fil:rad/DB-evidens i granskningsrapporten.
Åtgärdat samma dag efter Samans klartecken ("kör topp 5"):
- **WP3 identitetslager light**: `merged_results` med alias-tabell
  (`TEAM_ALIAS` + meta `oddset_alias:{liga}`), datumtolerans ±1 dygn mellan
  källor (MLS: Sofascore=UTC-datum, fd=lokalt → 304 dubbletter i fitten),
  målvakt (olika mål ⇒ ingen merge), fd-raden som bas, audit-lista i
  `cli.py modeldata`. Resultat: MLS-fitten 1648→1270 rader, LA Galaxy en
  identitet, xG 57→73 %. Bonus-fynd: Sofascores `current` inkluderar straffar
  i slutspel → `normaltime`-fix + sanering av 11 rader (se db-atgarder.md).
- **Grönt-kriterium v2**: ≥50 stängda OCH undre 90 %-KI > 0 (kluster-bootstrap
  per match, close-EV winsoriserad ±20 %), nedbrutet per tier×liga×marknad×
  version i `clv_report().groups`; KI i UI:ts 📒-rad.
- plan.md omskriven till WP-backlogg; Europa-ligorna pausade; decay-kommentaren
  rättad (240 d är e-folding, halveringstid ≈ 166 d — beteendet oförändrat).

**2026-07-16 — Runda 2 åtgärdad** (dagens commits)
Dina åtta punkter besvarades (svaren återgivna i korthet under §3); därefter
Samans klartecken och implementation:
- **WP0**: WAL + busy_timeout 10 s + synchronous=NORMAL + `Storage.bulk()`
  (batch-transaktioner; fd-refreshen var ~1 700 commits). OBS: `mode=ro`-URI:er
  mot WAL-databasen kan ge "unable to open" — öppna normalt och kör SELECT.
- **WP2-mini (notisvakten)**: `collect()` bygger ett presence-set av
  (match_id, källa, marknad) ur varvets LYCKADE svar; `log_and_notify(...,
  present=...)` skapar larm (inkl. 🔔-historik) ENDAST när både bokpriset och
  Pinnacle-priset för marknaden är närvarobekräftade. Misslyckad källa/saknad
  marknad ⇒ gated (räknas i `value.gated`, syns i snapshot-loggen). Medveten
  begränsning: i snabbvarven pollas bara 1X2 ⇒ AH/ÖU-larm väntar på nästa
  fulla varv (≤30 min). CLV-loggningen är INTE gated (fulla WP2 tar färskhet
  i värde/facit).
- **Version-split (din punkt 5)**: `model_version` = semantiskt fingeravtryck
  per tier (`s-c32b7065` ur SHARP_PARAMS+DATA_VERSION; `m-8bf25277` ur
  MODEL_PARAMS+T-kalibrering+DATA_VERSION); ny kolumn `git_hash` för exakt
  reproducerbarhet. Migration körd via `scripts/migrera_signalversion.py`
  (idempotent; 43 rader mappade — parametrarna oförändrade sedan stämpling,
  därför infogade i nuvarande version; 66 äldre rader = legacy `-`).
- **Dokumentation**: db-atgarder.md (11-raders saneringstabell + reproducerbar
  SQL + processregeln), plan.md (runda 2-korrigeringarna: NTFY efter vakten,
  grönt v3-trappan, fuzzy-audit som WP3-tillägg, testlistan), CLAUDE.md
  (inaktuell launchd-rad fixad, nya metodregler), AGENTS.md omgjord till
  pekar-fil (din kopia var 3 dagar gammal och hade två introducerade fel:
  `.Codex/launch.json` finns inte, och den påstod att ingen launchd-insamling
  var laddad).
- **Backuper säkrade**: `backend/data/backups/stryktips-2026-07-13-fore-sanering.db`
  + `...2026-07-16-fore-versionsmigration.db` (gitignorade).

## 2. Driftläge just nu

- launchd `com.saman.spelkompisen.snapshot` kör `cli.py smart` var 30:e min;
  backend 8002 + frontend 5175 uppe. Kambi-varningar för ligor utan listade
  events (friendlies/OBOS ibland) är normala.
- Facit: sharp 35 flaggor (9 stängda, snitt +≈11 % men n långt under krav),
  modell 74 (7 stängda, negativ tendens) — inget är grönt, inget SKA vara grönt.
- **NTFY_TOPIC är inte satt** — notisvakten är på plats så det är nu Samans
  nästa steg (eget topic i `backend/.env`, prenumerera i ntfy-appen).

## 3. Dina runda 2-punkter — status

| # | Punkt | Status |
|---|---|---|
| 1 | NTFY före närvaroskydd | ✅ Åtgärdad — notisvakten byggd; ordningen ändrad som du föreslog |
| 2 | ✓ på tier-aggregat | ⚠️ Delvis — beslutsregeln dokumenterad (grönt per grupp; v3-trappan i WP5); UI:ts grupptabell + borttagning av tier-✓ ÅTERSTÅR (ingen grupp kan bli grön på länge, så ingen akut risk) |
| 3 | Flaggor ≠ matcher | 📋 Specad i plan.md (n_matches ≥ 30, span ≥ 28 d, instabil-märkning < 10) — implementeras med v3 i WP5 |
| 4 | Multiple testing | 📋 Specad (förregistrerade primära grupper, candidate→green out-of-time, BH-FDR 10 % för utforskande); nuvarande facit omdöpt "interimistiskt flaggfacit" |
| 5 | Git-hash för grov | ✅ Åtgärdad — signal_version + git_hash, migrerad |
| 6 | Tysta fuzzy-beslut | 📋 Specad som WP3-tillägg (fuzzy_links-audit); scope-markering inskriven |
| 7 | Reproducerbar sanering | ✅ Åtgärdad — db-atgarder.md + backuper + processregel; avvikelsen 13/7 dokumenterad ärligt |
| 8 | Tester | 📋 Tio fall designade (nedan); pytest-beslutet (nr 10) väntar på Saman |
| 9 | Ändringsprocessen | Förklarad: frysen bröts aldrig — commitarna 13/7 kom EFTER Samans uttryckliga "kör topp 5"; dagens arbete efter "kör på". Din försiktighet var rimlig utifrån vad du kunde se |

**Designade tester (skrivs före respektive fix):** LA Galaxy-alias ⇒ en
identitet · ±1 dygns-merge med fd som bas · målvakt (olika mål ⇒ ej merge +
audit) · fuzzy-länk ⇒ audit som unverified · normaltime 2-2/current 6-7 ⇒ 2-2 ·
statistikfel ⇒ ej seen-markerad (skrivs med WP8) · bootstrap: <3 block ⇒ KI
None, ≥3 deterministiskt · tier-aggregat får aldrig göra grupp grön · docs-
commit ⇒ signal_version oförändrad · settlement-roundtrip hel/halv/kvarts (WP1).

## 4. Planen härifrån (prioritetsordning)

1. **Saman: sätt NTFY_TOPIC** (enda användarsteget).
2. **WP1 settlement-ankring** (S/M) — projektets viktigaste kvarvarande
   matematikfel (72 % av ankrade ÖU-linjer). Test först (roundtrip via
   `pair_fair`); ordningen temper→ankare; bumpa `anchor` i MODEL_PARAMS
   (ger ny m-version automatiskt); omkör `oddsetcalibrate`.
3. **WP2 full** (M) — persistent närvaro: last_seen_at (uppdateras vid
   dedup-skip), available/suspended, source health i statusraden, åldersvakt
   även i värde/facit, deep-markets i snabbvarvet för 3h-fönstrets matcher.
4. **WP4 CLV-linje** (S/M) — line i PK (recreate, facit bevaras), stängning på
   flaggans lina, "line moved" som kategori i stället för censur.
5. **WP5 ledger + grönt v3** (M/L) — fasta horisonter T−24h/−3h/−20m, ALLA
   prediktioner, candidate/green-trappan, BH-FDR, UI-grupptabell (stänger
   runda 2-punkterna 2–4 helt).
6. Därefter: WP6 pool-EV (jackpot in i builderns radval är en S — frontend
   visar redan jackpot-EV på rader valda utan den; κ̂-korrektion; MC-portfolio
   som M), WP8 insamlingsintegritet (seen-retry, frånvaro-snapshots MED
   spelar-ID, Elo-historik), WP9 källor (ASA har certfel härifrån — verifiera
   åtkomst innan planering; Sofascore coverage-matrix: shot-xG finns för
   Eliteserien 30/30, saknas för Allsvenskan 0/31), mobilpolish (C9–C11).
7. **Europa-ligorna förblir pausade** tills WP0–WP5 är klara (Samans beslut).

**Öppna beslut hos Saman** (nr ur granskningsrapporten): 5 pool-EV-ambitionen ·
8 manuell spel-journal · 9 ASA-felsökning · 10 pytest som dev-beroende.

## 5. Fallgropar (dyrt vunna — läs innan du kodar)

- Sharp-ankrat är enda gröna; modell = amber, ALDRIG in i CLV. Live-odds
  sparas/värderas aldrig. Inga automatiska spel. Enbart gratiskällor.
- `evalRows` (frontend) och `build_ev_system` (backend) ska hållas konsistenta.
- Pinnacle Cloudflare-blockar på IP-nivå i perioder — öka aldrig pollvolymen
  utan att tänka på det (därav 3h-fönstret i snabbpollen).
- Sofascore: verifiera SPORTEN på nya id:n (ut 1420 var handboll); curl_cffi
  med `impersonate='chrome'` krävs; `normaltime`, inte `current`.
- SQLite är i WAL nu: `mode=ro`-öppning kan faila — öppna normalt för läsning.
- Backend auto-reloadar inte; restart-kommandot står i AGENTS.md — aldrig
  `pkill -f uvicorn`, aldrig `lsof -ti:<port>` utan `-sTCP:LISTEN`.
- Stoppa aldrig frontend 5173/5175 utan omstart — Saman kör mot dem från mobilen.
