# Live-radar v6: Sofascore ur, Flashscore som ankare — 2026-08-06

Beställare: Saman, efter att ha sett **fyra dubbletter samtidigt** i Live-vyn
under europacupkvällen. Hans ord: *"Trodde vi hade löst detta?"* — en rimlig
fråga, eftersom 13 providerpar länkades så sent som 2026-08-05.

Svaret är att aliasjakten var fel verktyg. Varje ny kvalomgång drar in nya
klubbar, och internationellt spel har en **egen namnkonvention** som ingen
lista hinner ikapp. Den här omgången löser klassen i stället för fallen.

---

## Del 1 — NULÄGET (mätt före ändring)

`/api/oddset/live-radar`, 12 kort där 8 unika matcher fanns:

| Match | Kort | Namn per källa |
|---|---|---|
| KuPS–Craiova | **3** | `KuPS (Fin)` / `KuPS` / `Kuopion Palloseura` |
| Paide–Rapid | **2** | `Paide (Est)` / `Paide Linnameeskond` |
| Jagiellonia–Rangers | **2** | `Jagiellonia (Pol)` / `Jagiellonia Białystok` |

### Varför länkningen föll

Landskoden `(Est)` strippas redan korrekt av `live_norm_team`. Problemet är
vad som blir KVAR: ett **enordsnamn** som är prefix av det andra. Enords-prefix
är spärrat med flit — annars blir `Inter` samma lag som `Inter Miami`.

Alltså föll exakt de par regeln var till för, och de såg olika ut varje kväll.

### Sofascore rapporterade falska nollor

Paide–SK Rapid, samma ögonblick:

| Källa | xG hemma | xG borta |
|---|---|---|
| Flashscore | 0,09 | **0,81** |
| Sofascore | **0,0** | **0,0** |

En nolla är inte saknad data — den ser ut som en mätning. Kortet läste alltså
som "inga chanser skapade" mitt i en match där bortalaget hade 0,81 xG. Det
är sämre än att sakna kortet helt, och det var Sofascore-kortet Saman såg.

### Statistiken som "uppenbarligen finns hos Flashscore"

Mätt över 12 samtidiga livematcher — feeden levererar två olika paket:

| Paket | Matcher | Innehåll |
|---|---|---|
| Bas | **8/12** | possession, skott, på mål, utanför, blockerade, hörnor, offside, fouls |
| Fullt | **2/12** | + xG, xGOT, stora chanser, skott i boxen, touches i box |
| Inget | 2/12 | (träningsmatcher) |

Vi läste **6 fält** av dem. Bland de olästa fanns `Touches in opposition box`
— ett fält som redan ingick i radarns täckningsrankning (`_stats_rank`), så
rankningen räknade på något ingen källa kunde fylla.

**xG saknas alltså genuint för de flesta europacupkvalmatcher.** Det är
providerns gräns, inte vår parser. Men skott/hörnor/possession fanns hela
tiden.

---

## Del 2 — ÅTGÄRDERNA

### 1. Sofascore urkopplad ur radarn — Flashscore blir ankare

`payload()` loopade över Sofascore-matcher och länkade de andra till dem.
Nu är Flashscore ankaret (bäst täckning: 19 av 19 matcher i slutmätningen)
och FotMob länkas dit, med egna ben för matcher Flashscore saknar.

**Sofascore är OFÖRÄNDRAD** i resultat (`RESULT_ONLY_UT`/`SOFA_UT`),
modellstatistik (`oddset_result_stats`) och frånvaro. Ingenting i
wp9c-/V2.2-fingeravtrycken rörs. `oddset_live_capture` behålls som historik.

### 2. Kontextlänkning i två steg

Ny `_same_team_in_context`, som **bara** får användas där liga, exakt avspark
och kravet på en enda kandidat redan håller:

1. **Strikt först** (`_same_team`). Träff ⇒ klart. Två träffar ⇒ tvetydigt,
   ingen länk.
2. **Kontextregeln bara i tomrummet** — kortnamn (`paide` ⊂ `paide
   linnameeskond`), förkortning (`univ craiova` ⊂ `universitatea craiova`)
   och grundningsår i mitten (`cfr cluj` ⊂ `cfr 1907 cluj`).

Alla spärrar gäller oförändrat: `LIVE_TEAM_REJECTED`, truppmarkörer
(U21/B/women) och kravet på entydighet. `Inter` ↔ `Inter Miami` passerar
namnregeln men kan aldrig länkas — de delar aldrig liga och avspark. Det är
med flit: skyddet ligger i kontexten, därför får regeln aldrig användas
fristående.

