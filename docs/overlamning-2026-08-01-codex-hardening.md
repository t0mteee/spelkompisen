# Överlämning 2026-08-01 — Codex hardening: live v4 och modelldata v4

Detta är den **aktuella överlämningen**. Den ersätter
`docs/overlamning-2026-08-01-flashscore.md`, vars observationer behålls som
historik men vars källordning, v3-status och modelldatalager inte längre är
aktuella. Läs även STATUS-blocket överst i `docs/plan.md`.

Arbetet ändrar inga spel automatiskt. Live-radarn är fortsatt shadow,
V2.2-ligorna är fortsatt research-only och inga notiser har aktiverats.

## Kort resultat

Två datagenererande processer börjar om rent:

- live-radarn vid **2026-08-01T21:00:00Z** under
  `chance-gap-shadow-v4`;
- V2.2 flerliga-shadow under
  `docs/model-v2.2-multileague-forward-manifest-v4.json` och
  `MODEL_DATA_VERSION=4` från **2026-08-01T21:20:00Z**.

v3:s liveperiod 08:00–21:00Z var en **ogiltig pilot**. Raderna raderas inte —
audit kräver historik — men de får aldrig läsas som stöd, blandas med v4 eller
användas för att justera trösklar. Sharp-pipelinen är semantiskt oförändrad
och behåller `DATA_VERSION=3`; det är målmodellens datakontrakt som är v4.

## 1. Live-radarn: tre ärliga källor i stället för en etikett

Flashscore, FotMob och Sofascore har nu var sin råcapture, capture-version,
presence och source-health. En match med färsk chansdata får ett eget kort
även om den inte kan länkas till Sofascore.

### Källval

Källan väljs på **rapporterad struktur**, aldrig på gapets storlek eller på
vilken rad som skulle ge en signal:

1. komplett xG-par;
2. komplett kärnproxy eller komplett signalgren;
3. partiell proxy;
4. inga chansmått.

Vid exakt lika täckning gäller Flashscore → FotMob → Sofascore. Alla
chansmått och 15-minutersdeltat kommer ur den valda providerns egen serie.
Endast saknad minut/ställning får lånas fältvis från en redan verifierad
Sofascore-länk.

Den faktiska råfälttäckningen är providerbunden:

| Provider | Råfält som kan lagras | Saknas i providerschemat |
|---|---|---|
| Flashscore | xG, xGOT, stora chanser, totalskott, skott på mål, skott i box, hörnor | boxberöringar, open-play-xG |
| FotMob | xG, xGOT, open-play-xG, stora chanser, totalskott, skott på mål, skott i box | boxberöringar, hörnor |
| Sofascore | xG, stora chanser, totalskott, skott på mål, skott i box, boxberöringar, hörnor | xGOT, open-play-xG |

“Kan lagras” betyder inte att fältet finns för varje match eller liga. v4
rankar den faktiskt rapporterade raden, inte providerns teoretiska schema.

### Färskhet och koherens

- En länkad eller fristående serie måste vara högst 12 minuter gammal.
- Flashscore har `flashscore-live-v2`: listställning och detaljstats får
  skilja högst 20 sekunder. Annars omhämtas feed/ID-index; kvarstår
  osäkerheten sparas ingen capture.
- FotMob har `fotmob-live-v2`: ställningen tas ur samma eventdetalj som
  statistiken. Listfallback får skilja högst 15 sekunder; annars omhämtas hela
  live-listan och ID-indexet. Okänd ställning blir aldrig påhittat 0–0.
- Sofascore kräver ett välformat objekt med en riktig `events`-lista.
  Transport-/parsefel skriver source-health men ändrar inte presence.

Samma strukturvakt gäller de andra två källorna. FotMob kräver en faktisk
`leagues`-lista; `{}` och `leagues: null` är källfel. Flashscore kräver det
globala `SA÷`-huvudet; en avhuggen feed med bara `ZA÷` är inte ett tomt
livefönster. Därmed kan inget av dessa trasiga 200-svar avsluta fungerande
livekort.

