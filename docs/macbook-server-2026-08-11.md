# MacBook-server — produktionsskifte 2026-08-11

> **Aktuell status:** MacBooken tog över produktionen den 11 augusti cirka
> 18:27 lokal tid. Huvuddatorns snapshot-, pool-, backend- och frontendjobb
> är stoppade men dess orörda databas finns kvar som omedelbar rollback.

## Syfte och säker avgränsning

Den gamla Intel-MacBooken kör Spelkompisen på lokaladressen
`192.168.50.100`. Skiftet gjordes utan parallella skrivare: först stoppades
snapshot och pool/live på huvuddatorn, därefter togs en SQLite-onlinebackup,
den verifierades lokalt och på MacBooken och gjordes slutligen aktiv där.

Följande körs nu på MacBooken:

- backend och byggd frontend;
- Oddset-snapshot på :00/:30 med smart förtätning;
- pool, settlement och liveradar var femte minut med :02-offset;
- ett separat, append-only IP-/källprov var sjätte timme;
- ett kontinuerligt `caffeinate -s`-skydd mot systemvila på nätström.
- Chartervakt på port `3100`, med Ving och TUI samt sina åtta befintliga
  bevakningar.
- Bonusvakt på port `3000`, med fyra inloggningsfria SAS-bevakningar och
  ntfy-notiser.

Inga spel läggs automatiskt och NTFY är fortsatt avstängt.

## Installerad miljö

- macOS 15.7.9, Intel x86_64, 16 GB RAM;
- Apples Command Line Tools 16.4;
- användarlokal Miniforge i
  `/Users/saman/.local/spelkompisen-runtime`;
- Python 3.13 i projektets vanliga `backend/.venv`;
- Node 22 och npm i den användarlokala körmiljön;
- konsekvent SQLite-onlinebackup från huvudmaskinen, verifierad med
  `PRAGMA integrity_check` både före och efter kopieringen.

Miniforge används bara som lösenordsfri grund för Python och Node. Backendens
paket ligger fortfarande i projektets vanliga venv; någon global
Python-miljö används inte av appen.

## Första acceptansprov

Källprovet den 11 augusti var helt grönt:

| källa | resultat |
|---|---|
| Svenskaspel | OK |
| Pinnacle | OK, 5 585 objekt |
| Kambi | OK |
| Sofascore modell | **8/8 endpoint-typer OK** |
| Sofascore live | OK |
| Flashscore | OK, chansdata för 3/3 provade matcher |
| FotMob | OK |
| Altenar | OK |

Backendens fulla svit gav **647 av 647 godkända tester** på MacBooken.
Frontendens fem tester var gröna och produktionsbygget slutfördes på cirka
en halv sekund. Från en annan dator på hemnätet svarade startsidan på cirka
0,03 sekunder och den kalla, lätta Oddset-frågan på cirka 0,74 sekunder.

Efter produktionsskiftet svarade `/api/health` `ok`. De två första färdiga
pool/live-varven skrev nya snapshots och livecaptures; det andra skrev även
en ny radarsignal. Oddset-varvet skrev nya, gröna källkontroller för bland
annat Pinnacle, SvS, Expekt, Smarkets, Matchbook, FotMob och Flashscore.

Det ursprungliga försiktighetskriteriet var minst 72 användbara prov över 72
timmar. Saman valde i stället ett direkt, reversibelt produktionsskifte när
engångstest, apptester och de första riktiga skrivvarven var gröna. Källprovet
fortsätter var sjätte timme som tidig varning och långsiktigt IP-facit, men är
inte längre en grind före drift.

## Autostart

Åtta LaunchAgents kör på MacBooken:

- `com.saman.spelkompisen.backend` — backend på `127.0.0.1:8002`;
- `com.saman.spelkompisen.frontend` — byggd frontend på alla lokala
  gränssnitt, port `5175`;
- `com.saman.spelkompisen.snapshot` — ordinarie Oddset-insamling;
- `com.saman.spelkompisen.pool` — pool, settlement och liveradar;
- `com.saman.spelkompisen.kalltest` — fristående IP-/källprov var 6:e timme;
- `com.saman.spelkompisen.awake` — håller systemet vaket på nätström.
- `com.saman.chartervakt` — Chartervakt på alla lokala gränssnitt, port
  `3100`.
- `com.saman.bonusvakt` — Bonusvakt på alla lokala gränssnitt, port `3000`;
  interaktiv Aqua-process eftersom manuell partnerinloggning öppnar Chrome.