### 3. Aliasbuggen: landskoden slog ut ALLA alias

`live_norm_team` körde `norm_team` (som slår upp `TEAM_ALIASES`) på hela
strängen — alltså på `goteborg (swe)`, en nyckel som aldrig finns. Landskoden
ströks först därefter.

Följden: **varje alias slutade tyst gälla så snart matchen var
internationell.** `Goteborg (Swe)` ↔ `IFK Göteborg` låg som två kort samtidigt
som enhetstestet för exakt det paret var grönt — det testade namnet utan kod.

Aliaset prövas nu om efter strippningen. Det löste Göteborg, Norrköping och
Värnamo på en gång.

### 4. Fyra observerade alias som ingen regel bör gissa

| Par | Varför inte generellt |
|---|---|
| `copenhagen` → `kobenhavn` | översättning; ingen gemensam teckenstruktur |
| `gyor` → `eto gyor` | providern kortar till stadens namn |
| `inter escaldes` → `inter club descaldes` | insatt ord **och** apostrof; `atletic club escaldes` finns i samma liga |

### 5. Fem nya måttpar ur Flashscore

`shots_off`, `shots_blocked`, `touches_box`, `saves`, `possession`.
Bollinnehav läses med en egen `_share` — `_f` avvisar procent med flit,
eftersom feedens andra procenttal är härledda kvoter (`85% (271/319)`) där
andelen inte är måttet.

### 6. Minuten: säg PAUS i stället för tomt

Klockan härleds ur stadiets starttid och är `None` i halvtid — korrekt censur,
men ett tomt fält läser som att vi tappat matchen. `stage=38` mättes på sex
samtidiga matcher (stadiet började 45–50 min efter avspark, båda källorna
slutade rapportera minut, matcherna gick vidare till `13`). Kortet visar nu
**Paus**; minuten förblir censurerad. Okänd kod ⇒ inget påstående.

Dessutom lånar Flashscore-kortet klocka från en länkad FotMob-serie när den
egna saknas — `fallback_source` följer med raden i stället för att vara
hårdkodad till `"sofascore"`, vilket hade blivit ren lögn efter ankarbytet.

### 7. Kohortstämpeln nådde inte journalen

`radar_version` saknades i `_FLASHSCORE_VIEW_KEYS`/`_FOTMOB_VIEW_KEYS`, så
journalen tappade radens egen version och föll tillbaka på härledning ur
observerade växlingar. Varje rad efter den sista kända växlingen blev därmed
`transitional` — alltså raderad ur blindkohorten. Exakt det fel kohortregeln
infördes för att stoppa, en dag efter att den infördes.

Journalens `_clock` läser nu signalens `basis` i stället för att härleda
lånet en andra gång; två oberoende härledningar av samma sak var det som gick
isär i verifieringsrundan 2026-08-01.

### 8. Detektorn körde andra regler än länken

`cli.py lanklucka` mätte med den strikta regeln och listade därför par som nu
länkar utmärkt — den letade efter en annan sorts fel än det som uppstår.
Samma lärdom som `live_norm_team` bär sedan 2026-08-05. Den använder nu samma
tvåstegslogik.

---

## Del 3 — EFTERLÄGET

Samma mätning, samma kväll:

| | Före | Efter |
|---|---|---|
| Kort | 12 (8 unika) | **19 (19 unika)** |
| Dubbletter | 4 matcher | **0** |
| Länkade FotMob-serier | delvis | **19 av 19** |
| `cli.py lanklucka` | 7 par | **inga** |
| Lästa Flashscore-fält | 6 | **12** (bas) / 17 (fullt) |

Driftverifierat kl 19:2x: samtliga 19 kort bär `+fm`, `by_source` säger
`flashscore 19, fotmob 0` (alla FotMob-serier länkade, ingen står ensam), och
`possession`/`touches_box` fylls.

**558 backend-tester gröna** (6 nya som låser kontextregeln, dess spärrar,
tvåstegsordningen, `radar_version` i vyn, aliaset genom landskoden och att
Sofascore inte är livekälla). `vite build` exitkod 0.

### Kohorten

`chance-gap-shadow-v6` från **2026-08-06T16:45:00Z**. Fyra ändringar i samma
datagenererande process (borttagen provider, ny länkning, nya mått, ändrad
källrankning) — kohorten börjar om och v5 blandas aldrig in. Testfixturernas
`NOW` flyttades in i det nya fönstret, enligt instruktionen som redan stod i
testfilen.

### Vad som INTE gjordes

