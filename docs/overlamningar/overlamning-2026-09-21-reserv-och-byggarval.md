# Överlämning — Ö/U-reserv och begripligt experimentval

## Beställning och viktiga avgränsningar

Saman bad att bygga reservoddsspåret och göra radbyggarens nya fördelning
begriplig. Bekräftat separat val: **visa experimentell reducering som ett
testval, behåll Standard som förvald**. Detta är inte en modellpromotion
och startar inget automatiskt forwardtest eller spel.

## Ö/U-reserv v1

- `app/pool_reserve.py`, `pool-reserve-ou-v1`, är en separat journal och
  presentationsväg. Första reservkälla är SvS/Kambi; Ninja är inte inkopplad.
- Poolens vanliga basvarv frågar bara matcher där Pinnacle-total saknas,
  matchen inte startat och SvS anger ett Kambi-id. Högst 3 anrop per delat
  varv, 8 s startbudget, 2 s per HTTP-fas och 15 min cooldown/provider-id.
  Ingen ny timer och inga leverantörsanrop i UI-/bygg-API:t.
- SvS deklarerar Kambi-id. Kräver exakt samma id i Kambis `events`, fotboll,
  `NOT_STARTED`, båda källors kända avspark inom 15 min och i framtiden.
  Providerns namn sparas för audit. Detta är id-proveniens, inte fuzzy.
- Bara Asian totalt / GOALS / FULL_TIME, öppet Över och Under på samma lina.
  MAIN_LINE prioriteras, annars paret närmast 2,0. HTTP Age dras av; priser
  äldre än 30 min eller efter matchstart visas inte som tillgängliga.
- Observation och hämtning sparas separat. Käll-/parsefel är `source_error`,
  inte frånvaro. Gamla cacheobjekt får inte skriva bakåt i observationstid.
  Färskt föregående pris kan visas med källfelsmarkering tills det blir gammalt.
- `MatchAnalysis.reserve_total` och oddsvarningens utfällda matchlista visar
  källa, lina, båda odds och observationstid. Kopierad granskning bär samma data.
- **Reservpriset används ännu INTE av byggaren.** Det fyller inte sharp-fält,
  påverkar inte Pinnacle-CLV, pit-total-v1 eller gamla frysningar och tar inte
  bort Pinnacle-varningen. Ett aktivt reservstyrt byggkontrakt är nästa steg.

Verifierat publikt Kambi-kontrakt med match 1026591201: komplett 200-svar,
matchidentitet och MAIN_LINE 2,25. Den tidigare svenska matchens id gav 404;
att en reserv finns innebär inte att den alltid har priset. Ingen vidare
Pinnacle-utredning av den svenska matchen enligt Samans tidigare besked.

## Experimentell reducering i Poolspel

- Välj **Värderader → Radprofil → Täckningstest v1 · experiment**.
  Högst 512 kr, en kupong. Alla 8-/13-matchers poolspel stöds. Fasta v1-vikter
  och seed; det manuella valet ändrar inte Standard, champion eller tester.
- `pool_portfolio.prepare` är nu gemensam för den befintliga read-only-
  screeningen och det manuella valet; samma kandidater, golv och väljare.
  Offline-maxbudget 20k finns kvar; UI-taket är en driftbegränsning.
- Ingen framtida facitinput. Kräver kompletta SvS-odds/streck och omsättning.
  Högst ett experimentbygge åt gången i backend (övriga får tydligt 409).
- Byggsvar och UI redovisar ändrade rader, fallback och **exakt beräknad
  toppträffchans** för Standard respektive experimentet på samma sannolikheter.
  Det är inte uppmätt ROI. Topptipset varnar särskilt att 7 rätt inte betalar.
- Om EV-/teckengolvet faller återges Standard-raderna, uttryckligen märkt.
  Den svaga toppträffchansen i tidigare 20k-prov har INTE lösts genom att
  tyst ändra v1. Toppchansskydd/fler parade mätningar återstår som ny kandidat.
- Vid omladdning återställs experimentvalet till Standard. Redan vald kupong
  och konkreta rader bevaras, med separat etikett. Bokföringskälla för en
  manuellt markerad spelad kupong är `byggare-pool-portfolio-screen-v1`.

## UI: så ser man vad byggaren gjort

**Så är kupongen byggd** ligger direkt under det skapade systemets rubrik,
före de långa simulerings-/utdelningsavsnitten. En kompakt matris visar
match och 1/X/2; reducerade rader visar procent OCH antal av de egna raderna,
inklusive 0. Matematiska system visar bara tecken. Motiveringen kan fällas
ut per match; färgreduceringens blå/gula markeringar bevaras.

