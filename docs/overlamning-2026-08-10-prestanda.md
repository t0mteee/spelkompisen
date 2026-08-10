# Överlämning 2026-08-10 — startvägens prestanda

**Till Codex.** Kompletterar `overlamning-2026-08-09.md` (som fortfarande
gäller för settlement, träningsmatchslänkning, jackpotläckan, b1024 och
Topptipset Dagens). Det här dokumentet handlar bara om varför Oddset-vyn var
seg att starta, vad som mättes och vad som återstår.

Commits: `f40090d`, `921b34e`. Före dem ligger din `24866f4`.

---

## Metodanteckning

Symtomet var "Oddset är segt att starta", med en skärminspelning som stöd.
Inspelningen visade sig vara gjord **21:15**, två minuter innan din
`24866f4` landade **21:17** — den beskrev alltså läget före fixen. Det var
ändå segt efteråt, men av andra skäl än inspelningen antydde.

Hela arbetet nedan är profilerat och mätt, inte gissat. Två mätningar var
direkt vilseledande tills de gjordes om:

1. Jag mätte först `/api/oddset/matches` **utan parametrar** (1,87 MB) och drog
   slutsatsen att `movement.pts` var 72,7 % av nyttolasten. Frontenden anropar
   `compact=true`, som redan strippar `pts` — rätt siffra var 1,06 MB. Mät det
   anrop klienten faktiskt gör.
2. `curl` visade 0,17 s på ett anrop som webbläsaren mätte till 2,5 s.
   Skillnaden var samtidighet, inte endpointen. Enskilda mätningar döljer det
   som gör startvägen långsam.

---

## Vad som var fel — profilerat

### 1. Modellen fittades om vid varje HTTP-anrop

`cProfile` på `matches_payload`: **`attach_model` 1,087 s av 1,331 s (82 %)** —
sju `fit_league` à 80 iterationer plus arton fullständiga läsningar av
resultathistoriken. Per request. Underlaget ändras några gånger per dygn.

### 2. Powerranken låg utanför och blockerade första skärmen

`/api/oddset/powerrank?league=all` hämtas när Oddset-vyn monteras och byggde
**elva egna fits, 2,2 s**, parallellt med matchhämtningen. Det var den som
faktiskt höll spinnern uppe — inte matchlistan.

### 3. Omgångslistningen scannades om vid varje appstart

Kallt `draws?product=topptipset` = **1 616 ms** (nummerscanning × 3 slugs) mot
20 ms varmt, med 5 minuters TTL. Insamlingsvarvet gör samma listning var 30:e
minut utan att dela med sig.

### 4. `/jackpots` hämtades sex gånger på startsidan

`get_jackpot` och `get_guarantees` gjorde varsin identisk hämtning av samma
globala payload, och startsidan frågar för tre produkter. `payouts` var
startvägens långsammaste anrop: **2 293 ms**.

### 5. Fit-cachens TTL gjorde den kall vid varje appstart

Första TTL:n var 300 s. Öppnar man appen efter en paus är cachen alltid kall —
alltså precis det fall som kändes segt. Höjd till 3600 s: datastämpeln
kontrolleras ändå vid varje uppslag (2 ms) och fångar alla tillägg, så TTL:n
skyddar bara mot uppdateringar PÅ PLATS.

---

## Resultat

Kall appstart rakt till Oddset, samma klickväg som Samans:

| | första paint | API-anrop |
|---|---|---|
| utgångsläge | 4 268 ms | — |
| nu, dev-server | 2 626 ms | 43 |
| nu, byggd bunt | **945 ms** | 25 |

Delmätningar: `matches` 1,01 → 0,41 s · `powerrank?league=all` 2,2 → 0,26 s ·
`draws?product=topptipset` 1 616 → 36 ms · `payouts` 1,1 → 0,18 s.

---

## Invarianter du inte får bryta

Det här är de fällor jag gick runt. De är alla dokumenterade i CLAUDE.md, men
de är lätta att missa när man optimerar.

1. **Rör aldrig modellens numerik för att vinna tid.** `_anchor_total` och
   `dc_matrix` står för resten av tiden i `attach_model`, men att ändra deras
   konvergens eller iterationsantal ändrar modellens utdata, alltså
   `model_version`, och nollställer dess facitgrupp. Cachning är gratis;
   numerik är det inte.
2. **Fit-cachens nyckel måste innehålla databasen.** Två tomma DB:er ger annars
   samma fingeravtryck `(0, None, 0, None)` och delar fit. Ofarligt i drift
   (en databas) men det läckte mellan testernas temp-DB:er direkt.
