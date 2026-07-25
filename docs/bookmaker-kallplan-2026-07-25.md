# Bokkällor — konkret genomförandeplan

Datum: 2026-07-25.

Målet är inte många logotyper utan fler **oberoende prismotorer**. Två skins
med samma feed får inte räknas som två bekräftelser av en edge.

## Levererat nu

### Altenar via Ninja Casino

- Altenar är redan inkopplat som `ninjacasinose`.
- Ninja valdes efter jämförelse av elva Altenar-skins: uppmätt 1X2-overround
  var cirka 6,45 procent mot Betinias 9,49 procent.
- Oddset-vyn visar Ninja som `N` under “fler odds” för 1X2, Ö/U och hörnor;
  källhälsan visar list- och deepdelen separat. Ninja-raden visas även när ett
  1X2-pris råkar vara identiskt med SvS, eftersom det är en oberoende feed.
- `GetEvents` ger 1X2 och totalt antal mål. Den publika eventdetaljen
  `GetEventDetails` ger dessutom totalt antal hörnor (`typeId=166`) med
  Altenars markerade huvudlina. Den hämtas nu bara i projektets befintliga
  deep-/snabbfönster och lagras med eventanropets egen observationstid.
- Verifierat 2026-07-25 på Brommapojkarna–Hammarby: huvudlina 9,5 hörnor,
  Över 1,70 / Under 2,05. Alternativlinorna 7,5–11,5 finns i källan men lagras
  inte förrän book-lagret kan bära flera linor utan att blanda tecken.
- Fler Altenar-skins ska inte läggas till: de tillför samma prisfeed och bara
  en annan marginal.
- Ninja ingår som vanlig spelbar mjuk bok i den sharp-ankrade värdemotorn.
  Samma-linje och 45-minutersfärskhet gäller som för SvS. UI-etiketten
  `bekräftat kvar` kräver dessutom tidsbevis: Ninja-priset skapades före
  Pinnacles senaste prisändring och återbekräftades efter den. Ett pris som
  bara är gammalt får aldrig kallas kvarhängande eller skapa signal/notis.

### Smarkets

- Smarkets publika REST-feed är inkopplad för 10/10 ligor och ligger utanför
  `BOOKS`: det är ett oberoende sharp-ankare, inte en mjuk bok att slå.
- Oddset-vyn visar nu Smarkets som `S` bredvid Pinnacle och källhälsan visar
  dess täckning.
- Runtime-signalen använder fortfarande bara Pinnacle. Nästa steg är ett
  **shadow-facit för tvåankarkravet**: logga om varje edge överlever mot både
  Pinnacle och Smarkets utan att ändra dagens tips.

Acceptans före tvåankarkrav i runtime:

- minst 200 stängda 1X2-observationer och minst 28 kalenderdagar;
- båda ankarpriserna var observerade, färska och matchade mot samma match;
- facit redovisar `båda`, `bara Pinnacle`, `bara Smarkets` och
  `ankarna oense`;
- tvåankarkravet måste förbättra precision/CLV utan att slå sönder
  användbar coverage;
- semantisk signalversion bumpas om gaten aktiveras.

## Nästa oberoende soft-källa: Betsson

Betsson/Betsafe/NordicBet använder en gemensam, genuint oberoende feed.
Browsergranskningen 2026-07-25 löste det tidigare headerfelet:

- headernamnet är exakt `brandId`;
- värdet är `sportsbookBrandId` från `/sv/odds` publika inline-bootstrap
  (`6a6d80b9-16ac-4387-a413-244d93a74deb` vid granskningen), inte sajtens
  separata content-brand-id;
- samma bootstrap ger färska `x-sb-static-context-id` och
  `x-sb-user-context-id`;
- `/sb/fe-api/v1/user-context` fungerar cookie-fritt med dessa två ID:n och
  ger resterande publik kontext dynamiskt.

`backend/app/betsson.py` kapslar nu denna bootstrap och bygger de headers som
webbklienten använder. Den lilla `/api/sb/v1/context-details` verifierades
med HTTP 200. Det krävs alltså inte längre någon manuell uppgift från Saman.