Den tidigare ändringen gällde Historik → Tester → öppna en kupong. Den
fanns inte högt upp i det vanliga skapandeflödet, vilket förklarade Samans
svårighet att hitta den. Båda vyerna finns kvar.

Knappen visar pågående bygge och stoppar dubbelklick. Svar från en äldre
inställning eller omgång får inte visas som nytt system.

## Migration och verifiering

Reservjournalen aktiveras bara efter explicit backup/migrering:
`cd backend && .venv/bin/python -B scripts/migrera_pool_reserve.py`.
Utan tabellen är reservspåret inaktivt och ordinarie app fungerar.
Ingen historik bakfylls. Se `docs/db-atgarder.md` för produktionskörningen.

Riktade tester omfattar identitet/tid/status/linpar, backup utan bakfyllning,
källfel kontra frånvaro, färskhet, trafikbudget/cooldown, experimentets budget,
separat API-val, oförändrad analys och faktisk radfördelning. Full kontroll
passerade inför kodpush `471f511` och CSS-fix `d48f493`; 47 frontendtester,
lint och produktionsbygge gröna. Backend och frontend omstartade på servern,
inget startat på den gamla datorn. `/api/health`: status/pools/v22/oddset `ok`.

Serverns faktiska API-byggen, 256 kr och värdevikt 0,5:

- Topptipset 4347: 256 rader, 1,21 s, 163 rader utbytta. Beräknad toppchans
  Standard 7,82 % → experiment 5,28 %.
- Europatipset 2610: 256 rader, 3,79 s, 256 rader utbytta. Beräknad toppchans
  Standard 1,20 % → experiment 0,25 %.

Detta är funktionstest, **inte bevis för en förbättring**. V1 bör inte
promoveras. Ny kandidat behöver särskilt ett toppchans-/vinstplansanpassat mål;
nuvarande täckning av N−1/N−2/N−3 får inte förväxlas med bättre pengautfall.
Inga spel lämnades eller bokfördes vid kontrollen.

## Tillägg 2026-09-22 — byggarguide

Saman efterfrågade bakgrund och syfte för samtliga byggare. Under
bygginställningarna finns nu **Vilken byggare är vilken — och varför finns den?**
i `BuilderGuide.jsx`. Guiden skiljer systemtyp från radprofil, värdereglage,
A/B-kuponger och testserier. Varje profil beskriver ursprung, mekanism och
begränsning; den gör inga nya resultatanspråk. Underlag:
`docs/topptips-radform-v1-resultat.md`,
`docs/radprofiler-256-512-2026-08-25.md` och
`docs/pool-portfolio-screen-v1-2026-09-21.md`.

Mobilkontrollen upptäckte att steglänkarna Analys/Bygg/Kupong skrev över
hash-rutten och kunde öppna Idag. Klicket scrollar nu inom poolsidan utan
att ändra appens rutt. Ingen algoritm eller automatisk testkonfiguration
ändras av detta tillägg.

### Slutkontroll 2026-09-22

- `878d004` driftsatt, full kontroll grön. Mobil 390×844: byggarguiden går
  att fälla ut, ”2 Bygg” behåller `#/pool`, experimentet går att välja och
  bygger 256 rader. A/B-valet inaktiveras korrekt. Fördelningsmatrisen ryms
  utan intern sidscroll (`clientWidth=scrollWidth=327`). Inga spel bokförda.
- Ordinarie reservinsamling, inte manuell backfill, hade sparat 40
  `available` och 20 `no_market`-observationer kl 05:57 UTC. Det är upprepade
  observationer, inte 60 olika matcher: Topptipset 4347 match 3/4 hade reserv
  (2,5 respektive 3,25), match 5 saknade denna marknad.
- Kontrollen hittade att 30-minutersvarvet annars alltid kunde spendera
  reservbudgeten på omgångens tre första matcher. Kandidater sorteras nu
  efter äldsta providerkontroll, aldrig kontrollerade först. Regressionstest
  simulerar 31 min gamla kontroller och bevisar att match 4–6 kommer nästa gång.
- Reservspåret är fortfarande begränsat till tre anrop per gemensamt varv.
  Vid många luckor kan alla priser inte hållas färska samtidigt. Gemensam
  prioriterad kö över flera produkter/omgångar och eventuell ändrad trafikbudget
  återstår innan reservspåret kan utlovas heltäckande; ingen dold färskhetsförlängning.
