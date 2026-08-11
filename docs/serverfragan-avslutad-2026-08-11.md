# Serverfrågan avslutad 2026-08-11 — molnspåret är stängt

**Till Codex.** Det här avslutar en tråd som stått öppen sedan
`overlamning-2026-08-01-flashscore.md` punkt 2 ("Serverfrågan"). Läs den här
i stället för att öppna den igen — frågan är besvarad, instansen avvecklad och
rådatan sparad i repot.

---

## Vad vi testade och varför

**Frågan:** kan insamlingen flyttas från Samans Mac till en server, så att den
inte hänger på att en laptop är vaken?

Det är inte en driftfråga utan en **källgränsfråga**. Alla våra källor är
gratis och publika, men flera av dem sitter bakom anti-bot-skydd som bedömer
klienten på IP-rykte. En datacenter-IP är en helt annan sak än ett svenskt
hemabonnemang. Projektets källgräns (`CLAUDE.md`) förbjuder uttryckligen att
lösa eller kringgå en sådan utmaning, så om en källa spärrar en molnadress är
det ett definitivt nej — inte ett problem att koda runt.

**Uppställningen:** AWS Lightsail, Ubuntu, `eu-north-1a` (Stockholm),
51.21.134.29. Skriptet `backend/scripts/kalltest_ip.py` kopierades dit och kördes
var 20:e minut via cron.

**Metoden är hårdare än en statuskoll.** Skriptet härmar appens exakta
anropsmönster — samma endpoints, samma headers, browserlik TLS via
`curl_cffi impersonate` för Sofascore — och räknar status 200 som OK **bara om
kroppen också går att tolka**. Det är transportregeln: CloudFront och
Cloudflare svarar gärna 200 med en interstitial eller brotli-skräp.

Bedömningsgrunden var förregistrerad i skriptets huvud: >95 % transport-OK per
källa, minst 72 mätpunkter, minst 72 verkliga timmar — och **en kritisk källa
som faller diskvalificerar IP:n oavsett de andra**.

---

## Resultat

Giltigt mätfönster `2026-08-01T10:58Z` → `2026-08-06T13:40Z`, **2 549
mätpunkter**:

| källa | | OK | av |
|---|---|---:|---:|
| svenskaspel | kritisk | 100,0 % | 365 |
| kambi | kritisk | 100,0 % | 365 |
| flashscore | kritisk | 100,0 % | 361 |
| pinnacle | kritisk | 96,2 % | 365 |
| **sofascore** | **kritisk** | **0,0 %** | **365** |
| fotmob | | 100,0 % | 364 |
| altenar | | 100,0 % | 364 |

**Bedömning: DISKVALIFICERAD** — kritisk källa blockerad.

Sofascore svarar `403` på varje enskilt försök. Det är inte brus och inte en
utmaning vi kan vänta ut: svaret kommer på 79 ms, alltså ett omedelbart
avvisande på IP-nivå. En kontrollkörning **2026-08-11**, tio dagar senare och
efter en omstart som gav maskinen ny nätverkskonfiguration, gav samma 403 —
blockeringen är stabil och knuten till adressen.

**Vad Sofascore kostar oss** (och varför den är märkt kritisk trots att den
kopplades bort ur live-radarn 2026-08-06): den är fortfarande modellens
datarygg. Mätt i databasen 2026-08-10 stod Sofascore för **6 468 av 6 504
xG-rader (99,4 %)** och 2 326 av 3 132 frånvarocaptures. Europaligornas
xG-bakfyllning — den som gjorde PL/Serie A/La Liga/Bundesliga till modelligor —
är 2 891 matcher, 100 % Sofascore, körd 2026-08-07, alltså *efter*
radar-urkopplingen. Att lämna Sofascore är inte en kosmetisk förlust.

Pinnacles 96,2 % passerar gränsen. 503:orna är den dokumenterade periodvisa
Cloudflare-strypningen, inte molnadressen.

---

## DNS-incidenten — och lärdomen som faktiskt betyder något

Instansens namnuppslagning gick sönder `2026-08-06T13:40Z` och läkte först av
en omstart `2026-08-11T12:05Z`. Cron fortsatte hela tiden, så loggen fylldes
med 2 460 rader `ConnectError: Temporary failure in name resolution`.

Uppdelat ser det ut så här:

| | giltigt fönster | DNS-trasigt fönster |
|---|---:|---:|
| svenskaspel, kambi, flashscore, fotmob, altenar | 100 % | **~14 %** |
| pinnacle | 96,2 % | 13,4 % |
| sofascore | 0,0 % | 0,0 % |

Ungefär var sjunde uppslag lyckades — alltså inte ett totalt avbrott utan en
**degraderad** resolver, vilket är exakt det som producerar en trovärdig men
felaktig rapport.

**Defekten i verktyget:** `kalltest_ip.py --rapport` räknar `ok: false` utan
att bry sig om orsaken. Kört på hela filen hade den visat sex friska källor
som fallerande i 86 % av försöken, och den slutsatsen hade varit helt fel.

Det är samma felklass som projektets transportregel och observationstidsregel
finns för: **ett fel hos oss är aldrig en observation om källan.** Verktyget
som skulle mäta källor kunde inte skilja sitt eget nätverksfel från en
blockering.

**Öppen punkt (ogjord):** härda `kalltest_ip.py` så att `ConnectError` med
namnuppslagningsfel räknas som infrastruktur och redovisas separat, aldrig mot
källans OK-andel. Den är värd att göra innan skriptet används på nästa IP —
Pi-spåret hemma står kvar som alternativ — men den gjordes inte nu eftersom
instansen avvecklades.

---

## Konsekvens för projektet

- **Molnspåret är stängt.** Inte "svårt" utan stängt: källgränsen förbjuder att
  kringgå 403:an, och Sofascore är kritisk. Öppna inte tråden igen utan en ny
  fråga.
- **Ett annat VPS lär falla likadant.** Sofascore blockerar datacenterområden
  brett. Hypotesen är oprövad men billig att pröva med samma skript.
- **Pi-spåret hemma** står kvar som det enkla alternativet, och behåller
  hemabonnemangets IP-rykte.
- **Insamlingen ligger kvar på Macen** tills vidare.

---

## Var bevisen finns

- **Rådata:** `docs/kalltest-bevis/kalltest-logg-51.21.134.29-2026-08-11.jsonl`
  — 5 009 rader, hela serien `2026-08-01T10:58Z` → `2026-08-11T12:10Z`,
  hämtad innan instansen togs bort. Filen innehåller BÅDA fönstren; det
  DNS-trasiga (`2026-08-06T13:40:03Z` ≤ `at` < `2026-08-11T12:05:00Z`) får
  aldrig räknas mot källorna.
- **Verktyget:** `backend/scripts/kalltest_ip.py` (i repot, oförändrat).
- **Historik:** `docs/overlamning-2026-08-01-flashscore.md` punkt 2 är den
  ursprungliga öppna tråden, `docs/live-kallor-2026-07-25.md` beskriver
  källgränsen.