Mallarna finns i `backend/scripts/`. Motsvarande snapshot- och pooljobb är
oladdade på huvuddatorn och får inte startas samtidigt med MacBookens jobb.

Tjänsterna är LaunchAgents och återstartar om deras processer faller; detta
är verifierat. Automatisk inloggning är avstängd, så efter en
full omstart måste `saman` tills vidare logga in på MacBooken innan de startar.
Före skarp, obemannad drift bör de flyttas till systemtjänster som körs som
användaren `saman`, vilket kräver en enda lokal administratörsgodkänning.

På samma wifi öppnas appen på:

`http://192.168.50.100:5175`

Chartervakt öppnas på:

`http://192.168.50.100:3100`

Bonusvakt öppnas på:

`http://192.168.50.100:3000`

Serverkontrollen finns i `tools/spelkompisen_menubar.py`. MacBook-servern kör
den kontinuerligt med en lokal tjänstestack-ikon. Huvuddatorn har i stället
`~/Desktop/Serverkontroll.app`, som startar fjärrkontrollen vid behov, visar
en tjänstestack med utåtriktad pil och avslutas efter 15 minuters inaktivitet.
Ingen fjärrmonitor startar automatiskt där. Serverversionen använder lokala
adresser och `launchctl`; fjärrversionen använder HTTP och SSH. Båda visar
`✓` när Spelkompisen, Chartervakt och Bonusvakt, API, datastatus,
insamlare och sömnskydd är friska. De kontrollerar var 30:e sekund och har
genvägar till båda apparna. Sedan 2026-08-11 har de även en **Tjänster**-meny
med Starta / Stoppa / Starta om / Stoppa permanent per tjänst samt *Starta allt
som ligger nere*. Den går genom `tools/spelkompisen_tjanster.py` — samma modul
som `tools/tjanster.sh` i terminalen — och kör launchctl lokalt på MacBooken
respektive över ssh från huvuddatorn. Tjänsterna grupperas synligt som
Spelkompisen, Chartervakt, Bonusvakt och Server & övervakning; kör/väntar
visas grönt och stopp/fel rött. MacBookens separata plistmall heter
`backend/scripts/com.saman.spelkompisen.server-menubar.plist` och laddas som
en interaktiv Aqua-LaunchAgent. Den gamla
menyradsappen tillhör ett annat projekt och ändras inte; om båda ikonerna
syns avslutas den gamla manuellt från dess egen meny.

På huvuddatorn är de gamla lokala Spelkompisen-jobben `snapshot`, `pool` och
`menubar` urkopplade och deras plist-filer arkiverade under
`~/Library/LaunchAgents.disabled`. Där ska inte heller någon Chartervakt- eller
Bonusvakt-process köras. Skrivbordsappen är endast en fjärrkontroll och startar
ingen lokal insamling.

## Chartervakt — produktionsskifte 2026-08-11

Chartervakt flyttades separat efter att samma kod hade installerats på
MacBooken och alla **176 tester** var gröna där. Den gamla processen stoppades
innan den slutliga SQLite-backupen togs, så endast en instans kan skriva.
Kopian verifierades på båda datorerna med `integrity_check=ok` och innehöll
8 bevakningar, 2 919 sedda erbjudanden, 23 018 prisnoteringar och 327
insamlingskörningar. MacBookens första start skapade dessutom en egen
öppningsbackup i `/Users/saman/charter/backups/`.

MacBooken kör `/Users/saman/charter/src/server.mjs` med sin användarlokala
Node 22. Ving och TUI är aktiva; Apollo är fortsatt avstängt enligt projektets
befintliga konfiguration. Push är okonfigurerad precis som före skiftet.
Efter starten gjordes varsin läsande en-dagssökning mot Ving och TUI från
MacBooken; båda gav riktiga paket utan källfel. Bevakningshistoriken ändrades
inte av dessa prov.
Huvuddatorns port 3100 är avstängd, men projekt och databas är orörda som
rollback. Chartervakts egen korta drift-/rollbacknot finns som
`/Users/saman/charter/DRIFT-MACBOOK-2026-08-11.md` på båda datorerna.

## Bonusvakt — produktionsskifte 2026-08-11

