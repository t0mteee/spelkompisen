# Modellbeslut och enklare pool-UI — granskning och föreslagen plan

Datum: 2026-09-13. Granskad drift: `dba6f16`, MacBook-servern
`192.168.50.100`. **Plan, inte genomförd implementation.** Saman bad om
bedömning och tillvägagångssätt som Claude kan ta över. Arbetsordningen
nedan är ett förslag; den ersätter inte godkänd backlog eller manifest.
Ingen modell, testversion, insamling, databas eller tjänst har ändrats.

## Slutsats

Ja, vi kan förbättra produkten nu. Det behövs inte fler testflikar innan
befintliga tester blivit begripliga. Gör två sammanhängande arbetsspår:

1. Rätta testernas identitet och beslutsöversikt, granska datatäckningen och
   använd redan insamlade omgångar för att förstå modellens bortval.
2. Separera **Mina kuponger** från **Tester**. Gör Idag till en personlig
   arbetsöversikt, inte ännu en forskningsrapport.

Vi har mer data, men hundra testkuponger är inte hundra oberoende omgångar.
Nya versioner får inte slås ihop med gamla för att nå en beslutsgrind.
UI-arbetet kan levereras utan att invänta modellgrindarna.

## 1. Vad finns faktiskt för beslutsunderlag?

Avläsning 13 september, huvudsakligen `cli.py gater` kl. 13:25:50 UTC,
kompletterad med read-only SQLite-frågor och visning av driftens 5 000-sida.
Siffrorna är en ögonblicksbild, inte löpande räknare.

| Spår | Observerat | Vad vi kan säga/göra |
|---|---|---|
| Bokförda egna kuponger | 59 totalt, 56 sluträttade, 3 öppna vid avläsningen | Det finns ett riktigt personligt facit att göra lättåtkomligt. Separera pengar från simuleringar. |
| PH3, Topptipset-familjen | Champion: 29 rättade omgångar vid 180 min, 30 vid 20 min; bästa utmanarnas jämförelser 29/30, FDR ej passerad | Nära 40-grinden, men varken antal eller stöd räcker för promotion nu. Kontrollera parade antal per kandidat, inte bara championens total. |
| PH3, Pinnacle som sannolikhetsbas | 28 frysningar och 26 ROI-rättade per horisont | Ett befintligt konkret modellspår. Kontrollera parade, tidsriktiga omgångar mot championen inför beslut. |
| Pooloptimerare, tre 256-radersarmar | 26 omgångar, 156 frysningar, 144 ROI-rättade kuponger totalt; 24 rättade omgångar per arm/horisont | 20 ordinarie Topptipsomgångar + 2 Extra + 2 Stryk. Inte 144 oberoende försök. 40 parade krävs för att ens nominera PH3-utmanare; inte direktpromotion. |
| 5 000-test, aktiva nycklar | 48 kuponger, 40 rättade; **2 Stryktips- och 3 Europaomgångar** per metod/horisont | Bra diagnostik, för tunt för vinnarmodell. Fyra metoder × två tider mångdubblar kupongantalet, inte evidensen. |
| Matematiskt max och reducerat max, aktiva versioner | Vardera 24 kuponger, 20 rättade; samma **2 Stryk + 3 Europa** per arm/horisont | Jämför konstruktion och bortval, inte säkra ROI-rankningar. |
| Ö/U-syskonserien `pit-total-v1` | Ordinarie Topptipset: alla 8 totaler på 2/22 observerade omgångar vid 180 min och 8/22 vid 20 min; 1/9 vid 24 h | Täckning är flaskhals. Detta räknar observerade omgångar, inte en verifierad uppsättning sluträttade/parade träningsfall. Kravet är 40 kompletta. |
| Radar, aktuell v12 | 122/200 prissatta och avgjorda; 9/30 dygns spann, 11/20 matchdygn | Över-ROI ungefär +0,06 %, KI90 cirka −14,3 till +15,1 %. Inte visad lönsamhet. |
| V2.2 | 135/149/146 kvalificerade avgjorda matcher vid 24 h/180 min/20 min; krav 300 per horisont, 42 dygn och per-liga-krav | Fortfarande identitetskontroll: V2.2 = sharp. Det är inte en färdig tränad egen modell som bara väntar på en UI-knapp. |
| Poolstyrka | 43/41/48 avgjorda per horisont mot 300; 0/3 ligor över representationskravet | Inte redo för modellbeslut. |