Kvarvarande hinder är ett annat: bulkflödet
`/api/sb/v1/widgets/events-table/v2` svarar med CloudFront 403 utanför den
vanliga webbläsarsessionen trots korrekt publik sportsbook-kontext.
Webbläsaren får 200 och visar matcherna, men projektet ska inte exportera eller
återspela browsercookies/WAF-token. Ingen instabil DOM-skrapa ska heller
läggas i launchd. Betsson är därför **header-klar men inte källinkopplad**.

**Omkontroll 2026-07-25 (eftermiddag, Opus 5).** Läget står kvar, men
bootstrapen var i praktiken trasig i drift av ett annat skäl: CloudFront svarar
`content-encoding: br` **även på `Accept-Encoding: gzip`**, och venv:et saknade
brotli-avkodare. httpx returnerade då kroppen som binärt skräp med status 200,
så `fetch_public_context` dog med `ValueError: Betsson-bootstrap saknar
sportsbookBrandId` på en fullt fungerande sida. Testerna var gröna eftersom de
läser en fixtur, inte nätet. `brotli` ligger nu i `requirements.txt` med ett
regressionstest på `httpx._decoders.SUPPORTED_DECODERS`
(`tests/test_betsson.py`) — felklassen gäller alla httpx-källor, inte bara
Betsson. Övriga källor svarar gzip i dag (kontrollerat: Pinnacle, Kambi,
SvS-pool), så ingen annan källa var drabbad.

Efter fixen, med korrekt publik kontext: `/api/sb/v1/context-details` → **200**,
`/api/sb/v1/widgets/events-table/v2` → **403 CloudFront**. Slutsatsen är alltså
oförändrad — det som fattas är en cookie-fri eventväg, inte headers.

När Betsson publicerar en cookie-fri eventväg, eller samma endpoint går att
anropa utan challenge, är återstående implementation:

1. läs liga/event/1X2 med artig timeout och rate-limit;
2. normalisera till samma bookmakerkontrakt som Kambi/Altenar;
3. lägg Betsson i `BOOKS` som **en** feed, aldrig tre skins;
4. spara prisnärvaro, `available`, `last_seen_at` och källhälsa;
5. visa `B` i UI;
6. samla minst två veckor i shadow innan Betsson får skapa en grön edge.

Acceptans: minst 90 procent matchidentitet på överlappande projektmatcher,
inga tysta källfel, ingen stale-price-signal och verifierad oberoende
prisvariation mot både Kambi och Altenar.

## Coolbet

Coolbet är en separat prismotor, men den publika sajten/API-vägen är skyddad
av Imperva. Projektet ska inte lösa, förfalska eller återspela
anti-bot-utmaningar. Därför finns ingen säker klient att bygga nu.

Konkreta beslut:

- Coolbet står kvar som blockerad kandidat, inte som “glömd”.
- Ingen kod eller schemaläggning byggs runt en instabil browser-scrape.
- Om Coolbet senare erbjuder ett publikt API eller ett vanligt JSON-svar utan
  challenge görs samma coverage-/närvaro-/shadowprocess som för Betsson.

## Omedelbart byggbart reservspår: Matchbook

Matchbook är en börs, inte en soft bookie, men dess publika API ger en tredje
oberoende marknadsreferens och faktisk likviditet nära matchstart. Det är mer
ny information än ännu ett Kambi- eller Altenar-skin.

Arbetspaket:

1. bygg `backend/app/matchbook.py` för 1X2-pris och tillgänglig likviditet;
2. polla bara i snabbfönstret nära avspark;
3. spara som separat ankarkälla och visa täckning/ålder i UI;
4. använd endast shadow-jämförelse mot Pinnacle/Smarkets i minst 28 dagar;
5. låt aldrig tunn likviditet bekräfta eller underkänna en edge.

Acceptans: entydig matchidentitet, pris och likviditet från samma
observationstid, explicit stale-/saknasstatus och noll runtimepåverkan innan
det frysta shadow-facitet utvärderats.