Ett **lyckat** tomt roster hos någon provider är däremot ett riktigt besked:
tidigare kort för den providern markeras avslutade och försvinner direkt i
stället för att hänga kvar till TTL. Vid källfel ligger den gamla 12-minuters-
TTL:n kvar som skydd; felet får inte se ut som att alla matcher tagit slut.
Ett enda lyckat detaljanrop kan inte heller göra ett partiellt varv grönt.
Varje detaljfel eller match som hoppas över gör source-health icke-grön; UI
visar partiellt svar amber och fullständigt/saknat/gammalt svar rött.

### Identitet

Providerlänk kräver samma liga, samma hemma-/bortalag, läsbar avspark inom
30 minuter och exakt en kandidat. Svensk genitiv och en liten observerad
livealiaslista stöds. Prefixkrockar (Inter↔Inter Miami/U23), ungdomslag,
dubbelmöten, speglad hemma/borta och tvetydighet faller stängt. En provider-
match får bara claimas en gång.

Det här är skyddet mot både den gamla Karlsruhe–Inter-krocken och dubbla
Györi-kort, utan att återinföra buggen där verklig Superettan-statistik döljs.

### Vad användaren ser

API:t skickar för varje signal:

- `signal.stats_source` — provider för samtliga chansmått;
- `signal.basis.minute` + `minute_source`;
- `signal.basis.home_score` + `home_score_source`;
- `signal.basis.away_score` + `away_score_source`.

Desktop visar minut-/resultatkällorna i tooltips och en egen källkolumn.
Mobilkort skriver ut fallback öppet, exempelvis
“Flashscore · minut Sofascore”. Varje livekälla har dessutom ett separat
hälsokort. Saknas en kontroll står det rött “ingen kontroll registrerad”.
Gemensam `last_run` finns först när alla tre har kontrollerats och är då den
äldsta av deras tre senaste tider; annars står “inväntar alla tre
livekällor”.

## 2. Signaljournal och settlement

Provider-id är nu en ogenomskinlig sträng i presence, journal och
settlement. Det behövs för Flashscores alfanumeriska id:n och hindrar att en
framtida provider tvingas in i Sofascores heltalsformat.

`backend/scripts/migrera_radar_event_id_text.py` bygger atomärt om
`oddset_live_moment_settlement.event_id` till TEXT. Den bevarar naturlig
primärnyckel `provider/event_id/captured_at/capture_version`, radantal och
index, tar en konsistent backup och kräver både grön FK- och
integritetskontroll före commit.

Settlement har fyra viktiga spärrar:

- alla capture-versioner läses, även äldre osettlade format;
- serier grupperas per provider **och capture-version**;
- radarversion bestäms av råcapturens tid, aldrig av aktiv kod vid
  reparationskörningen: v2 före 08:00Z, v3 08:00–21:00Z, v4 från 21:00Z;
- signalledgerns exakt lånade minut/ställning används i **signaljournalens**
  settlement, så det facitet mäter samma signal som användaren såg.

Det äldre momentfacitet är ett separat diagnostiskt estimand: det räknar
varje råproviderpunkt med just den providerns egen klocka/ställning. Det ska
inte beskrivas som UI-signalens exakta facit eller slås ihop med journalens
blindkohort.

Varje Storage-anslutning aktiverar dessutom SQLite foreign keys. En andra
settlementkörning ska vara idempotent och ge noll nya rader.

## 3. Modell-/statistikproveniens v4

Det gamla lagret överlastade `oddset_results.source` med strängar som
`sofa+fs`, samtidigt som xG och hörnor kunde ha olika ursprung. Det är
avskaffat.

### Resultat och statistik har olika ansvar

- `oddset_results` bär matchidentitet och normaltidsresultat.
- En komplett football-data-rad vinner atomiskt som resultatfacit: källa,
  råa lagnamn samt hemma- och bortamål uppdateras som ett paket. Därmed kan
  ett äldre Sofascore-/straffläggningsresultat inte ligga kvar under falsk
  `fd`-etikett.
- `oddset_result_stats` bär en rad per match och provider med event-id,
  observationstid, starttid, slutställning, xG och hörnor.
- Läsningen väljer ett komplett hem/borta-**xG-par** enligt fryst
  providerprioritet och ett separat komplett **hörnpar**. Proveniens visas som
  `xg_provider*`/`xg_observed_at` respektive
  `corners_provider*`/`corners_observed_at`; fält eller observationstider
  blandas aldrig mellan providers.
