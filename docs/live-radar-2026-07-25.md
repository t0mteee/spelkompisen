# Live-radar v2 — observerat chansgap och signaljournal i shadow mode

Datum: 2026-07-25.

## Produktbeslut

Samans beställning är en observationsradar: hitta pågående matcher där
chanserna är större än målutdelningen medan det fortfarande finns tid kvar.
Den ska hjälpa användaren att välja vad som är värt att granska live. Den
lägger aldrig spel automatiskt.

Claudes offlineprov på 220 matcher visade att en enkel skottvikt inte
förutsade mål i nästa 15-minutersfönster. Det stoppar en grön spelsignal, men
inte en tydligt märkt informationsradar. Därför byggs radarn i shadow mode och
dess egna observationer samlas innan notiser eller modellstöd övervägs.

## Levererat

- `app/live_radar.py` läser Sofascores publika livefeed och kumulativa
  matchstats för projektets ligor.
- Observerade fält: xG, stora chanser, skott, skott på mål, skott i box,
  boxberöringar och hörnor. Coverage varierar per liga.
- Träningsmatchernas globala Sofascore-turnering filtreras mot matcher som
  redan finns i Spelkompisens Oddset-vy; radarn fylls inte med godtyckliga
  träningsmatcher från hela världen.
- `oddset_live_capture` och FotMobs separata capturetabell sparar råa
  snapshots. De används både som kontrollgrupp och för att återskapa vad som
  hände efter signalögonblicket; providrarnas chansmått blandas aldrig.
- `app/live_signal_ledger.py` sparar från 2026-07-31 den **första** synliga
  förekomsten per match × signaltyp × nivå. En signal som ligger kvar genom
  tio radarvarv blir alltså ett beslut, inte tio påhittade spel. Om Följer
  senare blir Stark sparas det som ett nytt, separat beslutstillfälle.
- Signaljournalen sparar källversion, minut, ställning, lag, alla relevanta
  xG-/skottmått, regelns förklaring samt observerad live-Ö/U-huvudlina och
  Över-/Under-odds från SvS/Kambi. Oddsets observationstid sparas separat
  från statistikkällans capturetid och korrigeras för Kambis eventuella
  CDN-`Age`.
- Stängd eller suspenderad Kambi-marknad räknas inte som spelbar — sedan
  2026-08-01 spärras även betOffer-nivåns `suspended`-flagga (Kambi kan
  suspendera hela erbjudandet medan utfallen står kvar som `OPEN`;
  verifierat i drift 2026-07-31) och en sedd-men-stängd marknad bokförs som
  eget statusvärde `suspended`, skilt från `not_offered`. Saknat match-id,
  saknad marknad och källfel får egna statusvärden och bakfylls aldrig.
  Livepriser skrivs aldrig till prematchtabellen `oddset_odds`.
- Efter matchen sparas normaltidsresultat, antal mål efter signalen, mål inom
  nästa 15 matchminuter, ytterligare mål före full tid och faktiskt
  enhetsresultat för Över-linan (inklusive push/halv vinst/halv förlust på
  kvartslinjer). Resultatet är append-only och skriver aldrig om signalen.
  Sedan 2026-08-01 bevisar det officiella slutresultatet BÅDA utfallen för
  "fler mål före FT" (== ⇒ 0, > ⇒ 1) — tidigare kunde bara nollan bevisas
  utan täckande capture, vilket censurerade enbart sanna ettor och biasade
  `more_before_ft_rate` nedåt. 15-minutersfönstret censureras fortsatt
  ärligt när målens tidpunkt inte kan avgöras.
- Journalnyckeln är LÅST sedan 2026-08-01 (`_locked_key`): samma fysiska
  match får aldrig två `match_key` även om kanonisk oddslänkning dyker upp
  mitt i matchen eller kortet byter bärande källa (fotmob↔sofascore).
  Uppslag via providrarnas event-id och i sista hand lagjämförelse med fyra
  spärrar (adversariellt verifierade samma dag): rader från en provider vars
  id kortet självt bär utesluts (samma provider utan id-träff = bevisat annan
  match — stoppar prefix-falskmergar som Inter↔Inter U23), spegling
  accepteras som i `_canonical_match`, starttider >3 h isär (dubbelmöten)
  låser aldrig, och tvetydighet låser aldrig. Utan låset kunde blindkohorten
  ("första aktiva signalen per match") tyst räkna samma match två gånger.
- `clock_source`/`clock_observed_at` (2026-08-01): journalens minut/ställning
  är EXAKT signalens beräkningsbas — samma per-fält-regel som
  `_fotmob_signal` (FotMobs egna värden behålls, bara saknade fält lånas
  från Sofascore-kortet; ett helparslån gav rader som motsade signal_score
  och settlementets providerserie). Lånet bokförs med källa
  ('fotmob+sofascore' = blandat) och de lånade fältens egen observationstid.
- `/api/oddset/live-radar` räknar signalen vid läsning och är märkt
  `mode=shadow`.
