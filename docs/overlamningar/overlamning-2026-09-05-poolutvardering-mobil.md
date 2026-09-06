# Poolutvärdering och kupongvisare — 2026-09-05

## Slutsats för Saman

Det finns konkreta svagheter i byggena, inte bara otur: hårda teckenbortval,
koncentrerat radurval och luckor i marknadsunderlaget. Men inte alla tester
förlorade: balanserade 5 000-systemet vid h3 gav 12 rätt och cirka 29 528 kr
simulerat tillbaka. Det är INTE en faktiskt spelad vinst.

### Faktiska sparade kuponger, Stryktipset 4969

| Kupong | Kostnad | Bästa rad | Utdelning | Vad stoppade den? |
|---|---:|---:|---:|---|
| #57 Standard | 512 kr | 9 rätt | 0 kr | Millwalls etta saknades helt; ytterligare tre rätt förlorades i kombinationsurvalet |
| #58 Träffsäkrare | 384 kr | 8 rätt | 0 kr | Brighton X och Crystal Palace 2 saknades; ytterligare tre rätt förlorades i kombinationsurvalet |

”Ytterligare tre” = tecknens oberoende tak minus bästa faktiskt sparade rad.
Det är en efterhandsdiagnos, INTE löftet att samma budget kunde täcka alla
tänkbara kombinationer eller att en viss annan radvalsvikt hade vunnit.

### De stora frysta testerna, samma omgång

| Test | 3 timmar före: rätt / sim. tillbaka | 20 minuter före: rätt / sim. tillbaka |
|---|---:|---:|
| 5 000 balanserat | 12 / 29 528 kr | 10 / 686 kr |
| 5 000 slumpurval | 13 / 747 568 kr | 11 / 1 265 kr |
| 5 000 favoritrad | 9 / 0 kr | 9 / 0 kr |
| 5 000 Max-EV | 10 / 1 861 kr | 7 / 0 kr |
| 20 000 EV medel | 11 / 7 013 kr | 11 / 4 087 kr |
| 20 000 EV högt | 11 / 7 413 kr | 10 / 2 449 kr |
| Matematiskt 39 366 medel | 12 / 29 296 kr | 12 / 29 296 kr |
| Matematiskt 39 366 högt | 12 / 29 296 kr | 11 / 2 244 kr |

Beloppen är ledgerns kontrafaktiska utdelningar med egna vinnarrader i
nämnaren, inte verkliga pengar. 12 rätt är alltså inte automatiskt vinst:
39 366-systemets cirka 29 296 kr är fortfarande cirka 10 070 kr minus.

## Vad vi faktiskt faller på

1. **Små pris-/streckförändringar kan ge helt andra tillåtna tecken.**
   Balanserat h3 hade Brighton X2 och Millwall 1X. Vid m20 blev det 12
   respektive X2. Båda rätta tecken försvann; taket gick från 13 till 11.
   SvS Brighton ändrades bara 2,05/3,65/3,80 → 2,00/3,70/3,90 och
   strecken 66/20/14 → 62/22/16. Millwall 1,87/3,70/4,40 →
   1,98/3,55/4,00, streck 61/22/17 → 58/23/19. Detta är observerad
   instabilitet; vi har inte isolerat en enda orsak genom ombyggnad.
2. **Stor budget innebär inte bred kombinationstäckning.** 20 000-armarna
   hade alla rätta tecken men reducerade bort kombinationerna som gav
   12–13 rätt. Den sena höga armen stannade på 10. Att ha med varje tecken
   minst en gång är ett mycket svagt täckningsmått. Radvis EV-rankning och
   sannolikhetsdämpning premierar liknande scenarier och maximerar inte
   automatiskt sannolikheten att systemet som helhet får en god utdelning.
3. **Datatäckning saknas där den behövs.** 10/13 matcher hade sparad
   sharp-1X2 och huvudtotal vid båda frysningarna. Brighton och Millwall
   saknade båda dessa; Ö/U-regeln kan inte använda en total som saknas.
   Vi vet ännu inte om orsaken är källtäckning, eventlänkning eller
   insamlingstid. Det ska felsökas innan nya trösklar väljs.
4. **Matematiskt system har koncentrationen i spikarna.** Hull–Aston Villa
   spikades 2 i båda armarna, men slutade X. H3-armarna var exakt samma
   kupong (100 % överlapp). Höga m20 spikade dessutom Wrexham, som också
   blev X. 3 spikar + 1 halv + 9 hela är användarens valda struktur, inte
   en garanti eller en bevisat optimal riskfördelning. Ingen sådan regel
   har ändrats nu.
5. **Slumpurval är en kontroll, inte en ny bevisad vinnarmodell.** Tidigare
   etikett ”byggarslump”: `_ph5_control_rows` drar 5 000 unika rader jämnt
   ur balanserade byggarens tillåtna tecken, utan EV-rankning. H3-universum
   var 41 472 kombinationer och facitraden fanns där. En uniform dragning
   på 5 000 har då 5 000/41 472 ≈ 12,1 % chans att innehålla just den raden.
   Den valda fasta slumpseedens träff är därför inte i sig märklig eller
   tillräcklig för promotion. Vid m20 saknades två facittecken även här.
