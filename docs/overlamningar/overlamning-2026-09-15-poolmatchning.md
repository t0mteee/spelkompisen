# Överlämning 2026-09-15 — säker poolmatchning och första täckningskontroll

## Uppdrag och utgångsläge

Saman: kör rekommendationen efter granskningen av Claudes arbete. Bas:
`66397c1` på MacBook-servern. Claude har levererat Historik → Mina kuponger /
Tester / Facit & prognos, personlig Idag, utdelningsprognos per nivå och
täckningspaketet a–e. Detta arbete ändrar inte UI, systembyggare eller
modellvikter. Modellstatus är fortsatt amber.

## Rättat

- `odds_provider.team_sim` gav full poäng för godtyckliga delnamn. Verifierat:
  Inter = Inter Miami och Barcelona = Barcelona SC. Ett syntetiskt index med
  Inter Miami–Lazio först och korrekta Inter–Lazio därefter gav fel odds.
  Detta bevisar kodfelet, INTE att någon verklig historisk kupong förorenats.
- `POOL_MATCH_VERSION=pool-name-v2`: bekräftade kortnamn har explicita
  poolalias (Leeds, Nottingham, Tottenham, Frankfurt, Sabah Masazir, Hull,
  Mainz). Obekräftade delnamn ger 0 utan fuzzy-fallback; SC bevaras lokalt.
  Truppspärr, kända falska par och trösklar 0,60/0,72 kvar.
- `pinnacle.match_index` kräver exakt en kvalificerad kandidat/orientering.
  Flera träffar, även dubbla identiska rader, avstår. Ingen listordning väljer
  odds. Omvänd hemma/bortaorientering speglar fortsatt 1/2 korrekt.
- `sharp_service` bokför `ambiguous` i befintliga captures, inte `not_listed`.
  Inga odds/snapshots skrivs för avslaget. Närmaste kandidat sparas som förut
  i `pool_match_diagnostic`; extra reason/count/version finns i returdiagnosen,
  men inte som nya kolumner i denna tabell. Täckningsrapporten visar `tvetydig`.
- Rapportens förklarande text beskrev fortfarande det gamla fönstret som
  nutid. Den skiljer nu på insamlingen före/efter 14/9.

Globala `oddset.TEAM_ALIASES` är orörda, liksom V2.2 och målmodellen.
`pit-v4`/`pit-total-v1` behålls inom Samans insamlingsbeslut 14/9 med ny
datumnot i manifest/dokument. Ingen historik bakfylls, inga manuella
databasändringar. 36-timmarsfönstret och annan fuzzy-stavningsmatchning är
oförändrade: detta är en avgränsad säkerhetsfix, inte ett komplett ID-lager.
Konservativa avslag kan öka; lägg bara till nya alias med match-/tidevidens.

## Verifiering

- 15 riktade tester i `test_tackning_ae.py` gröna: tidigare positiva namn,
  Inter/Barcelona, indexordning, flera kandidater, dubbla rader, dubbel
  orientering, oddspegling samt `ambiguous` genom insamling och capturelagring.
- `tools/kontroll.sh`: backendtester, frontendlint och frontendtester gröna.
- Arbete i isolerad worktree på gamla datorn; endast tester, inga
  produktionsinsamlare eller tjänster startade där.
- Driftsättningsrutin: ren server → ff-pull → endast backendens LaunchAgent
  startas om. Pooljobbet läser ny kod nästa ordinarie process/tick.
  Slutlig driftverifiering noteras separat efter leveransen.

## Read-only-täckning 2026-09-15 06:41 UTC

Kommando på servern, före denna fix:

```sh
cd /Users/saman/spelkompisen/backend
.venv/bin/python -B scripts/pool_tackning_rapport.py \
  --sedan 2026-09-14 --out /tmp/pool-tackning-20260915-codex
```

Tre sluträttade Topptipsomgångar: 4332 (14/9 00:14 svensk tid), 4333
(18:59), 4334 (23:59). Giltiga matchobservationer: h24 20/24, h3 14/24,
m20 8/24. Alla giltiga 1X2 hade också giltig total. Bara en komplett omgång
per horisont. Underlaget är för litet och blandar gamla/nya observationer:
4332 stängde före Claudes fix; även senare omgångars h24 är äldre.
Detta är INTE en skattning av förbättringens kausala effekt.

### Nästa prioritet: leverera observationer i tid

För 4333 är m20-as-of 16:39 UTC, giltigt bakåtfönster 16:29–16:39.
Alla åtta matcher hade odds 16:27:50, men de är 70 s för gamla. Nästa
observation 16:43:01 är för sen. 4334 har däremot giltiga odds för alla åtta
vid både h3 och m20 (m20-observation 21:34 före 21:39). Observerad kadens
kring dessa fönster är cirka 15 min mot m20-tolerans 10 min.

4333 h3-as-of är 13:59 UTC, men captures har ett avbrott mellan 10:40:57
och 14:56:00. Orsaken till det avbrottet är inte fastställd. Behöver separat
kontroll mot launchd/poollogg, processlängd och nät-/CDN-fel.

Föreslagen fortsättning:

1. Läs rå hämtningstid **och** CDN-Age kring horisonterna. Avgör om scheduler,
   cachens observationstakt eller ett driftavbrott orsakade luckan.
2. Testa en cachemedveten kadens/fönsterplan innan den ändras. Tätare HTTP-anrop
   ensamt garanterar inte färskare Pinnacle-priser. Ändra inte toleransen för
   att få grön täckning och använd aldrig efterhandspriser före as-of.
3. Följ `ambiguous` och namnrejektioner separat från saknade marknader. Ett
   framtida provider-ID-baserat deduplager kan minska konservativa avslag.
4. Kör planerad täckningsskörd omkring 21/9, dela före/efter-regim och redovisa
   hela parade omgångar. Ingen ny modellpromotion på dessa tre omgångar.

Gamla DB-rader och gamla snapshots är inte sanerade av denna framåtriktade
fix. Om faktisk historisk felkoppling hittas: avgränsad audit, backup,
versionsstyrt rättningsskript och `docs/db-atgarder.md` enligt projektregeln.