- Flashscore och Sofascore samlas parallellt. “Första observationen vinner”
  och skip-av-den-andra-källan är borta.

Resultatskelettet hämtas innan providerstats. Flashscore-länk för avslutad
statistik kräver unik exakt providerstart och samma full-time-resultat;
saknad start eller dubbel träff faller stängt.

### Frånvaro

Flashscore och Sofascore sparas parallellt med provider i primärnyckeln.
Capturen har status `observed` eller `unavailable`; bara ett bevisat
providerbesked får bli `unavailable`. Transportfel får aldrig fabricera
frånvaro. Ett lyckat tomt svar sparas som observerat noll. Spelar-id:n är
TEXT och namespacade `fs:`/`sofa:`; namn-only-fallbacken är också
providerseparerad.

Senastevisningen väljer först bekräftad lineup, därefter senaste capture och
till sist fast providerprioritet. Alla historiska provider-captures ligger
kvar för audit.

`backend/scripts/migrera_modelldata_v4.py` tar backup och migrerar atomärt:
providerstatistik ut ur generiska resultatrader, bort med `+fs`, samt nytt
frånvaroschema. Historiska `+fs`-hörn vars källa inte kan bevisas märks
konservativt `legacy`; migrationen fabricerar inte Flashscore-proveniens.

## 4. V2.2 och close-facit hålls versionsrena

V2.2:s aktuella kontrakt är
`docs/model-v2.2-multileague-forward-manifest-v4.json`, fryst för start
21:20Z. Det fingeravtrycker `MODEL_DATA_VERSION=4`, providerlagret, den
frysta prioriteten och alias för samtliga huvud- och matarligor i `FIT_POOLS`.
Manifest v3 från 21:00Z hann få **0 captures** innan den saknade
matarligefingerprinten upptäcktes; filen lämnas oförändrad som historik.
V1/v2-rader ligger kvar under sina gamla shadowversioner. Inget äldre
manifest får bidra till v4:s träning eller dom.

Frysta runtime-ID:n efter kontrollen är modell `m22-5d7d5120`, features
`f22-86969e71` och kombinerad shadow `v22-be50c514`.

`backend/scripts/close_drift_facit.py` och `close_drift_facit_v2.py` väljer en
exakt `signal_version`; utan argument används ledgerns aktuella sharpversion.
Versionen ingår i minnesnycklar, SQL-filter och linjeflyttsjoin. Det stoppar
de 367 observerade logiska nyckelkrockarna från att para ett gammalt
predictionögonblick med en ny modellversion.

V2-skriptets breda frånvarofönster normaliserar dessutom både kolumn och
gränser med SQLite `datetime()`. Tidigare jämfördes lagrad ISO-tid med `T/Z`
lexikalt mot databasens blankstegsformat, vilket kunde tappa captures på den
övre gränsens kalenderdag.

## 5. Övrig käll-/migrationshärdning

- `migrera_flashscore.py` kör hela schemaombyggnaden atomärt, förvaliderar
  det verkliga legacy-schemat och rullar tillbaka även fel efter påbörjad
  rebuild.
- `kalltest_ip.py` skiljer transporthälsa från Flashscore-statstäckning,
  kräver alla definierade checks samt minst 72 prover **och 72 verkliga
  timmar per källa**. Kort eller saknat underlag blir “UNDERLAG
  OTILLRÄCKLIGT”, aldrig ett falskt godkännande eller en diskvalificering.
- `brotli` är uttryckligt installationskrav för CloudFront-/Flashscore-svar.

## 6. Produktionskvitto — stoppad och säker driftkörning

Backend, snapshot-jobbet och pool-jobbet stoppades före migrationerna.
Databasen säkerhetskopierades före respektive ändring och båda migrationerna
kördes därefter en andra gång för att verifiera idempotens.

### Modelldata v4

- Backup: `backend/data/backups/stryktips-2026-08-01-fore-modelldata-v4.db`
- Resultatrader bevarade: **11 665**
- Providerstats efter migration: **9 665**
- Frånvarocaptures bevarade: **1 714**
- Frånvarospelare bevarade: **8 058**
- Integritet/FK: `integrity_check=ok`, 0 foreign-key-fel. Andra körningen
  gav 0 inserts och byggde inte om något schema.

### Radar event-id TEXT

