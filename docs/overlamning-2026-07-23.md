# Överlämning/changelog för Codex — 2026-07-23

**Historik:** aktuell arbetsöverlämning finns i
`docs/overlamning-till-claude-2026-07-24.md`.

Ersätter `docs/overlamning-2026-07-16.md` som aktuell ingång (den gamla ligger
kvar som historik — dess "Fallgropar"-avsnitt gäller fortfarande ordagrant).
Sanningskällor i ordning: `docs/plan.md` (STATUS överst) → `docs/db-atgarder.md`
→ git-loggen (svenska, per arbetspaket).

## Changelog sedan 2026-07-16-överlämningen

**Codex egna 19 commits (16–17/7)** — hela P0/P1-backloggen: WP1 settlement-
ankring, WP2 full prisnärvaro/källhälsa, WP4 CLV per lina, WP5 prediction
ledger + grönt v3, WP6 jackpot/κ/portfolio-MC, WP7, WP8 frånvaro-/Elo-historik,
WP3-fuzzy-audit (hittade äkta felkoppling Egersund→Haugesund, gräns 0,75),
backtest v4, UI v3 + PWA, WP9c team-events, modell v2 förregistrerad och
**STOPPAD på egna kriterier** (ingen live-påverkan). Claude spot-verifierade
17/7: 107/107 tester, ankringsmatematiken korrekt, DB-integritet ok, v2
isolerad — inga metodfel funna. Granskningsnoter i konversation/plan.md.

**Alt-linjelagret (Claude, 20/7, `b917125`)** — Samans "steppa upp"-beställning:
samma-linje-regeln dödade 67 % av AH- och ~40 % av Ö/U-jämförelserna (AH samma
huvudlinje bara 33 %). Ny tabell `oddset_sharp_alt` sparar sharpens ALLA linjer
(samma två API-anrop, noll ny trafik); värdemotorn devigar alt-paret på BOKENS
exakta lina (fresh ≤45 min, `alt_line: true` i posten); `closing_snapshot`
läser alt-lagret när huvudlinan flyttat. Ny sharp-version `s-776ca0e0`
(`alt_lines` i SHARP_PARAMS). Första varvet: 1 238 alt-rader/38 matcher;
Ö/U-jämförelser 66 (28 via alt), AH 38 (12), hörnor 6 (2). 5 nya tester
(112/112). Detaljer: `docs/db-atgarder.md` 2026-07-20.

**Facit-läge 20/7:** sharp 1X2 close-EV **+3,8 %** på 50 stängda (Allsvenskan
+3,7 %/16 matcher, MLS +6,8 %/12) — riktning rätt, långt till candidate
(30 matcher/liga). Modell-tiern fortsatt negativ (amber gör sitt jobb).

**Drift/miljö:**
- **svs PAUSAD 20/7** (fryst arkiv, total paritet verifierad): launchd urlastat,
  plist-kopian borta ur ~/Library/LaunchAgents (original i svs/backend/scripts/),
  servrar 8000/5173 stoppade, DB kvar. Borttagen ur menybars-appen 23/7.
- **VM-koll på is** (Samans beslut, se ~/vm/LÄRDOMAR.md): borttagen ur menybars-
  appen 23/7; vm-launchd-insamlingarna redan urlastade. Menybars-appen
  (`~/vm/tools/menubar.py`) hanterar nu ENBART Spelkompisen (8002/5175) och är
  vägen att starta servrarna efter omstart ("Starta allt").
- Spelkompisen är därmed **enda driften** — och enda Pinnacle-konsumenten på IP:t.

## Att göra (utöver NTFY_TOPIC, som förblir Samans steg)

1. ✅ **UI-grupptabell + candidate-ETA klara 23/7:** aktuella primärgrupper
   visas som egna statuskort med 50/30/28-progress. Tier-summan är ren översikt
   utan ✓; äldre versioner finns kvar nedtonade i detaljtabellen. ETA:n
   prognostiserar bara mängd/tid vid nuvarande takt — KI-gaten måste fortfarande
   klaras. Desktop och 390 px verifierade utan sidscroll/konsolfel.
2. ✅ **Alt-linje-flödet spot-checkat 23/7:** `s-776ca0e0` hade 98 flaggor,
   52 jämförbara stängningar och 8 exakt-line-stängningar trots flyttad
   huvudlina (5 Ö/U, 2 hörnor, 1 AH). 67 862 historikrader/210 matcher,
   DB 47 MB och `integrity_check=ok`.
3. **Hörn-grön väg (gamla B8)**: nu UPPLÅST av alt-linjerna — vänta tills
   hörn-facitet samlat n, sedan egen facit-grupp (utforskande, BH-FDR).
4. ✅ **Gamla V2 vilande; V2.2-flerligeförsök armerat 23/7:** V2.1 förblir
   stoppad. Allsvenskan-only hann få 0 rader och ersattes före första
   observationen av Allsvenskan + research-only PL/Serie A/La Liga/Bundesliga.
   Andradivisionerna är fit-only för uppflyttare. 6 292 resultat, 78 lag/arenor
   och 3 441 lag-event är inlästa; 38/39 premiärmatcher kompletta.
   `p_v22 == p_sharp` fram till träningsgaten, aldrig tips/notis/CLV.
   Status: `cli.py v22audit`; rapport:
   `v2.2-multileague-start-2026-07-23.md`.
5. ✅ **Värde-pill-flimmer mätt 23/7:** 120/236 fullvarvsintervall under sju
   dygn var längre än 45 minuter (median 51, max 63); riskytan var 147 minuter
   per dygn för djuppriser utanför snabbfönstret. Färskhetskravet lämnas
   oförändrat. Vid faktiskt UX-problem är rätt lösning en separat, nedtonad och
   icke-spelbar ”senast sedd signal”, inte att gamla priser görs spelbara.
   Rapport: `docs/flimmer-audit-2026-07-23.md`.
6. **Låt dagens signalfacit mogna**: inga tröskeländringar medan ledgern dömer
   (tidigast ~2–3 veckor för första candidate). V2.2 får under tiden endast
   samla enligt sitt frysta kontrakt; ingen fit före 300 avgjorda kompletta
   matcher per horisont, minst 50 per liga och minst 42 dagars span.
7. **Öppna produktbeslut hos Saman**: 🎯 Bara signaler som mobil-default;
   spel-journal i appen; om/när researchligorna ska bli synliga produktligor;
   ASA-certfelet; servermigrering (E14). **pytest-beslutet kan stängas** —
   unittest-sviten (132 fall) täcker behovet utan ny dependency.

## Regler som aldrig viker (påminnelse)

Sharp-ankrat = enda gröna; modell = amber, aldrig i CLV. Grönt per signalgrupp,
aldrig per tier. Notiser kräver närvarobekräftat pris. DB-ändringar = skript +
backup + rapport. Versionspolicy: signal_version grupperar facit, git_hash
reproducerar. Inga automatiska spel, enbart gratiskällor, rör aldrig ~/svs
eller ~/vm (svs är dessutom fryst arkiv).