Sharp-CLV har redan positiva grupper, bland annat MLS, Allsvenskan,
Superettan och Belgien 1X2 i aktuell rapport. Det är stöd enligt respektive
**marknadsbaserade close-EV-grind**, inte bevis för egen målmodell eller
garanterad faktisk spel-ROI. Conference League, La Liga och Danmark har
inte motsvarande stöd. Visa gruppskillnader, inte ett globalt grönt betyg.

PH4 Topptipset har redan utvärderats 2 september: streck/streckrörelse gav
inte stöd för förbättring över ren Pinnacle; promotion NEJ. Att dataräknaren
nu säger 102/40 är inte ett nytt positivt resultat. Konvergensreservationen
står i befintlig backlog. Gör inte om analysen tills den råkar bli positiv.

### Ett konkret exempel på varför summeringarna behöver förbättras

Driftens 5 000-sida visar Slumpurval vid 180 min: 773 869 kr simulerat tillbaka
på 60 000 kr, cirka +1 190 %. En enda kupong, Stryktipset 4969 den 5 september,
står för cirka 747 568 kr — ungefär 97 % av återbetalningen.
Det är en verklig observation i testet men inte tillräckligt för slutsatsen
att slump är överlägsen. Redovisa största vinstens bidrag och känslighet
utan största omgången som diagnostik, inte som ersättning för primärmåttet.

Samtidigt fick Värderader i Europatipset 2606 den 9 september 13 rätt vid
båda tiderna och cirka 19 032 kr simulerat tillbaka per kupong. Vi bör alltså
inte utgå från berättelsen att byggaren aldrig lyckas. Dessa två frysningar
är fortfarande samma omgång, inte två oberoende fullträffar.

## 2. Verifierade brister att rätta först

### P1: Nya konfigurationer klassas som avslutade legacy-tester

`backend/app/pool_system_ledger.py::_bench` (kring rad 771) saknar
`POOLOPT_FORWARD_CONFIGS` och `PROB_BASE_CHALLENGERS`. Okänd-nyckel-fallback
ger `retired=True`, `research=False`, `method=legacy`.

Effekt: pooloptöversikten säger noll aktiva tester trots 156 sparade.
Pinnacle-utmanaren felmärks också i metadata. Insamlingen finns; det här är
inte belägg för att 156 kuponger gått förlorade. PH3:s championrapport läser
via `benchmarks_for` och innehåller fortfarande sannolikhetsbasutmanaren.

Åtgärd: komplett gemensamt konfigurationsregister för insamling och
presentation, utan att ändra befintliga nycklar, frysta rader eller modell.
Behåll säker legacy-fallback för verkligt okända nycklar. Researcharmar får
inte bli `promotion_eligible` bara för att de nu identifieras korrekt.

Test: samtliga aktiva konfigurationsnycklar ska ha rätt aktiv/research/
familj/metod-status; samtliga pensionerade ska förbli pensionerade. Lägg
regression för poolopt och `dr1-b256-medel-sharp` samt översiktens antal.

### P2: Beslutsöversikten har ingen fullständig beslutsmodell

`backend/app/gater.py::_research` visar hårdkodad status `samlar`, inget
numeriskt krav och kupongantal snarare än oberoende omgångar. Max-spåren
namnges v1 trots aktuella v2, och avslutade max40 visas som samlande.
`pit-total-v1` saknas helt trots att första data finns och backlog uttryckligen
kräver dess grind. `_sharp_clv` kan dessutom märka hela tiern grön, i strid
med regeln om beslut per signalgrupp.

Åtgärd: återanvänd respektive manifests definition och visa separat:
**samlar → tillräckligt underlag → granskat (stöd/ej stöd) → infört/avslutat**.
Visa version, rättade oberoende omgångar, parade antal, bortfall, senaste
beslutsdatum/datastopp och nästa förregistrerade prövning. Uppfinn inga
gemensamma trösklar för olika experiment. Grön aggregate-tier ska inte vara
ett promotionsbeslut. Visa inte en redan granskad PH4 som ny skördemöjlighet.

Dokumentationsdrift: plan.md säger fortfarande 60 radardygn. Koden beskriver
Samans beslut den 18 augusti: 30 dygns spann OCH 20 matchdygn, utöver 200
prissatta/avgjorda. Rätta dokumentationen, inte grinden för att få snabbare stöd.

### P2: Summeringar och listor beskriver olika populationer

`frontend/src/historik/ForwardTestV3.jsx` visar `data.groups` före filtren;
filtreringen påverkar kuponglistan men inte summeringen. `research_groups`
i backend grupperar på etikett/metod + horisont, över produkter och
testversioner. Det kan fungera som tydligt märkt arkivbokföring, men inte
som jämförelse av aktuell modell. Sidans KPI gäller samtidigt aktiva nycklar.