- Backup:
  `backend/data/backups/stryktips-2026-08-01-fore-radar-event-id-text.db`
- Momentsettlement-rader bevarade: **17 774** före återhämtad settlement
- PK/schema/integritet/FK: `event_id TEXT`, PK
  `(provider, event_id, captured_at, capture_version)`,
  `integrity_check=ok` och 0 foreign-key-fel. Andra körningen var en no-op.

### Återhämtad settlement

- Första körningen: **5 112** nya rader — Flashscore 467, FotMob 451 och
  Sofascore 4 194; censur A 799, censur B 1 820 och 20 öppna serier.
- Andra idempotenskörningen: **0** nya rader; 20 öppna serier kvar.
- Direkt efter återhämtningen: **22 886** rader — v2 17 288, v3 5 598 och
  v4 0. Efter återstart settlade det ordinarie jobbet ytterligare 179 gamla
  v3-captures. Driftkvittot 2026-08-01T21:31Z är därför **23 065** rader —
  v2 17 288, ogiltig pilot v3 5 777 och v4 0. En direkt omkörning skapade
  0 nya rader och lämnade 16 öppna serier. v4 är korrekt tom eftersom inga
  matcher var live efter dess startgräns vid kontrollen.

### Verifiering efter omstart

- Full backendsvit: **501/501 tester gröna**.
- Frontend: produktionsbygget och **3/3 nya källhälso-UI-tester gröna**.
- Frontend-lint: projektets befintliga baseline är fortfarande röd med
  39 fel och 5 varningar, främst nya React-regler i äldre komponentkod.
  Denna leverans introducerar inte de rapporterade mönstren; en bred
  lint-/komponentrefaktor ingick inte i käll- och datahärdningen.
- API-/browserkontroll: `/api/health` grönt; live-radarn rapporterade
  `chance-gap-shadow-v4` och separat frisk source-health för Flashscore,
  FotMob och Sofascore. Desktop och 390 × 844 kontrollerades utan
  horisontellt spill eller konsolvarningar. Vanliga Oddset-vyn visar även
  Premier League, Serie A, La Liga och Bundesliga som research-ligor. V2.2-
  API:t rapporterade manifest v4 med `v22-be50c514`/`f22-86969e71`, 0 rader
  vid den rena starten och fortsatt `actionable=false`/`notifications=false`.
- launchd/backendstatus: backend lyssnar på port 8002; snapshot-jobbet är
  återstartat och pool-jobbets senaste körning avslutades utan fel. Den
  första skarpa v4-ticken gav 0 matcher/captures hos alla tre providers —
  ett väntat tomt livefönster, inte ett källfel.

Samma exakta DB-kvitto är fört i `docs/db-atgarder.md` enligt projektregeln.

## 7. Nästa säkra arbete

1. Låt live-v4 och V2.2-manifest v4 samla helt orört. Tolka inte live-v3 och bakfyll
   inga missade liveodds, stats eller V2.2-horisonter.
2. Kontrollera veckovis tre saker: source-health/presence per liveprovider,
   coverage per faktiskt `stats_source` samt andel signaler med observerat
   öppet Kambi-livepris.
3. Kör close-driftfacit endast på dess förregistrerade kadens och skriv alltid
   ut vald exakt `signal_version` i rapporten.
4. Ändra inte live-trösklar efter att ha sett v4-utfall. Ny källa, annan
   rankning, annan färskhet eller annan identitet kräver ny version och nytt
   forwardfönster.
5. Blind Över-ROI får tidigast ge stöd vid ≥200 oddssatta+avgjorda v4-matcher,
   ≥60 dagar och undre KI90 > 0. Push/automatiska spel kräver fortfarande ett
   nytt uttryckligt produktbeslut.

## Viktiga filer

- `backend/app/live_radar.py`, `flashscore.py`, `fotmob.py`
- `backend/app/live_signal_ledger.py`, `live_settlement.py`
- `backend/app/storage.py`, `oddset_data.py`, `flashscore_data.py`
- `backend/app/oddset_v22.py`
- `backend/scripts/migrera_radar_event_id_text.py`
- `backend/scripts/migrera_modelldata_v4.py`
- `backend/scripts/close_drift_facit.py`, `close_drift_facit_v2.py`
- `docs/live-radar-2026-07-25.md`, `docs/db-atgarder.md`
