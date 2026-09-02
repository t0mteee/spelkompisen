# Överlämning 2026-07-31 — live-radarns signaljournal

Det här är aktuell överlämning efter Samans beställning att spara vad som
händer efter live-radarns faktiska signaler, inklusive matchminut, ställning,
live-Ö/U och slutresultat. Läs statusöversikten i `docs/plan.md` först;
metoden och grindarna finns i `docs/live-radar-2026-07-25.md`.

## Levererat

- Den befintliga råserien och momentsettlingen är bevarad. Den fortsätter
  mäta alla captureögonblick och konditionerad kontrollgrupp.
- Ny `app/live_signal_ledger.py` sparar den första synliga förekomsten per
  `match × signalversion × signaltyp × nivå`. En kvarliggande signal räknas
  därför inte om varannan minut. Följer som senare blir Stark ger en andra,
  uttrycklig eskaleringsrad.
- Varje signalrad bär provider/event-id och version, capture-/registreringstid,
  liga/lag, minut, ställning, signalens lag/sida/förklaring, xG-/skottmått och
  återstående tid.
- Kambi-klienten har en separat liveparser. Den läser bara fulltidens
  `Antal mål`/`Total Goals`, kräver `OFFERED_LIVE`, kräver båda utfallen
  `OPEN` och föredrar `MAIN_LINE`. Suspenderat pris får aldrig bli spelbart.
- Signalögonblicket sparar SvS/Kambis live-huvudlina samt både Över- och
  Under-odds. Oddsens observationstid är separat och korrigeras för HTTP
  `Age`. Livepris skrivs aldrig till prematchkanon `oddset_odds`.
- Efter matchen sparas normaltidsresultat, mål efter signalen, mål inom nästa
  15 matchminuter, ytterligare mål före FT och enhetsresultat för Över-linan.
  Asian hel-/halv-/kvartslinje hanterar win, half_win, push, half_loss, loss.
- Ny UI-yta i `Labb → Radar-facit och signaljournal`: exakta trösklar,
  nivåförklaring, fryst blindgate, nivågrupper och detaljerad signaljournal.
  Mobilen visar en kolumn utan horisontell overflow.
- `live-tick` fångar nya signaler direkt efter FotMob/Sofascore-varvet medan
  marknaden fortfarande är live och settlar öppna signaler efteråt. Alla nya
  steg är skyddade så att journalfel aldrig fäller radarinsamlingen.

## Nivåer och frysta regler

- **Info:** ingen aktiv signal; sparas i råserien men inte som ett tänkbart
  spel i beslutssignaljournalen.
- **Följer · xG:** minut 15–78, minst 12 minuter kvar; lagets
  `xG−mål ≥ 0,65` eller matchens `total xG−mål ≥ 1,00`.
- **Stark · xG:** samma fönster; lagets `xG−mål ≥ 1,15` eller matchens
  `total xG−mål ≥ 1,65`.
- **Följer · skott:** minut 20–78, minst 12 minuter kvar; antingen
  `stora chanser−mål ≥ 1,5` eller `skott på mål−mål ≥ 5` och minst åtta
  skott i box.
- Skott har ingen Stark-nivå i `chance-gap-shadow-v2`. Lägg inte till eller
  justera nivåer efter att ha tittat på utfallet utan en ny förregistrering
  och signalversionsbump.

## Facit och beslutsgate

Två frågor hålls avsiktligt isär:

1. `live_settlement` mäter om signalögonblick har högre målfrekvens än
   jämförbara kontrollögonblick (liga × minutband × ställning).
2. `live_signal_ledger` mäter om den faktiska synliga signalen hade gått att
   rygga på observerad live-Över-lina.

Blindkohorten är förregistrerad till **första aktiva signalen per match**.
Den får stödstatus först vid minst 200 oddssatta och avgjorda matcher, minst
60 dagars spann och positiv undre 90-procentig bootstrapgräns för enhets-ROI.
Följer/Stark och xG/skott visas diagnostiskt men får inte ersätta huvudkohorten
genom efterhandsval.

Vid överlämningen hade det första riktiga driftvarvet inga livematcher. Den
nya journalen står därför korrekt på 0/200 och 0/60. Historiska liveodds har
inte bakfyllts. Den gamla momentserien har 15 925 settlade ögonblick men är
nära neutral för mål inom 15 minuter; den är inget stöd för blind ryggning.

## Databas och drift

- Additiva tabeller: `oddset_live_signal` (42 kolumner) och
  `oddset_live_signal_result` (13 kolumner), append-only/unikhetsvakt.
- Migration: `backend/scripts/migrera_live_signal_ledger.py`.
- Backup:
  `backend/data/backups/stryktips-2026-07-31-fore-live-signal-ledger.db`.
- Båda tabellerna var tomma och `PRAGMA integrity_check=ok` vid aktivering.
  Den tomma schemamaterialiseringen före det explicita migreringsskriptet är
  ärligt noterad i `docs/db-atgarder.md`.
- Backend är omstartad på port 8002. `/api/oddset/radar-facit` exponerar
  `signal_ledger`, regler, gate, grupper och rader. Launchd:s vanliga
  `live-tick` fortsätter insamlingen automatiskt.

## Verifiering

- 363 backendtester gröna.
- Frontend-build grön.
- `git diff --check` grön.
- API verifierat mot produktions-DB.
- Browser verifierad på desktop och 390 px mobil: regler/gate synliga,
  ingen sidscroll, inga console errors.
- Regressionstest finns för append-once, Följer→Stark, info-exkludering,
  settlement, kvartslinje, blindgate, idempotent migration och Kambis verkliga
  liveformat inklusive suspenderad marknad.

## Nästa säkra arbete

1. Låt serien växa. Kontrollera veckovis antal nya/settlade signaler,
   livepristäckning och fördelningen av `no_canonical_match`,
   `no_svenskaspel_id`, `not_offered` och `source_error`.
2. När första signalen har settlats: kontrollera manuellt en rad hela vägen
   från provider-capture och Kambi-observation till normaltidsresultat och
   Asian-vinst. Ändra inte raden; dokumentera avvikelse om något inte stämmer.
3. Gamla momentfacitets `outcome_more_before_ft` visar i nuläget en
   degenererad 100-procentsrad och ska inte tolkas. Den nya journalens
   normaltidsankrade slutresultat är den relevanta framåtriktade vägen.
4. Sänk inte trösklar för att få snabbare volym. Om volymen blir för låg,
   redovisa först coverage per liga, provider och signaltyp och förregistrera
   sedan ett eventuellt nytt experiment.
5. Ingen push, automatisk insats, Kelly-ändring eller modell-/systemkoppling
   är godkänd. Allt förblir shadow tills Saman tar ett nytt uttryckligt beslut.

## Viktiga filer

- `backend/app/live_signal_ledger.py`
- `backend/app/kambi.py`
- `backend/app/storage.py`
- `backend/app/live_radar.py`
- `backend/app/live_settlement.py`
- `backend/cli.py`
- `frontend/src/AppV3.jsx`
- `frontend/src/AppV3.css`
- `backend/tests/test_live_signal_ledger.py`
- `backend/tests/test_live_signal_migration.py`
- `docs/live-radar-2026-07-25.md`
- `docs/db-atgarder.md`
