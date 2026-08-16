# Överlämning 2026-08-16 — dubbelkuponger v2 och mobilflöde

Detta är den senaste överlämningen för poolbyggaren. Läs först statusdelen i
`docs/plan.md`, därefter denna fil och metodkontraktet i
`docs/kompletterande-kuponger-2026-08-15.md`.

## Vad som hände

Samans faktiskt spelade Stryktips 4966 sparades som kupong 27 (A) och 28 (B).
De bevisade att första dubbelkupongsversionen var för kosmetisk:

- 146 av 256 rader, 57 procent, var exakt identiska;
- B följde A:s båda spiktecken i 230 av 256 rader;
- flera andra favoriter hade nästan samma vikt i båda systemen.

Topptipset Stryk 976 visade ett andra fel. Singelförslagets 256 rader hade
ingen helt fast match, varpå v1 vägrade skapa B. Den spelade raden finns som
kupong 29 och ska inte ändras i efterhand.

## Nuvarande produktkontrakt

Commit `2c6e39b` ersatte v1 med en gemensam portföljbyggare:

- A och B skapas tillsammans; A är därför inte singelförslaget i detta läge.
- Kupongerna har disjunkta spikankare.
- Den andra kupongens ankartecken får finnas på högst 50 procent av raderna.
- Högst 10 procent av de exakta raderna får överlappa.
- Båda håller minst 75 procent av singelförslagets interna
  `träffchans^k × EV`-summa.
- På 13 matcher och högst 512 rader försöker byggaren ge två ankare per sida;
  Topptipset får minst ett per sida även om singelförslaget saknar spik.
- Anrop utan `complementary=true` och den vanliga enkelbyggaren är exakt
  oförändrade. Ingen modellversion eller databas ändrades.

Driftprovet efter `2c6e39b` gav 256+256 rader och 0 procent överlapp för både
Stryktips 4966 och Topptipset Stryk 976. Serverhälsa och båda
portföljsimuleringarna var gröna. Gamla kuponger 27/28 är v1-evidens och får
inte användas som utvärdering av v2.

## Mobilgränssnitt

Den första UI-versionen visade hela A-systemets portföljsimulering, tabeller
och teckenfördelning före jämförelsen och därefter hela B. På 390 px krävde
det en mycket lång bläddring för att ens hitta B.

Mobilflödet är därför ombyggt:

1. Direkt efter **Föreslå två kuponger** visas **Välj scenario A eller B**.
2. Två kort visar fullständiga matchnamn, ankartecken, radantal och kostnad.
3. **Använd kupong A/B** ligger direkt i respektive kort och flyttar till
   kupongen som tidigare.
4. Radöverlapp och korsgardering summeras på en kort rad.
5. Kvalitetsprocenten ligger under **Visa teknisk jämförelse**.
6. Portföljsimulering och alla teckentabeller ligger hopfällda under
   **Fördjupning kupong A/B**.

På mobil staplas A och B; på större skärm visas de i två kolumner. Det vanliga
singelförslaget använder fortsatt gamla `SystemView` utan extra steg.

## Överlämning till Svenska Spel

Svenska Spels officiella **Externa systemspel** är en inloggningsskyddad
filuppladdning. Det finns ingen offentlig direktimport, och webbläsarens
säkerhetsmodell förbjuder Spelkompisen att fylla en filruta på
`svenskaspel.se` från vår egen domän.

Kupongen har därför ett så kort och ärligt flöde som går att bygga i mobilen:

1. **Fortsätt hos Svenska Spel** skapar rätt Egna rader-fil och öppnar rätt
   uppladdningssida i samma användarklick.
2. UI:t skriver ut filnamnet; på SvS väljer användaren **Ladda upp** och den
   senaste filen, granskar och betalar.
3. Knappen är en riktig extern länk, inte en programmerisk popup; det fungerar
   stabilare i mobilwebbläsare. **Bara filen** finns kvar som reserv.
4. Spelkompisen skickar aldrig in eller betalar ett spel och bokför inte
   kupongen som spelad förrän användaren uttryckligen trycker på den separata
   bokföringsknappen efteråt.

Försök inte kringgå detta via privata SvS-endpoints, sessionscookies eller
lagrade inloggningar. Det vore skört, skulle blanda autentisering med vår
server och bryta projektregeln att aldrig lägga spel automatiskt.

## Rättade testkuponger i Historik

Avgjorda bokförda kuponger är inte längre bara summeringsrader. **Historik →
Spelade kuponger → Visa kupong** öppnar en detaljvy med:

- officiellt facittecken och matchnamn i kupongens sparade eventordning;
- antal rader per rättnivå;
- de exakta sparade raderna, sorterade bäst först, med grönt/rött per tecken;
- publicerad utdelning per vinnande rad och möjlighet att visa samtliga rader.

Kupong A/B identifieras via de beständiga `build_kind`-värdena
`byggare-komplement-a/b`, inte genom att tolka ordningen i listan. Det nya
läs-API:t är `GET /api/pool/played/{id}` och gör en eventNumber-join mellan
`pool_played_coupon` och den officiella settlementkanonen. Det omräknade
facitet jämförs dessutom med kupongens sparade `correct_dist`; avvikelse visas
som en varning och får aldrig döljas.

Listan `GET /api/pool/played` skickar inte längre `rows_text` eller
`events_order` till klienten. Livestatus räknas färdigt i backend först, och
de potentiellt 5 000 × 13 tecknen hämtas bara när detaljvyn öppnas. Återinför
inte raderna i listsvaret — det skulle göra Historik långsammare för varje ny
testkupong.

## Kod och verifiering

- Backend: `backend/app/builder.py`, `backend/app/main.py`.
- UI: `frontend/src/AppV3.jsx`, `frontend/src/AppV3.css`, återanvänd
  `SystemView` i `frontend/src/App.jsx`.
- Tester: `backend/tests/test_builder.py` låser Topptips utan basspik,
  disjunkta ankare, 50-procentskorstak, 10-procentsöverlapp, kvalitetsgolv och
  determinism.
- Före v2-drift: 714 backendtester, 12 frontendtester och Vite-bygge gröna.
- Mobilvyn ska verifieras på 390 × 844 efter varje UI-ändring; båda
  fördjupningsblocken ska vara stängda från start.

## Nästa rimliga uppföljning

Spara och följ nya v2-A/B-spel med befintliga `byggare-komplement-a/b` i
historiken. Dra inga slutsatser från enstaka kuponger. När kohorten räcker bör
v2 bedömas både per kupong och som A+B-portfölj: kostnad, utdelning, bästa
träff, om något av ankarscenarierna bar utfallet och hur ofta båda föll på
samma icke-ankrade favorit.
