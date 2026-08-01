# Live-radar v4 — observerat chansgap och signaljournal i shadow mode

Datum: 2026-07-25.

## Uppdatering 2026-08-01 — tre-källorskontrakt och ren v4-kohort

Flashscore täppte verkliga täckningsluckor: Chelsea–Tottenham hade full xG,
xGOT, skott och stora chanser där FotMob/Sofascore saknade signalbara fält,
och Östersund–Öster i Superettan blev synlig med skottdata. Den erfarenheten
motiverade en tredje liveprovider, men **ingen provider är ovillkorligt
primär**. Aktiv regel väljer i denna ordning:

1. komplett xG-par;
2. komplett kärnproxy eller komplett signalgren;
3. partiell proxy;
4. inga chansmått.

Först vid samma strukturella täckning används fast prioritet
Flashscore → FotMob → Sofascore. Urvalet tittar aldrig på gapets storlek eller
vilken källa som råkar ge starkast signal. Hela xG-/skott-/chansberäkningen och
15-minutersdeltat kommer ur den valda providerns egen serie.

| Provider | Råfält som kan lagras | Saknas i providerschemat |
|---|---|---|
| Flashscore | xG, xGOT, stora chanser, totalskott, skott på mål, skott i box, hörnor | boxberöringar, open-play-xG |
| FotMob | xG, xGOT, open-play-xG, stora chanser, totalskott, skott på mål, skott i box | boxberöringar, hörnor |
| Sofascore | xG, stora chanser, totalskott, skott på mål, skott i box, boxberöringar, hörnor | xGOT, open-play-xG |

Tabellen beskriver schemat, inte ett löfte per match. v4 rankar de fält som
faktiskt finns i den aktuella capturen.

**v3 är inte en giltig beslutsserie.** Captures från
2026-08-01T08:00:00Z till men inte med 21:00:00Z stämplas fortsatt
`chance-gap-shadow-v3` för audit, men perioden var en pilot före de samlade
färskhets-, identitets-, presence- och koherensvakterna. Den får aldrig
användas som stöd. Den rena kohorten är `chance-gap-shadow-v4` från exakt
**2026-08-01T21:00:00Z**. v2 (<08:00Z), v3 och v4 redovisas och settlas var
för sig; gränserna är frysta.

### Färskhet, koherens och presence

- Alla länkade och fristående serier måste vara högst **12 minuter** gamla.
- Flashscore samlar som `flashscore-live-v2`. Listställning och detaljstats
  får skilja högst 20 sekunder; annars omhämtas feed/ID-index och capturen
  hoppas över om koherens fortfarande inte kan bevisas.
- FotMob samlar som `fotmob-live-v2`. Ställningen läses i första hand ur
  samma eventdetalj som statistiken. Om listställningen måste användas får
  den vara högst 15 sekunder från detaljobservationen; annars omhämtas hela
  live-listan och ID-indexet. Okänd/inkoherent ställning sparas aldrig som
  0–0 och ger ingen capture.
- Sofascore-listan måste vara ett välformat objekt med en faktisk
  `events`-lista. Ett lyckat tomt roster är ett riktigt presence-besked och
  avslutar tidigare kort; ett transport-/parsefel skriver röd source-health
  men ändrar aldrig presence.
- FotMob kräver på samma sätt en faktisk `leagues`-lista (`{}` och
  `leagues:null` är fel), och Flashscore kräver det globala `SA÷`-huvudet
  (`ZA÷` ensamt kan vara en avhuggen feed). Bara explicit tomma, validerade
  roster får avsluta tidigare kort.
- Alla tre providers har egen presence och egen source-health. API:ts
  `source_runs` visar deras egna senaste kontroller. Gemensam `last_run` är
  den **äldsta** av de tre och är tom tills alla tre faktiskt kontrollerats;
  UI visar då “inväntar alla tre livekällor”.
- Source-health är grön bara för ett komplett rent varv. Ett partiellt
  detaljfel eller en match som hoppas över blir amber i UI; fullt fel,
  saknad kontroll eller för gammal kontroll blir rött.

### Identitet och exakt visningsproveniens

En providerlänk kräver samma liga, samma två lag i samma hemma/bortaordning,
en läsbar avspark inom 30 minuter och exakt **en** kandidat. Svensk genitiv
och observerade livealias stöds, men enords-prefix som Inter↔Inter Miami/U23,
ungdomslag, dubbelmöten och tvetydighet faller stängt. En färsk olänkad
FotMob-/Flashscore-serie får i stället eget namespacat kort; stats får aldrig
försvinna bara för att Sofascore saknar matchen.

`signal.stats_source` och källchipet visar vem som bär alla chansmått. Bara
saknad minut eller ställning får lånas fältvis från en redan verifierad
Sofascore-länk. `signal.basis` innehåller exakt
`minute`/`minute_source`, `home_score`/`home_score_source` och
`away_score`/`away_score_source`. Desktop visar källorna i tooltips; mobilkort
skriver ut exempelvis “Flashscore · minut Sofascore”. **Signaljournalens**
facit använder samma effektiva minut/ställning. Det separata momentfacitet är
medvetet diagnostiskt och räknas på råproviderns egen klocka/ställning; de två
estimanden får inte beskrivas som samma sak.