Observerat i browsern: 48 aktiva kuponger i toppen, 104 listade längre ned,
och texten ”56 avslutade”. Den sista siffran kommer ur `retiredCount` —
den betyder **äldre testversion**, inte 56 färdigrättade kuponger.

Åtgärd: ett filterkontrakt för KPI, summering, lista och export. Aktuell
version som standard, arkiv via explicit val. Skilj testversionens livscykel
från kupongens match-/rättningsstatus. Topptipsets familjegruppering ska
fortsatt följa `family_of`, inte blanda Stryk/Europa med åttamatchsspelen.

## 3. Modellarbete: vad gör vi nu, utan att jaga senaste facit?

**Först diagnostik på befintliga frysta kuponger**, även vinnare. Ingen ny
10 000-konfigurationssökning på samma sluttest. Rapport per produkt,
modellversion och horisont, jämförelser på samma omgångar:

1. **Källdata:** skilj saknad Pinnacle-matchning, missad capture/tidsfönster,
   observerad 1X2 utan total och ogiltig total. Mät per match/ligatyp/tid.
   `total_eligible=0` och ingen rad är olika felklasser. Följ upp tidigare
   Brighton/Millwall-fynd och om senare 20-minuterscapture faktiskt löser dem.
   Ingen bakfyllning med slutodds eller dagens priser i forwarddata.
2. **Var förloras rätt rad?** Separera att rätt tecken saknas redan i
   kandidatunderlaget, att rätt kombination faller bort vid reducering,
   och att kupongen träffar men utdelningen inte täcker kostnaden. Redovisa
   hur många högsannolika tecken som helt saknar täckning och hur många
   rader som samtidigt faller vid en missad spik. Alla 1/X/2, inte X ensamt.
3. **Sannolikhet eller konstruktion?** Bedöm prognoser mot samma tids
   Pinnacle med logloss/kalibrering, och byggarens urval mot jämförbara
   referenssystem med träffar, vinstnivåer, kostnad, återbetalning och ROI.
   En bra prognos kan användas av ett för koncentrerat system; en storvinst
   kan uppstå med en dålig prognos. Håll frågorna isär.
4. **Robusthet:** rapportera största omgångens andel av vinsterna,
   förlustsviter och budgetskillnader. Bootstrap med omgång som block;
   flera tider/metoder på samma matcher är beroende. Diagnostiska delgrupper
   är hypoteser, inte ett sätt att välja bort förlustomgångar.

Mest relevanta kommande modellbeslut:

- Skörda först befintlig 256-kr Pinnacle-utmanare och poolopt när respektive
  parade 40-grind nås. Poolopt har separat nominering och därefter PH3,
  inte en genväg till standard. Följ också den beslutade 120-omgångsgränsen.
- Prioritera Ö/U-täckningen. Testa sedan om totalen tillför information om
  oavgjort utöver X-oddset enligt eget manifest. Nuvarande skydd är en
  riskregel, inte verifierad modellförbättring. Ingen ny ”X-viktat”-UI-text.
- Om bortfallsanalysen visar koncentrationsproblem: förregistrera en liten
  kandidat med kontrollerad tecken-/kombinationstäckning, samma budget och
  sannolikhetsbas. Inte samtidigt ny xG-modell, ny EV-vikt och ny radprofil.
- Matematiska maxets tre spikar är ett användarvalt konstruktionskrav,
  inte empiriskt bevisad optimalitet. Mät var missarna uppstår, men ändra
  inte formkravet utan Samans beslut. Reducerade 256/512-system kräver egna
  jämförelser; resultat på 5 000/39 366 rader kan inte direkt överföras.

Slutsats: behåll nuvarande produktion tills befintliga kandidater fått stöd.
Det betyder inte att allt arbete står still — bättre täckning, analyser och
UI är motiverade nu. Skapa inte nya versioner enbart för etikett-/UI-fixar.

## 4. Föreslagen UI-struktur

Detta är en avsiktlig ändring av nuvarande navigationskonvention, inte bara
ny färg/CSS. Vid godkänd implementation uppdateras CLAUDE.md samtidigt.
Pooldata ska fortsatt inte spridas till Oddset-Labb.

| Plats | Frågan den ska besvara | Första vyn |
|---|---|---|
| Idag | Vad behöver jag se/göra nu? | Mina pågående kuponger, nästa spelstopp, nya resultat, få relevanta signaler |
| Poolspel | Vilken kupong vill jag skapa? | Befintlig analys/byggare; tydlig ”Visa min kupong” efter tillägg |
| Mina kuponger | Vad har jag faktiskt spelat och hur går det? | Pågående / Avslutade; import som knapp, inte lång förklaring |
| Tester | Vilka experiment körs och hur går varje omgång? | Kort testkatalog, inte hundratals konfigurationsgrupper |
| Oddset / Labb | Matcher/signaler respektive oddsutvärdering | Behåll ytgränsen; inte huvudfokus i detta paket |

