# Reducering: isolerad screening v1

Samans godkännande 2026-09-21: undersök oddsluckorna och pröva en byggare
som värderar hela kupongens täckning. Standard och befintliga frysta tester
ändras inte. Detta är ett körbart OFFLINE-test, inte ett nytt aktivt forwardspår.

## Fryst specifikation före första resultatkörning

- Version `pool-portfolio-screen-v1`, seed 20260921.
- Samma budget, frystidsinput, vinstplan, jackpot och befintligt X-riskgolv
  i båda armarna. SvS-sannolikheter som nuvarande standard.
- Referens: oförändrade `_rank_ev_rows` och `_select_draw_risk_rows`.
- Kandidat: referensens kandidater + 1024 sannolikhetsdragna fullständiga
  utfall och alla deras enstegsgrannar. Inget faktiskt resultat används.
- Girigt radval på nytillkommande täckning av 8192 simulerade utfall.
  Vikter för minst N/N−1/N−2/N−3 rätt: 0,4/0,3/0,2/0,1.
  Linjär term 0,25 × rad-EV / referensens summerade rad-EV.
- Budgeten fylls med exakt lika många unika rader. Understigs 90 % av
  referensens rad-EV eller något befintligt teckengolv blir hela armen
  referensen igen, uttryckligen redovisat som fallback. Inte en ROI-garanti.
- Separat utvärderingssample: 16384 utfall, seed+1; kandidater seed+2.
  Optimeringssamplet redovisas aldrig som uppmätt förbättring.
- Databasen öppnas read-only, inga produktionsrader/parametrar skrivs.
  Kräver kompletta SvS-priser/streck i snapshot före tidsriktig frysning.
  Snapshot är inte bevis på färsk presence: detta är diagnostisk replay,
  INTE pit-v4-resultat. `same_rows_as_saved` visar reproduktionsskillnader.
- Pengafacit visas bara om samtliga vinstnivåer har identifierbar pott;
  samma bortfallskriterium för båda armarna, egen utspädning via befintligt facit.

## Hur resultatet får användas

Septembers omgångar är redan sedda. De används till mekanisk kontroll och
diagnostik, aldrig som bevis för lönsamhet. Slumpen och vikterna ändras inte
för att vinna en gammal omgång. Topptipset betalar enbart för N=8; bättre
7-rättstäckning får inte kallas bättre ekonomiskt resultat.

Grindarna lästes före arbetet: poolopt har 42 parade omgångar, men tidigare
avläsning gav inga säkra förbättringar. V2.2 och radar återstår på tid/volym.
Ingen promotion. Innan automatisk frysning av denna kandidat: mät körtid,
oberoende sample-variation och fallbackfrekvens på ALLA tillgängliga tidsriktiga
omgångar med samma budget, därefter ett separat förregistrerat forwardtest
med egen config_key, starttid och parade utfall. UI/Testkatalog påverkas inte än.

## Körning på servern

Från `backend/` (utdata till terminal eller en rapportfil utanför DB):

```sh
.venv/bin/python -B scripts/prova_pool_portfolio.py --product stryktipset --draw 4971 --config reducedmax-v2-dr1-b20000-ev50 --budget 512
```

Utelämna `--budget` för referensens faktiska insats. Börja med 512 för ett
snabbt funktionstest. `--budget 20000` provar maxreduceringen; inga pengar spelas.
