# Testöversikt — första leveransen ur modell-/UI-planen

Datum: 2026-09-13. Fortsättning på
`overlamning-2026-09-13-modell-ui-plan.md`. Saman bad Codex ta ett avgränsat
paket inom återstående session, inklusive commit och dokumentation.

## Genomfört

- `_bench` känner igen `PROB_BASE_CHALLENGERS` som ordinarie PH3-utmanare
  och `POOLOPT_FORWARD_CONFIGS` som aktiv research. Poolopt har fortsatt
  `promotion_eligible=False`; ingen researcharm blir spelrekommendation.
  Äldre och okända nycklar förblir inaktiva. Inga frysta rader ändras.
- `research_groups` delar nu på **produkt × config_key × horisont**.
  Samma visningsnamn slår inte längre ihop gamla/nya modeller eller Stryk
  och Europa. Pengar beräknas fortfarande i backend enligt samma
  tidsriktighets-/utdelningsregler som tidigare.
- 5 000-/maxtester visar aktuell version som standard, med explicit val
  för äldre versioner respektive alla. Arkiv är inte samma sak som sluträttat.
- Samma filter styr kuponglista, KPI och metodsummering. Separata räknare
  för omgångar, kuponger, matchfacit och utvärderbart belopp. En omgång
  räknas en gång även med flera metoder/tider; produkt ingår i identiteten.
- Metodsummeringen är utvikbar. Rubrikerna säger simulerad kostnad,
  simulerat tillbaka och simulerat saldo. Grupp-ROI visas först vid
  `ROI_MIN_N=10`; detta är inte en ny promotionsgrind. Enskilda kupongers
  faktiska testutfall/belopp är fortfarande möjliga att inspektera.
- Listan använder gemensamma `SortableTable`: rubriksortering på desktop,
  sortval på mobil, 20 kuponger först och ”Visa 20 till”. Sortering sker
  före begränsning; filterbyte återställer gränsen till 20.
- NULL i `payout_complete` visas som okänd utdelning, inte ett färdigt
  belopp. Rättnings- och livefunktionerna i övrigt oförändrade.

## Kontrakt för nästa agent

`research_groups[].key` är nu `product:config_key:horizon`, inte
`label:horizon`. Grupperna innehåller dessutom `product`, `config_key`
och `retired`. Backend och frontend ska driftsättas ihop. Frontendens
`lib/forwardTests.js` väljer population och räknar antal; den räknar inte om
kronor/ROI. API:ts summary-fält finns kvar för andra konsumenter.

Detta är visnings-/metadatafixar. **Inga modellparametrar, nycklar,
DATA_VERSION, manifest, radval, signaler eller databasscheman ändrades.**
Ingen bakfyllning, omfrysning eller databasåtgärd behövs.

## Verifiering

- `tools/kontroll.sh`: backendtester, ESLint och frontendtester gröna.
- 11 riktade tester i `test_research_live_overview.py`: aktiva och äldre
  registerposter, pooloptöversikt med riktiga testfrysningar i temporär DB,
  produkt-/versionsisolering, okänd utdelning och sen frysning, liveöversikt.
- 30 frontendtester inklusive fyra nya filter-/populationsregressioner.
- `npm run build` och `git diff --check` gröna.
- Browser-/driftkontroll dokumenteras efter publicering nedan.

## Kvar, tydligt avgränsat

Detta är **del av A**, inte hela den större planen. Fortfarande kvar:

1. Komplettera `gater`: pit-total, korrekta maxversionsnamn, oberoende/parade
   omgångar, verklig beslutsstatus och inget grönt tier-aggregat.
2. Read-only analys av 1X2-/Ö/U-täckning och var rätt rad försvinner.
3. Mina kuponger, gemensam testkatalog/omgångsvy och personlig Idag.

Ingen egen kupong flyttades, ingen ny navigationsstruktur infördes och ingen
ny modell har fått stöd/promoverats med denna leverans. Behåll den större
planens acceptanskriterier, särskilt direktlänkar och mobil detaljvisning.