### Mina kuponger

Idag → klick på egen kupong → liverättning. Historikens egna kuponger finns
redan under ”Dina spelade kuponger”, men de delar i dag en lång sida med
autopool, prognoser, kalibrering och modelltester.

En kompakt rad/kort: datum, spel/omgång, egen insats, status, aktuellt eller
slutligt rättningsläge, återbetalning/resultat när känt, ”Visa kupongen”.
Insats/återbetalning avser verkligt bokförda kuponger, aldrig simulerat
kapital. Filtrera period, produkt och status. Summeringen följer filtren.

Statusar: ej startat, live, matcher klara/utdelning väntas, rättad, datafel.
Okänd utdelning är inte förlust. Bekräftat facit, livebild och prognos är
olika saker. Första API-felet får inte maskeras som ”inga kuponger”; granska
`PlayedPanel` som i dag kan falla tillbaka till en tom lista vid första fel.

### Tester

En katalog med en rad per experiment: Standardjämförelsen, 5 000,
Matematiskt max 39 366, Reducerat max 20 000, Optimerare 256, Poolstyrka.
Äldre/avslutade experiment bakom ”Arkiv”, ingen återkomst för 40 000-piloten.
Varje rad visar kort syfte, aktuell version, öppna kuponger, rättade
omgångar/krav, senaste resultat/beslut och en knapp ”Följ testet”.

Inuti testet: **Omgångar** som standard, **Jämför metoder** som separat val.
Visa datum + spel + omgång en gång, därefter kompakta rader för metoder/tider.
Högst 20 omgångar först. Filter över både summering och lista. Ingen vägg av
KI, förklaringar och arkivsaldo innan användaren kommer till kupongerna.

Jämförelsevyn visar simulerad kostnad/återbetalning tydligt, antal oberoende
omgångar och version. Kronor ska gå att inspektera även i små serier;
modellbetyg/ROI-stöd ska fortsatt följa experimentets minimiunderlag.
Undvik ”Spelat” som ensam rubrik för simulerade pengar.

### Samma kupongvisare, olika bokföring

Återanvänd befintlig `CouponOverview`/detaljkomponenter. Egen kupong har
spelat-ID; testkupong har exakt `(product, draw_number, horizon, config_key)`.
En gemensam UI-komponent får inte blanda deras settlement- eller pengarlogik.

- Först matcherna och valda 1/X/2 med inramat rätt tecken; missa aldrig
  skillnaden mellan reducerat urval och matematiskt system.
- Live: kort ”max möjligt / avgjorda matcher”; mer avancerade nivåantal
  och chans bakom ”Detaljer”. Pott är inte personlig vinst/utdelning.
- Odds/streck som sparades vid kupongens tid bakom ett utvikbart avsnitt,
  med käll-/observationstid och tydligt saknat värde. Import utan historisk
  snapshot får aldrig låtsas ha odds från speltillfället.
- Råa tusentals rader laddas endast på begäran och sidindelas.
- På mobil: helskärmsdetalj med tydlig tillbaka-knapp, ingen bred tabell i
  liten modal med både horisontell och vertikal intern scroll.

### Idag

Prioritering: (1) driftfel som kräver åtgärd, kompakt, (2) **mina pågående
kuponger**, (3) nästa spelstopp, (4) nya rättade egna resultat, (5) ett fåtal
aktuella värden/rörelser, (6) endast viktig testnyhet, exempelvis redo för
utvärdering. Djuprapporter hör inte hemma här.

Nu ligger egna kuponger efter värden/rörelser, länken går till hela Historik
och data hämtas med `live=false`. En lätt, cachad liveöversikt behövs för
aktuellt läge — inte chansberäkning eller fulla testrapporter på startsidan.
`DashboardV3` hämtar dessutom full `/api/pool/systems` för systemkortet;
ersätt med liten sammanfattning/lazy load inom denna etapp.

## 5. Leveransordning och acceptans för Claude/Codex

### A. Sanna räknare och datatäckningsrapport — litet avgränsat paket

- Rätta konfigurationsregistret, labels/versionsstatus och filterkontrakt.
- Gör gater komplett och skilj mätbar volym från faktiskt modellbeslut.
- Read-only rapport över 1X2-/Ö/U-bortfall och deras orsaker; jämför samma
  omgångar vid 180/20 min. Fixa inte provider-/tidsregler utan separat
  bedömning av om den observerade serien ändras.