Bonusvakt flyttades efter **102 gröna tester** och ett skarpt, läsande
SAS-källprov från MacBooken som gav HTTP 200 och riktiga bonusplatser. Den
verifierade databaskopian innehöll 4 bevakningar, 1 oschemalagd
partnerfavorit, 29 aktuella platsposter, 80 notiser och 4 566
insamlingsrader. Ntfy följde med och API:t svarar grönt på port 3000.

Vanliga SAS-bevakningar är inloggningsfria och kör fullt ut. Den gamla
Chrome-sessionen kopierades medvetet inte eftersom dess kakor är bundna till
huvuddatorns nyckelring; partnerfavoriten är inte schemalagd och påverkar
därför inget automatiskt. SAS-lösenordet lagras aldrig av projektet. Saman
kan senare välja **Logga in till SAS** på partnersidan och använda SAS
**Glömt lösenord** i Chrome på MacBooken.

Bonusvakts gamla `PUBLIC_URL` var huvuddatorns Tailscale-IP. Tills Tailscale
installerats på MacBooken överstyr LaunchAgenten den med
`http://192.168.50.100:3000`, så notislänkar fungerar på hemnätet. Full
drift-/rollbacknot finns i
`/Users/saman/sas/DRIFT-MACBOOK-2026-08-11.md` på båda datorerna.

## Topptipsets live- och settlementkontroll 2026-08-11

Efter skiftet såg Topptipset 4260 ut att inte rättas och UI:t stod kvar på
“Livestatus otillgänglig”. Databasen och femminutersjobbet var friska.
SvS-payloaden visade att omgången faktiskt fortfarande pågick: sista matcher
startade 20:15, 20:30 och 21:00 svensk tid. Settlementmaskinens nästa försök
23:10 är därför avsiktligt — senaste avspark plus 130 minuters matchmarginal,
normaliserat korrekt till UTC.

UI-felet var separat: spelade kuponger hämtade livestatus bara en gång vid
sidöppning. Ett tillfälligt uppströmsfel blev därför kvar tills man laddade om
sidan, trots att nästa backendanrop fungerade. Öppna kuponger uppdateras nu
var 60:e sekund, transportfel säger uttryckligen att automatisk retry sker och
backend loggar produkt/omgång samt full felorsak. Verifierat med 52 relevanta
backendtester, fem frontendtester, produktionsbygge och skarpt live-API efter
distribution till MacBooken.

## Kvar för helt obemannad drift

1. Reservera `192.168.50.100` för MacBooken i routerns DHCP-inställningar;
   adressen delas just nu ut via DHCP och är alltså inte garanterad.
2. LaunchAgents kräver fortfarande att `saman` är inloggad efter en full
   omstart. Före helt obemannad drift bör de flyttas till systemtjänster som
   kör som `saman`; det kräver ett lokalt administratörsgodkännande.
3. `caffeinate` hindrar systemvila på nätström men ett stängt laptoplock är
   en separat fysisk vilosignal. Kör med locket öppet eller i korrekt
   clamshell-läge med nätström och extern skärm.
4. Bestäm hur åtkomst utanför hemmet ska lösas; exponera inte port 5175
   direkt mot internet. Samma sak gäller Chartervakts port 3100 och
   Bonusvakts port 3000. Bonusvakt behöver Tailscale för fungerande externa
   notislänkar.

## Rollback

1. Ladda ur snapshot och pool på MacBooken.
2. Ladda tillbaka huvuddatorns befintliga
   `com.saman.spelkompisen.snapshot.plist` och
   `com.saman.spelkompisen.pool.plist`.
3. Starta huvuddatorns backend/frontend igen.

Om MacBooken hunnit skriva data efter skiftet bör databasen först kopieras
tillbaka med samma SQLite-onlinebackup-rutin, så att inga nya snapshots eller
radarsignaler tappas. Starta aldrig båda skrivarparen samtidigt.

För Chartervakt: ladda först ur `com.saman.chartervakt` på MacBooken. Ta en
SQLite-backup av dess aktuella `/Users/saman/charter/chartervakt.db` tillbaka
till huvuddatorn om nya körningar hunnit ske, och starta först därefter den
gamla Chartervakt-processen. Kör aldrig båda Chartervakt-instanserna samtidigt.

För Bonusvakt gäller samma regel med `com.saman.bonusvakt`, port 3000 och
`/Users/saman/sas/sas-monitor.db`. Kopiera tillbaka MacBookens senaste
SQLite-backup innan den gamla processen startas om. Kör aldrig båda
Bonusvakt-instanserna samtidigt.