- **Signalregeln är orörd.** Proxysignalen kräver stora chanser och skott i
  boxen, vilket Flashscore inte ger för de flesta kvalmatcher — så den kan
  sällan utlösa där. Att sänka kravet vore en metodändring som nollställer
  blindkohorten och kräver förregistrering. Rapporterat, inte ändrat.
- **Ingen bakfyllning.** Nya fält gäller framåt; historiska rader har NULL,
  vilket betyder oobserverad, aldrig mätt noll.

---

## Del 4 — ANDRA OMGÅNGEN samma kväll

Saman såg **en dubblett till** och två fel som första omgången inte fångade.

### Steg 3: ett lag räcker

`Austria Vienna` ↔ `Austria Wien` är en översättning, och nästa kväll är det
en translitteration vi inte sett. Namnklasserna tar aldrig slut, så
`_linked_series` fick ett tredje steg som inte handlar om namn alls:

> Delar två providerrader liga och **exakt** avspark, och är ett av lagen
> samma, kan de omöjligen vara olika matcher — ett lag spelar en match i taget.

Steget körs bara när båda namnstegen gett noll kandidater och kräver som de
en enda kandidat. **Truppmarkörer spärrar i alla tre stegen** — ett test
fångade att `Inter` mot `Como` och `Inter U23` mot `Como` annars hade slagits
ihop. `_squad()` är nu delad av alla steg.

Detektorn anropar `_linked_series` direkt i stället för att härma reglerna;
den hade hamnat efter två gånger i rad.

### Pausen dödade signalen

Minuten censurerades i halvtid, och utan minut returnerar `radar_signal`
`no_clock` → nivån faller till `info`. En match med stort chansgap föll alltså
ur "starkt chansgap" i samma sekund domaren blåste av — precis när gapet är
intressant.

Paus är inte okänd tid: den inträffar per definition efter 45 spelade
minuter. `STAGE_FROZEN` bär etikett och minut tillsammans så de inte kan
glida isär; klockan fryses vid 45 och pausens längd läggs aldrig på.

### Klockan saknas aldrig

Tre lägen: `STAGE_LABEL` (frysta stadier) visas **i klockans ställe** eftersom
`45′` antyder att spelet pågår; annars minuten; annars `STAGE_NAME` som reserv
när koherensvakten nollställt stadieklockan. Ordet "saknas" är borta ur
klockan, och payload sanerar historiska etiketter så en gammal rad inte
ersätter en minut som är sannare.

**Efterläge:** 16 kort, 0 dubbletter, **0 kort utan klockinfo**, och
paus-matcher behåller sina xg/proxy-signaler. 560 tester gröna.

---

## ÖPPEN FRÅGA: proxysignalen är död efter Sofascore-borttaget

Mätt på 37 matcher (24 h, Flashscore), senaste capture per match:

| Fält | Täckning |
|---|---|
| skott på mål | **37/37 (100 %)** |
| bollinnehav | **37/37 (100 %)** |
| xG | 15/37 (41 %) |
| stora chanser | 15/37 (41 %) |
| skott i box | 15/37 (41 %) |
| touches i box | 15/37 (41 %) |

Proxyn kräver *stora chanser* ELLER *(skott på mål OCH skott i box)* — alltså
exakt de fält som bara finns när xG också finns. Konsekvensen, uppmätt:

- matcher där proxyn tillför något utöver xG-signalen: **0 av 37**
- matcher som aldrig kan få NÅGON signal: **22 av 37 (59 %)**

Proxyn fungerade tidigare eftersom Sofascore bar `big_chances` och
`touches_box` bredare. Att koppla bort Sofascore var ändå rätt — den
rapporterade falska xG-nollor — men konsekvensen för proxyn förutsågs inte.

**Förslaget** är att bygga om proxyn på de fält som faktiskt finns i
baspaketet (skott på mål, totala skott, hörnor, bollinnehav — alla 100 %
täckta). Det är en **metodändring**: den byter signalversion, nollställer
blindkohorten igen och kräver förregistrering enligt samma disciplin som
resten. Därför är den INTE gjord — den är Samans beslut.

---

## Fotnot: JSON-felet i poolvyn samma kväll

Saman såg `SyntaxError: The string did not match the expected pattern` i
Poolspel. Orsaken var inte poolkoden utan att backend startades om upprepade
gånger under det här arbetet: `res.json()` på proxyns icke-JSON-svar ger exakt
det meddelandet i Safari. Omgång 2596 verifierades i efterhand svara 200 med
alla 13 matcher.

Felet var övergående, men meddelandet var oanvändbart. `get()`/`getDetail()`
säger nu *"Backend svarade inte med data — servern kan vara nere eller starta
om"*. Reproducerat i preview med ett mockat HTML-svar och verifierat både
före och efter.
