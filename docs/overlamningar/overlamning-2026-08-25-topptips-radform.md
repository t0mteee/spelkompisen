# Överlämning 2026-08-25 — Topptipsets radform och X-backtest

## Kort status

Samans faktiskt spelade Topptipset 4289 (`21XX21XX`) hade fyra X medan hans
384 rader saknade alla 4X-rader. Den exakta kupongen, inte PH5-frysningen, var
utgångspunkten. Ingen spelad kupong, standardprofil eller automatisk
forskningskonfiguration har ändrats.

Två isolerade researchbyggare finns nu i `backend/app/builder.py`:

- `build_topptips_row_shape_system` / `topptips-radform-v1`: samma
  matchsannolikheter och radscore som current men separat medvinnarkappa för
  0, 1, 2, 3 och 4+ X;
- `build_topptips_x_balanced_system` / `topptips-xbalans-v1`: diagnostiskt
  stresstest som fördelar 384 rader enligt marknadens sannolikhet för antal X.

`topptips-radform-v1` kan nu väljas manuellt i ordinarie API/kupongskapare,
men anropas inte av autoinsamlingen och är inte standard. `topptips-xbalans-v1`
är fortsatt en ren offlinediagnos. Den exakta Topptips-snabbvägen i
`_rank_ev_rows` är testad matematiskt likvärdig med den gamla
Poisson-binomialvägen och gör full ranking av 6 561 rader snabb nog.

## Resultat

Förregistreringar:

- `docs/topptips-radform-v1-forregistrering.md`
- `docs/topptips-xbalans-v1-forregistrering.md`

Full rapport: `docs/topptips-radform-v1-resultat.md`; rådata per omgång:
`docs/topptips-radform-v1-resultat.json`.

Modern era gav 1 388 utvecklings- och 597 senare holdoutomgångar. Radform v1
gav 208 mot currents 204 toppträffar, fyra egna/noll förlorade, och +1,34 pp
parad winsoriserad ROI med 90 % KI `[+0,34..+2,35]`. Den bytte bara 9,8 av
384 rader i snitt. Utvecklingsperioden var dock svagt negativ och de fyra
skiljande utfallen är få: starta forward-challenger, byt inte standard.

Full X-balans gav 203 mot 204 träffar och lägre marknadsberäknad träffchans.
Den hade fångat 4289 i final_only-rekonstruktionen men underkänns som generell
standard. Värdevikt 0 gav 225 träffar och högre träffchans men sämre rå ROI;
även den saknade 4X-rad på 4289.

## Rekommenderad fortsättning

1. Lägg `topptips-radform-v1` som en separat 384-raders researchnyckel vid h3
   och m20 från första ännu ofrysta Topptipsomgång. Ingen retrofrysning.
2. Visa den under 5 000-test/research med eget namn trots 384-radersbudget;
   blanda den inte i PH5-v3:s Stryk/Europa-facit.
3. Förregistrera därefter en liten X-svansportfölj som behåller majoriteten av
   current och ersätter en låst andel med X-balansens unika rader. Välj inte
   andelen på den redan öppnade 2024+-holdouten.
4. Efter minst 40 point-in-time-omgångar: jämför parat current, radform och
   svansportfölj på toppträff, winsoriserad ROI, portföljträff och antal
   X-omöjliga facit. Standard får ändras först då.

## Manuell kupongskapare tillagd samma dag

Poolbyggaren visar tre radprofiler för Topptipsets Dagens/Stryk/Extra när
systemtypen är Värderader:

- **Standard** — nuvarande modell; användaren kan fortsätta justera reglaget.
- **Träffsäkrare** — låst värdevikt 0. Historiskt fler toppträffar men
  folkligare/lägre utdelning per träff och inget särskilt skydd mot många X.
  Efter 256/512-kontrollen är den även manuellt valbar på Stryktipset och
  Europatipset; ROI-fördelen är inte säker där.
- **Radform v1 · test** — låst värdevikt 0,5 och exakt den frysta kappakartan
  från rapporten. Den kan inte kombineras med dubbelkupong och är numera
  strikt begränsad till 384 kr.

Standard är fortsatt förvald. Båda challengers märks i API-svaret, kupongen
och historiken; den effektiva värdevikten fångas när förslaget läggs i
kupongen, så ett senare reglagebyte inte kan skriva om dess identitet.
Portföljsimuleringen använder samma X-beroende kappa som radvalet. API och UI
faller stängt om Radform begärs med annan budget än 384. Inget spel lämnas in
automatiskt.