3. **Jackpot-cachen ligger i API-lagret, inte i klienten.** Insamlingsvarvet
   skriver jackpotten till PIT-serien med observationstid, och ett cachat
   värde får aldrig bokföras som en ny observation. `get_jackpot()` utan
   `data` hämtar därför fortfarande färskt.
4. **`UI_HIDDEN_SOURCES` döljer, den avspärrar inte.** Smarkets är borta ur
   API-payloaden (116 kB, 10 %) eftersom den varken är spelbar bok eller
   ankare sedan 2026-08-07. Men spärren i `ANCHOR_SOURCES` står kvar — utan
   den blir den spelbar bok igen (184 av 476 felaktiga flaggor 2026-07-25) —
   insamlingen fortsätter för promotionsregeln, och den INTERNA payloaden till
   WP5-ledgern strippas aldrig. Låst av
   `test_dold_kalla_forsvinner_ur_api_men_inte_ur_ledgerns_payload`.
5. **Gruppcachen för `/api/draws` är borta för poolprodukterna med flit.**
   Slug-cachen ÄR sanningen; en gruppkopia kan skugga en färskare listning från
   varvet. Bomben behåller gruppcachen eftersom den har en egen hämtväg.

---

## Rekommendationer, i prioritetsordning

### 1. Avbryt föregående vys hämtningar vid vybyte (störst kvarvarande vinst)

**Detta är den enda kvarvarande stora posten, och den är frontend.**

Varje endpoint är nu 20–180 ms **ensam** men 1 500–1 800 ms när 43 startar
samtidigt. Appen öppnas på Idag; dess hämtningar (`pool/systems` 160 kB,
`dashboard/oddset` 154 kB, `pool/played` 75 kB, fem `pool/history`) är redan i
luften när användaren trycker Oddset, och Oddsets anrop ställer sig i kö.

Förslag: `AbortController` i `AppV3`:s `get`/`getDetail` (rad ~56/65), med en
controller per vy som avbryts när `view` ändras. Vyerna är redan gatade
(`{view === 'oddset' && …}`), så det som saknas är att stoppa det som redan
skickats. Jag har medvetet INTE gjort den — den rör alla vyers laddningslogik
och Saman hade inte bett om så bred ändring.

**Mät före och efter med samma metod:** kall appstart, klicka Oddset direkt,
räkna anrop och tid till att spinnern försvinner. Sifforna ovan är baslinjen.

### 2. Fundera på om dev-servern ska vara det dagliga läget

`<StrictMode>` dubbelkör varje effekt i dev — det är hela skillnaden mellan 43
och 25 anrop, och mellan 2 626 ms och 945 ms. Samans telefon går mot
dev-servern på 5175 via Tailscale. `vite.config` har nu `preview`-proxy så den
byggda bunten går att köra på 5176. Ta INTE bort StrictMode: den är ett
dev-skyddsnät, och det var den som gjorde dubbelhämtningen synlig.

### 3. Larm när en poolprodukt slutar samlas

Står kvar från 08-09-överlämningen. Topptipset Dagens var tyst utan insamling i
fem dygn. Roten är fixad (`Storage.seed_hint` delas), men det finns fortfarande
ingen väg som säger till. Din `pool_health` i `/api/health` täcker en del —
utvärdera om den fångar just scanfönstrets marginal.

### 4. Leta fler per-omgångsvärden i panelstate

Från 08-09: jackpotläckan mellan produkter var ett `useState` utan
omgångsnycklad återställning, och `turnover` bar samma fel. Frågan att ställa
per panel: *hör det här värdet till omgången eller till panelen?*

### 5. Verifiera settlementens omprövningstid i drift

Också från 08-09, fortfarande overifierad: den kräver en omgång som avgörs
efter 2026-08-08. Förväntad kadens är facit inom ~15 min efter att SvS
publicerar, mot uppmätta 6–8 h före ändringen.

---

## Sådant jag mätte men INTE åtgärdade

- **`_anchor_total` 0,315 s** i varmt `attach_model`. Se invariant 1 — det är
  inte en optimering utan en modelländring.
- **Payloaden 944 kB** i den detaljerade hämtningen, varav `movement`-summeringar
  ~596 kB. Den ligger efter första paint och berikar rader som redan visas, så
  den kostar inte spinnertid. Vill man ändå ned: hämta rörelsesummeringar bara
  för de böcker och marknader listan faktiskt renderar.
- **`payouts?product=topptipset` 0,53 s** — kvarvarande kostnad är `_get_draw`,
  som live-hämtar aktuell omgång. Cachningsbart, men rör samma
  observationstidsfråga som jackpotten: kontrollera vem mer som läser den
  innan du cachar.
