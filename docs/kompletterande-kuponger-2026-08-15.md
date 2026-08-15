# Kompletterande kuponger — 2026-08-15

## Vad användaren får

Poolbyggaren har ett frivilligt läge **Två kompletterande kuponger** för
Värderader. Samma strategi, reglage och insats används för båda förslagen:

- **Kupong A** är exakt det förslag som den vanliga byggaren skulle ha lämnat.
- **Kupong B** spikar andra matcher än A och garderar varje A-spik i minst
  10 procent av sina rader.
- B har lika många rader och samma kostnad som A.
- UI:t visar spikarna, exakt radöverlapp, B:s interna rankningskvalitet och
  både kostnad per kupong och total kostnad om båda spelas.
- A och B kan var för sig läggas i kupongen. Historiken märker vilken variant
  som valdes.

Det är alltså två fullstora spelalternativ, inte två delar av samma budget.
Läget är avstängt som standard och lägger aldrig in eller lämnar in något
automatiskt.

## Säkerhetsregler

B visas bara när byggaren kan uppfylla samtliga villkor:

1. A har minst en spik.
2. B får minst en spik på en annan match och inga av A:s spikmatcher får vara
   spikar i B.
3. Det valda B-tecknet har minst 40 procents sharp-/fair-sannolikhet.
4. B behåller minst 90 procent av A:s sammanlagda interna
   `träffchans^k × EV`-poäng.
5. Varje A-spik garderas i minst 10 procent av B-raderna.

Om detta inte går visas A oförändrad tillsammans med en tydlig förklaring;
byggaren sänker inte kvalitetsgolvet i tysthet. Kvalitetsprocenten är ett
relativt byggarmått, inte vinstsannolikhet eller historiskt bevisad avkastning.

## Teknisk utformning

`GET /api/system` accepterar `complementary=true` tillsammans med `ev=true`.
Det vanliga svaret ligger kvar på toppnivån som Kupong A. Fältet
`complementary` innehåller metadata och, när reglerna klaras, ett separat
system för Kupong B. Befintliga anrop utan flaggan är oförändrade.

Standardbyggaren fullrankar ett begränsat toppurval. I dubbelkupongsläget
byggs A först med exakt denna gamla väg. Bara sökningen efter B fullrankar hela
det redan begränsade kandidatuniversumet (högst 60 000 rader), eftersom de
garderingsrader som krävs annars kan ha sorterats bort för tidigt.

Ingen databas eller modellversion ändrades. Funktionen påverkar bara ett
frivilligt radval i pool-UI:t.

## Verifiering

- Kupong A jämförs rad för rad med den ordinarie byggaren.
- B måste vara deterministisk, hålla samma kostnad och radantal, ha andra
  spikmatcher, klara 90-procentsgolvet och gardera varje A-spik enligt kvoten.
- Backendens fulla testsvit, frontendens enhetstester och produktionsbygget
  ska vara gröna före drift.
- Riktigt torrtest på Stryktipset 4966 vid 256 kr: A spikade match 4 och 9,
  B spikade match 5, kvalitet 90,0 procent, 50,4 procent exakt radöverlapp och
  cirka 1,3 sekunders lokal byggtid före portföljsimuleringen.

Vid 128 kr hade A fem spikar och ingen annan match klarade ankarkravet. Det är
ett avsiktligt, ärligt tomläge: användaren kan höja insatsen eller ändra
strategin, men får inget konstgjort B-förslag.