Budgetrobustheten finns i `docs/radprofiler-256-512-2026-08-25.md`. På samma
597 holdoutomgångar gav Radform 171/173 mot Standard vid 256 och 235/236 vid
512; bara 384-resultatet var positivt. Träffsäkrare gav 174/173 vid 256,
225/204 vid 384 och 253/236 vid 512. På 13-matchsspelen gav Träffsäkrare fler
toppträffar i samtliga fyra produkt×budget-celler, men ROI-KI korsade noll.

Den visuella mobilkontrollen hittade också dubbla `product+draw` i ett
Topptips-listsvar. Frontend deduplicerar nu identiteten deterministiskt och
föredrar den öppna varianten; regressionstest finns i `poolSelection.test.js`.

## Verifiering och drift

- 793 backendtester, 13 frontendtester, frontend-lint och produktionsbygge
  gröna efter UI-integrationen.
- Backtestet öppnar snapshoten read-only och sparar hash, kodversion,
  träningskoefficienter, summeringar samt varje omgång.
- Lokal browserkontroll på mobilbredd verifierade profilval, låsta reglage,
  API-bygge, Radform-märkt kupong och X-justerat portföljkort.
- Commit `c6da62b` är pushad till `main` och driftsatt på produktionsservern.
  Servern körde 793 backendtester, 13 frontendtester, lint och
  produktionsbygge grönt. Backend/frontend startades om via sina launchd-
  tjänster och svarade på port 8002/5175.
- Ett skarpt läsande API-prov mot Topptipset 4292 skapade 128 rader med
  `row_model=row_shape_v1`, rätt systemtyp, låst värdevikt 0,5 och den frysta
  X-beroende kappakartan i portföljsimuleringen. Inget spel lades och ingen
  databas migrerades eller skrevs av driftsättningen.
- Budget-/familjeuppföljningen är implementerad i `722a50f`, dokumenterad i
  `688d3e7`, pushad och driftsatt. Lokal helkörning gav 797 backendtester,
  13 frontendtester, lint och produktionsbygge grönt; servern körde de 10
  direkt berörda backendtesterna samt samma frontendkontroller grönt.
- Drift-API verifierade Europatipset 2602 med 256 `Träffsäkrare`-rader,
  Radform 256 som HTTP 400 och Radform 384 som 384 rader. Browserkontrollen
  verifierade Standard/Träffsäkrare på Europatipset, låst värdeviktsreglage,
  tydlig `kräver 384 kr`-text på Topptipset och noll konsolfel.

## Tillägg 2026-08-25 — felaktig 0,8-procentschans i liverättningen

Topptipset 4292 hade en rad med alla åtta aktuella tecken, men chanskolumnen
visade cirka 0,8 %. Det var inte ett skalningsfel: Ninja-parsern godtog varje
Altenar-marknad med `typeId=1` som matchresultat. Providern skapar samtidigt
syntetiska `isAlt`-marknader med samma typ-id för exempelvis **Fjärde målet**;
där betyder utfallstyp 7 **Ingen**, inte X. Vid 3–0 gav den felaktiga tolkningen
Bodø/Glimt 21 % och X 73 %, och liknande nästa-mål-priser förstörde hela
kupongchansen.

Parsern accepterar nu bara den observerade kanoniska liveidentiteten
`sportMarketId=70472`, `typeId=1`, `isAlt≠true`, och endast utfall 1/2/3 som
1/X/2. Saknas den faller liverättningen vidare till Pinnacle eller den tydligt
märkta ställningsmodellen. Ett komplett felmärkt pris är aldrig en godkänd
reserv. Regressionstestet innehåller den verkliga Bodø/Glimt-strukturen med
`Fjärde målet` och `Ingen`.

Liverättningen redovisar dessutom två skilda mått:

- **fastställt bäst** — rätt i avslutade matcher;
- **om det slutar som nu** — bästa rad mot samtliga aktuella ställningar.

Procentkolumnen heter nu **chans att nå** och är uttryckligen oddsbaserad;
den är inte andelen rätt just nu. Backendens nya fält är `current_known`,
`current_best` och `current_best_rows`. Ändringen påverkar bara visningen av en
redan inlämnad kupong, aldrig systembyggaren, facit eller automatiska spel.