6. **Jämförelser måste hålla vad de lovar.** Max-EV-kontrollen ändrar både
   kandidattecken och rankning via value_weight och sätter jackpot=0,
   medan balanserad arm kan använda jackpot. Den är inte en isolerad
   radvalsablation. Missvisande kodkommentar rättad, fryst algoritm ORÖRD.
   Ny PH5-v4 har bara EN färdigrättad Stryktipsomgång och EN Europaomgång
   med kompletta fyrarmspar. H3/m20 är samma omgång, inte två oberoende
   observationer. Äldre versioner får inte poolas för att skapa skenbart n.

## Nästa arbete, i prioritetsordning (förslag, inte en startad kohort)

1. **Spåra odds-/totalbortfallen per kupongmatch.** Spara/visa internt
   källstatus, matchningsutfall, senaste observationstid och fallbackorsak.
   Kontrollera Brighton, Millwall och tredje luckan i 4969 mot redan
   insamlad rådata. Ingen efterhandsbakfyllning av frysta input.
2. **Reproducerbar urvalsdiagnos över befintlig historik.** Separera
   teckenbortval från kombinationsbortval, täckt sannolikhetsmassa,
   koncentration per match och hur mycket förslaget ändras mellan h3/m20.
   Jämför samma produkt, budget, version och frystid; bootstrap på omgång,
   inte på rader eller på båda horisonterna som oberoende försök.
3. **Utforma ett litet stabilitets-/diversifieringstest.** När befintliga
   gater skördats: högst ett fåtal förregistrerade alternativ. Testa mjukare
   kandidatgräns vid osäkra värdeskillnader och diversifierat urval utan
   återläggning, med gemensam sannolikhetsbas, kandidater och jackpot.
   Mål: systemets chans till utdelning/vinst och kalibrerad risk utöver
   summerad rad-EV. Inga godtyckliga X-kvoter och ingen obegränsad jakt på
   bästa historiska seed. O/U ska vara ett modellunderlag, inte UI-brus.
4. **Beslutsregel före ny promotion.** Håll en tidsmässigt senare del helt
   orörd; redovisa ROI, topprätt, nollutdelningsandel, drawdown och känslighet
   utan största vinsten. Bedöm separat för 8/13 matcher och budget. En
   förändring som bara vinner på dagens kupong ska inte till produktion.

Befintliga gatekrav och stoppregler gäller fortfarande. Detta underlag
motiverar inte att starta ännu en parallellexperimentfamilj direkt.

## Implementerat nu

- Gemensam `CouponOverview` för frysta tester och spelade kuponger:
  tydliga 1/X/2-rutor, rätt utfall inramat, struket med officiellt lottat
  tecken bevarat. Matematik visar inga meningslösa 33/33/33-andelar.
- Odds/streck vid frysning och stopp samt Ö/U finns under respektive
  matchs utvikning. Reducerade andelar ligger där, inte som huvudinnehåll.
- `SystemDetail` öppnas i native dialog: fokus/ESC, bakgrundens scroll
  låses och fokus återställs utan automatisk scroll. Exakta rader visas
  20 åt gången i en utvikning; även 13 tecken ryms på telefon.
- Testlistor blir mobilkort; metodförklaringar fälls ut vid behov.
  Byggarens matchtabell och spelade/exakta radvisare får mobilanpassning.
- 40 000 reducerad pilot borttagen från maxtestflikar, historikgrupper och
  senaste tester. DB och historiskt API bevaras; ingen destruktiv radering.
- X-sammanfattningar, X-viktkolumn och X-skyddsflaggor bort ur UI. Äldre
  byggarmotiveringar filtreras bara vid visning. O/U-logiken orörd.
- ”Lägg i kupongen” gör ingen automatisk layoutberoende scroll längre.
  Bekräftelse med explicit ”Visa kupongen”, bunden till produkt/omgång;
  mobilfält har 16 px för att undvika iOS autozoom.
- Ny läsbar förklaring skiljer saknade tecken från bortreducerad kombination.
- Oriktig formulering ”fördelen bevisad” i byggaren ersatt med försiktigare
  historisk beskrivning; ingen ny modellfördel påstås.

## Reproducera och kontrollera

Bas för granskningen: server/origin `785d1af`. Läsning ur serverns DB i
SQLite `mode=ro` + `PRAGMA query_only=ON`; inga databasåtgärder gjorda.
Fullt numeriskt underlag: `docs/pool-audit-2026-09-05.json`.

```sh
cd backend
PYTHONPATH=. .venv/bin/python scripts/audit_pool_day.py data/stryktips.db --draw 4969
```

Frontend: lint, node-tester och produktionsbygge. Backend: hela unittest-
sviten via `tools/kontroll.sh`. Mobilkontroll i Chrome vid 390 px: fryst
39 366-kupong, ramar, detaljer och 13-teckensrader; dialogens scrollWidth
= clientWidth (375 px med scrollbaren). Ingen insamlare har startats på
gamla datorn; enbart temporär frontendpreview och API-tunnel för UI-test.
Även skapa → lägg i kupongen verifierat vid 390 px: scrollY låg kvar på
2545,5 px och scrollX=0. Explicit ”Visa kupongen” placerade kupongens topp
vid 12 px och tog bort bekräftelsen. Inget markerades som spelat och inget
lämnades in. Sista kontroll/leverans slutförd natten till 2026-09-06.

Leveransväg: fast-forward till samma commit på servern och omstart av
Spelkompisens frontend, därefter HTTP- och versionskontroll. Övriga projekt
lämnas igång. Ingen DATA_VERSION/MODEL_PARAMS-bump: bara presentation,
läsningsskript och en rättad kommentar; numerik och databehandling orörda.