Provider-id behandlas som ogenomskinlig sträng i presence, journal och
momentsettlement. `oddset_live_moment_settlement.event_id` migreras därför
till TEXT med `backend/scripts/migrera_radar_event_id_text.py`; skriptet tar
backup, bevarar append-only-rader och kontrollerar PK, FK och integritet.

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

- `app/live_radar.py`, `app/flashscore.py` och `app/fotmob.py` läser tre
  separata publika livefeeds och kumulativa matchstats för projektets ligor.
- Observerade fält: xG, stora chanser, skott, skott på mål, skott i box,
  boxberöringar och hörnor. Coverage varierar per liga.
- Träningsmatchernas globala Sofascore-turnering filtreras mot matcher som
  redan finns i Spelkompisens Oddset-vy; radarn fylls inte med godtyckliga
  träningsmatcher från hela världen.
- `oddset_live_capture`, `oddset_live_fotmob` och
  `oddset_live_flashscore` sparar var sina råa snapshots. De används både som
  kontrollgrupp och för att återskapa vad som hände efter signalögonblicket;
  providrarnas chansmått blandas aldrig och capture-version ingår i
  settlementseriens identitet.
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
- `clock_source`/`clock_observed_at` och v4:s `signal.basis` (2026-08-01):
  journalens minut/ställning är EXAKT signalens beräkningsbas. Providerns egna
  värden behålls och bara saknade fält lånas från en verifierad
  Sofascore-länk. Lånet bokförs per fält i API/UI och som kombinerad
  `clock_source` i journalen; settlement återanvänder samma värden.
- `/api/oddset/live-radar` räknar signalen vid läsning och är märkt
  `mode=shadow`.
- Oddset-vyn har en mobilanpassad Live-radar med minut, ställning, xG/proxy,
  chansmått och förklaring.
- Samma fasta femminutersjobb som poolinsamlingen kör `live-tick`. Det är
  förskjutet två minuter från Oddset-jobbet.

## Signaltrösklar (oförändrade i v4)

`chance-gap-shadow-v4` använder samma förregistrerade trösklar som v2/v3;
versionsbytet gäller datagenereringen, inte en efterhandsoptimerad gräns.
Regeln använder i första hand:

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
- Skottspåret har ingen Stark-nivå i `chance-gap-shadow-v4`. Det ska inte
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

Ny v4-migration:
`backend/scripts/migrera_radar_event_id_text.py`. Den gör
`oddset_live_moment_settlement.event_id` till TEXT, bevarar naturlig PK
`provider/event_id/captured_at/capture_version` och är atomär/idempotent.
Produktionsbackup och exakta radantal dokumenteras i `docs/db-atgarder.md`;
fylls även i den aktuella överlämningen när driftkörningen är verifierad.

Settlement läser alla capture-versioner, grupperar dem var för sig och
stämplar signalversion enligt råcapturens observationstid:

- före 2026-08-01T08:00:00Z: v2;
- 08:00:00Z–20:59:59Z: v3 (ogiltig pilot/historik);
- från 2026-08-01T21:00:00Z: v4 (ren kohort).

`scripts/close_drift_facit.py` och `close_drift_facit_v2.py` har samtidigt
härdats så att varje körning väljer en exakt sharp-`signal_version`; både
nycklar och linjeflyttsjoin innehåller versionen. Close-resultat över
modellversioner får aldrig aggregeras eller korsparas.

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
   veckovis coverage för Kambi-livepris, varje providers source-health,
   `source_runs`/gemensam vattenstämpel och varför priser saknades.
2. Vid mognad: redovisa först den frysta blindkohorten, därefter Följer/Stark,
   xG/skott, liga och minutband som diagnostik — aldrig välj bästa delgrupp
   som nytt huvudresultat i efterhand.
3. Om skottspåret återigen är neutralt: visa bara xG-ligor som
   “granska”-signal och behåll proxydata som coverage.

## Acceptanskriterier före notiser

- minst 40 avslutade signalmatcher och minst 28 kalenderdagar;
- ingen dataläcka från händelser efter capture;
- momentfacit settlas från samma råprovider/event-id/capture-version, medan
  signaljournalens facit använder samma effektiva minut/ställning som UI-
  signalen använde;
- separat facit för xG och proxy;
- positiv undre 90-procentig KI-gräns mot konditionerad basrate;
- bara `chance-gap-shadow-v4` från 21:00Z får bidra; v3 är ogiltig historik;
- nytt uttryckligt beslut från Saman innan push aktiveras.

Notisgaten ovan är separat från blind-ROI-gaten och kan inte i sig göra
signalen spelbar. Inga notiser aktiverades i arbetet 2026-07-31.