- Testa aktiva/äldre/okända nycklar och populationsräkning. Ingen migration
  eller omfrysning behövs för rena register-/visningsrättningar.

### B. Mina kuponger + testkatalog + exakt detalj — största användarnyttan

- Bygg först ett komplett flöde för egna kuponger och 5 000-testet; använd
  samma komponenter för max/övriga tester. Undvik en parallell ny app.
- URL-baserade direktlänkar till kupong/test, tillbaka återställer filter och
  scroll. Bevara Idag som normal start; explicit direktlänk är ett särskilt
  kontrakt som dokumenteras/testas. Ersätt fördröjd `scrollIntoView`-navigering.
- Återanvänd `SortableTable`, dess mobilordning och befintliga datakällor.
  Inför inte egna sorteringskopior. Ladda endast aktuell vy och öppna detaljer.

### C. Idag som personlig översikt

- Flytta upp egna kuponger, visa färskt rättningsläge och nya resultat.
- Testnotiser bara när något ändrats eller ett beslut behövs.
- Bevara progressiv laddning och skydd mot sena svar, single-flight och
  pausad polling i dold flik. Tomt, laddar, gammalt och fel är olika lägen.

### D. Skörd och nästa modellkandidat

- Genomför bortfalls-/koncentrationsdiagnostiken i avsnitt 3.
- Vid befintlig grind: kör förregistrerad parad rapport, besluta stöd/ej
  stöd, dokumentera data-cutoff, artefakt och nästa steg. Stoppa spår vid
  deras beslutade slutkriterium; lägg inte bara nya på toppen.
- Ny kandidat först utifrån diagnos och godkänt manifest. UI-färdigställande
  ska inte villkoras av att något experiment visar positivt resultat.

Acceptans före UI-driftsättning:

1. Egna öppna kupongen nås på högst två klick från Idag; exakt testkupong
   på högst tre från Tester. Direktlänk, omladdning och tillbaka fungerar.
2. 320/390/768/1440 px: tydligt datum, spel och status; ingen sidscroll i
   huvudflödet; läsbara knappar, synligt fokus och text utöver statusfärg.
3. Filter och sammanfattning visar samma population. Aktiva och äldre
   versioner blandas inte tyst; rättad kupong ≠ pensionerat experiment.
4. Validera live, slut före utdelning, fullständigt facit, bortfall, tomt
   arkiv och API-fel. En request för tidigare val får inte skriva över nytt.
5. Kupongens rader, kostnad, odds/streck och facit identiska före/efter
   UI-flytten. Ingen omskrivning av historik eller modellfingeravtryck.
6. `tools/kontroll.sh` plus browserkontroll av verkliga exempel och mobil.
   Commit/push/driftsätt enligt serveröverlämningen, aldrig start på gamla
   datorn. Uppdatera status, backlog och UI-konventioner när arbetet godkänts
   och respektive etapp faktiskt levererats.

## 6. Handover och reproduktion

Denna granskning gjordes från ren worktree på aktuell `origin/main`.
Gamla huvudkatalogen på arbetsdatorn var en äldre gren och användes inte
som sanningen för drift. Serverns Git var rent vid kontrollen.

Läs först CLAUDE.md, docs/plan.md, docs/backlog.md och serveröverlämningen.
Relevanta filer: `pool_system_ledger.py`, `gater.py`, `pool_dataset.py`,
`live_signal_ledger.py`; frontend `AppV3.jsx`, `historik/HistorikV3.jsx`,
`historik/ForwardTestV3.jsx`, `App.jsx` (`PlayedPanel`, kupongdetaljer).

Avläsning: serverns `backend/.venv/bin/python cli.py gater` och read-only
SQLite URI `file:data/stryktips.db?mode=ro`. För aktuella testnycklar används
modulens konfigurationstupler, inte LIKE-gissningar. Gruppera ledger på
produkt + horisont och räkna distinkta draw_number med känt roi; inför
beslut krävs dessutom manifestets parade/timely/eligibility-filter.
Totalseriens preliminära kompletthet: gruppera produkt + omgång + horisont
för `pit-total-v1`, räkna åttamatchsfall där count=8 och sum(total_eligible)=8.
Denna diagnostik är inte automatiskt samma sak som ett färdigt träningsurval.

Inga nya tester, nya tjänster, modelländringar eller UI-ändringar har
levererats med detta dokument. Nästa föreslagna praktiska arbete är A,
följt av B; användaren tar ställning till upplägget först.
