# Mina kuponger, Tester och personlig Idag — leverans av Codex plan del B och C

Datum: 2026-09-13 (Claude). Genomför del B och C i
`overlamning-2026-09-13-modell-ui-plan.md` enligt Samans val av navigation:
**underflikar i Historik** (inte nya toppflikar, inte ersatt Historik).
Ytgränsen står kvar: Historik = 100 % pool, Labb = 100 % odds.

## Vad som byggts

**Historik har tre underflikar** (`historik/HistorikHub.jsx`), toppraden har
fem flikar igen (5 000-test och Max-tester är inte längre egna flikar):

1. **Mina kuponger** (`historik/MinaKuponger.jsx`, öppnas som standard) —
   verkligt spelade kuponger, pågående och avslutade i en lista. Filter på
   period, spelfamilj och status; summeringen (kuponger, pågående, satsat,
   tillbaka, saldo, ROI) följer filtren och räknar pengar bara på komplett
   utdelning. Status per kupong: ej startad · live · avgjord/väntar på
   utdelning · rättad · rättad/utdelning ofullständig · livedata saknas
   (`lib/coupons.js`). Läget i en rad: avgjorda, fastställt bäst, max
   möjligt. "Visa kupongen" öppnar detaljen (`historik/PlayedCoupon.jsx`,
   flyttad ur App.jsx): livekort med matcher, nivåer och chans för pågående,
   officiellt facit match för match och raderna för rättade. Import av radfil
   bakom en knapp. Första API-felet visas som fel med "försök igen", aldrig
   som "inga kuponger" (`historik/usePlayedCoupons.js`).
2. **Tester** (`historik/Tester.jsx`) — katalog med en rad per experiment ur
   `/api/pool/tests` (`backend/app/pool_tests.py`, byggd av gater-raderna):
   syfte, version, status i samma trappa som `cli.py gater`, underlag n/krav,
   öppna kuponger, senaste dokumenterade beslut, "Följ testet". Avslutade
   experiment bakom Arkiv. Inne i ett test: grindkortet (celler = gater-rader,
   beslutstext med datum och dokument) och därunder testets egen vy —
   5 000-test/maxtester/poolopt med **Omgångar** som standard (datum, spel,
   omgång en gång; en kompakt rad per metod × frystid; 20 omgångar först),
   Kuponger (sorterbar tabell) och Jämför metoder som val;
   Standardjämförelsen (`historik/SystemfacitCard.jsx`) och Poolstyrka
   (`historik/PoolmodellCard.jsx`) utbrutna ur gamla HistorikV3.
3. **Facit & prognos** (`historik/HistorikV3.jsx`, slimmad) — produktväljaren
   styr prognosträff och omsättning/utdelning.

**Idag** (C): Mina kuponger överst — pågående med lätt livebild (ingen
chansberäkning) och nya egna resultat inom sju dygn, varje rad klickbar
direkt till kupongen — sedan nästa spelstopp, värden och rörelser, och ett
Tester-kort som bara listar tester som väntar på eller nyss fått beslut
(`lib/tests.js newsworthy`). Idag hämtar `/api/pool/tests` (≈1 s) i stället
för hela `/api/pool/systems`.

**Direktlänkar** (`lib/routes.js`): rutten är vyn. Utan hash startar appen i
Idag; `#/kuponger/12`, `#/tester/ph5/stryktipset/4969/h3/<nyckel>`,
`#/facit/stryktipset`, `#/tester/standard` m.fl. öppnar direkt där, även efter
omladdning. Navigering pushar hash; "← Tillbaka"/stäng backar i webbläsarens
historik. Filtren i Mina kuponger ligger i sessionStorage och överlever
flikbyte. Ingen vy sparas i localStorage.

## Verifierat i drift (desktop 1024 px och mobil 375 px)

- Idag → Mina kuponger-kortet med 3 pågående och 6 nya resultat → klick
  öppnar kupongen (`#/kuponger/67`) med livekort; tillbaka återställer listan
  och filtren. Två klick från Idag till den öppna kupongen.
- Mina kuponger: 59 kuponger, KPI och lista på samma population; mobil visar
  kort, ingen sidscroll.
- Tester: nio rader, ett i arkivet; 5 000-testet i omgångsvy (6 omgångar);
  kupongknapp öppnar exakt kupong med djup hash; stäng backar till testet.
- Direktlänk med omladdning till Stryktipset 4969 h3 Värderader öppnar
  detaljen direkt: 12 rätt, 29 528 kr.
- `tools/kontroll.sh` grönt: backend (inkl. 3 nya tester för katalogen),
  eslint, 55 frontendtester (rutter, kupongstatus/filter/summering,
  testnyheter).

## Kvar och avgränsningar

- Liveläget i listor pollas bara medan fliken är synlig (som förut).
- Scrollposition återställs av webbläsaren vid tillbaka; ingen egen
  scrollminne utöver det.
- Del D (bortfallsdiagnostik, beslut a–e) väntar på Saman:
  `overlamning-2026-09-13-pooltackning.md`.