- Oddset-vyn har en mobilanpassad Live-radar med minut, ställning, xG/proxy,
  chansmått och förklaring.
- Samma fasta femminutersjobb som poolinsamlingen kör `live-tick`. Det är
  förskjutet två minuter från Oddset-jobbet.

## Signalpolicy v2

`chance-gap-shadow-v2` använder i första hand:

- lagets `xG − mål`;
- matchens `total xG − totala mål`;
- ny xG sedan observationen cirka 15 minuter tidigare;
- minst tolv minuter kvar av ordinarie tid.

Om xG saknas används en strikt proxy av stora chanser, skott på mål, skott i
box och boxberöringar. Proxyflaggan visar uttryckligen varningen att historiken
ännu inte har visat någon prediktiv mållyft. Den får aldrig blandas ihop med
Oddsets gröna värdesignaler.

Inget i v2 påverkar:

- värdesignaler eller Kelly;
- Oddset- eller poolmodellen;
- CLV-/prediction-facit;
- pushnotiser;
- systemförslag.

## Nivåerna som visas

- **Info**: ännu ingen aktiv signal. Råögonblicket finns i den gamla
  momentserien men räknas inte som ett möjligt spel i signaljournalen.
- **Följer · xG**: minut 15–78, minst tolv minuter kvar och antingen lagets
  `xG − mål ≥ 0,65` eller matchens `total xG − mål ≥ 1,00`.
- **Stark · xG**: samma tidsfönster och antingen lagets
  `xG − mål ≥ 1,15` eller matchens `total xG − mål ≥ 1,65`.
- **Följer · skott**: minut 20–78, minst tolv minuter kvar och antingen
  `stora chanser − mål ≥ 1,5` eller `skott på mål − mål ≥ 5` samtidigt som
  laget har minst åtta skott i box.
- Skottspåret har ingen Stark-nivå i `chance-gap-shadow-v2`. Det ska inte
  skapas en sådan nivå genom efterhandsgranskning av resultaten.

Reglerna skrivs ut direkt på Labb-sidans **Radar-facit och signaljournal** så
att trösklarna kan granskas samtidigt som utfallet, utan att behöva läsa kod.

## Databasåtgärd

Migration: `backend/scripts/migrera_live_radar.py`.

Backup:
`backend/data/backups/stryktips-2026-07-25-fore-live-radar.db`.

Första migreringen skapade 26 kolumner, 0 rader och gav
`PRAGMA integrity_check = ok`. Fem första globala träningsmatchsprober ligger
kvar som auditerbar `sofa-live-v1`, men är efter scope-rättningen exkluderade
från API och utvärdering. Aktuell captureversion är `sofa-live-v2`.

Signaljournalens additiva migration:
`backend/scripts/migrera_live_signal_ledger.py`. Backup:
`backend/data/backups/stryktips-2026-07-31-fore-live-signal-ledger.db`.
Tabellerna `oddset_live_signal` och `oddset_live_signal_result` var tomma när
migrationen verifierades; inga historiska liveodds har bakfyllts.

## Två frågor, två facit

1. **Ger signalregeln mer mål än jämförbara ögonblick?** Den äldre
   momentsettlingen jämför varje capture mot liga × minutband × aktuell
   målskillnad. Den får svara på prediktiv lyft och coverage.
2. **Hade det gått att rygga signalen blint?** Signaljournalens förregistrerade
   blindkohort använder bara den första aktiva signalen per match, kräver ett
   faktiskt observerat livepris och räknar enhets-ROI på Över-linan. Beslut
   tas först vid minst **200 oddssatta och avgjorda signalmatcher**, minst
   **60 dagars** spann och undre 90-procentig bootstrapgräns över noll.

Följer→Stark-raderna och nivågrupperna visas också, men de får inte ersätta
den frysta blindkohorten efter att resultaten blivit kända. Fram till gaten
passerar är status alltid `shadow`/samlar och sidan ger ingen uppmaning att
rygga.

## Nästa konkreta actions

1. Låt launchd-varvet samla utan manuell intervention och kontrollera
   veckovis coverage för Kambi-livepris samt varför priser saknades.
2. Vid mognad: redovisa först den frysta blindkohorten, därefter Följer/Stark,
   xG/skott, liga och minutband som diagnostik — aldrig välj bästa delgrupp
   som nytt huvudresultat i efterhand.
3. Om skottspåret återigen är neutralt: visa bara xG-ligor som
   “granska”-signal och behåll proxydata som coverage.

## Acceptanskriterier före notiser

- minst 40 avslutade signalmatcher och minst 28 kalenderdagar;
- ingen dataläcka från händelser efter capture;
- resultat settlas från samma Sofascore-event-id;
- separat facit för xG och proxy;
- positiv undre 90-procentig KI-gräns mot konditionerad basrate;
- nytt uttryckligt beslut från Saman innan push aktiveras.

Notisgaten ovan är separat från blind-ROI-gaten och kan inte i sig göra
signalen spelbar. Inga notiser aktiverades i arbetet 2026-07-31.
