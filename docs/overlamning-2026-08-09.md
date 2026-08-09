# Överlämning 2026-08-09 — settlement, träningsmatcher, jackpot, benchmarkfamilj

**LÄS DENNA FÖRST.** Ersätter `overlamning-2026-08-07-powerrank.md`, som nu
bara gäller som historik. STATUS-blocket i `docs/plan.md` är fortsatt
projektets sanning; det här dokumentet beskriver vad som ändrades i dag och
varför.

Alla fem punkter nedan utlöstes av att Saman såg något fel i appen. Det är
värt att notera som mönster: **fyra av fem fel var tysta** — inget larm, inget
felmeddelande, bara data som saknades eller var uppblåst. Sök efter tysta fel,
inte efter undantag.

---

## 1. Settlementen väntade sex timmar på ett publicerat facit

**Symtom:** "Återigen segar du med att avsluta pool spelen."

**Mätning:** 30 observerade `not_finalized → ok`-övergångar i
`pool_backfill_log`. Median 6,21 h, och **100 % låg över 5,5 h**. Den fasta
backoffen `retry_after_h=6.0` var inte en del av fördröjningen — den *var*
fördröjningen. Median från spelstopp till facit: 8,47 h, medan matcherna
slutar 2–4 h efter spelstopp.

**Två samverkande fel.**
1. Ett försök gjordes ofta *innan matcherna var färdigspelade* — en spelad
   kupong är kandidat från sekunden den bokförs. Det försöket kunde omöjligt
   lyckas men startade klockan som blockerade det försök som hade lyckats.
2. Settlementen låg inne i 30-minuters **basvarvet**, som är budgeterat för
   INSAMLING.

**Åtgärd.** Varje rad i `pool_backfill_log` bär nu sin egen `retry_after`,
härledd ur draw-payloaden vi ändå har i handen (`pool_settlement._retry_after`):
matcher som rullar prövas när de rimligen är slut (sista avspark + 130 min),
en färdigspelad omgång var 15:e minut, tak 6 h. `NULL` = ingen åsikt ⇒ gammal
backoff, så historiken bakfylls inte. `cli._settle_pass()` kör settlement på
varje femminuterstick oberoende av basvarvet (0,15 s i tyst läge, tak
`SETTLE_PASS_MAX_DRAWS = 2` per produkt — radarns 180-sekundersbudget är
orörd).

`pool_played.match_finished()` är nu EN delad definition av "färdigspelad" för
livekortet och omprövningstiden. Skriv aldrig en parallell: det var just en
parallell statuslista som gjorde två straffavgjorda cupmatcher till
"pågående" dagen innan.

**Att göra:** verifiera i drift på en omgång som avgörs EFTER 2026-08-08.
Kvällens två omgångar settlades manuellt eftersom deras loggrader var skrivna
av gammal kod (NULL `retry_after` ⇒ 6h-fallback).

---

## 2. Manchester City och Chelsea saknades i live-radarn

**Symtom:** "varför saknas live på man city och chelseas träningsmatcher? det
finns xg data till båda hos flashscore."

**Orsak:** inte ligafiltret — `WORLD: Club Friendly` fanns i `LEAGUE_NAMES`
och båda matcherna låg i feeden. `_scope_friendlies` → `known_friendly` krävde
namnträff på BÅDA lagen, och båda matcherna föll på **motståndaren**:
`Atl. Madrid` mot Oddsets `Atlético Madrid`, `Johor DT` mot
`Johor Darul Takzim`. City och Chelsea matchade fint — de var bara fel halva.

**Mätning före åtgärd** (dagsfeeden 2026-08-09, 27 träningsmatcher): 15 föll
på spärren, varav **6 hade exakt en Oddset-match som delade ett lag**, noll
tvetydiga.

**Åtgärd.** `_one_sided_friendly`: ett lag räcker när avsparken är känd på
båda sidor och kandidaten är ENTYDIG — samma resonemang som steg 3 i
`_linked_series` (*ett lag spelar en match i taget*). Det avskaffar
aliasjakten på providerns kortnamn, som annars är oändlig. Spärren gick
12/27 → 18/27.

**Viktigt om säkerheten:** spärren styr RÄCKVIDD, inte pris. Ett falskt
positivt kostar ett statistikanrop och en shadowrad — livekortets odds hämtas
i ett separat steg med egen identitetskontroll (`no_canonical_match`).
Regeln får inte lyftas ur sitt anropsställe.

**Verifierat i drift:** Manchester City–Atl. Madrid (min 60, 2–1, xG
2,28/0,58) och Johor DT–Chelsea (min 25, 1–0, xG 0,34/0,24).

---

## 3. Topptipset räknades med Europatipsets jackpot

**Symtom:** "topptipset räknas med europatipsets jackpott och skapar fel roi
prognos."

**Orsak:** ren frontend-state. `CouponPanel` synkade jackpotten bara UPPÅT:

```js
if (payouts?.jackpot > 0) setJackpot(payouts.jackpot)   // aldrig tillbaka till 0
```

Ett byte till ett spel utan jackpot lämnade alltså föregående spels rullpott
kvar. `turnover` (`→ prognos`) bar exakt samma fel.

**Bevisat med före/efter** (samma klickväg, gammal och ny bundle):

| | Europatipset | Topptipset efter byte |
|---|---|---|
| gammal kod | jackpot 2,5 Mkr | **jackpot 2,5 Mkr** på 0,91 Mkr omsättning |
| ny kod | jackpot 2,5 Mkr | jackpot 0 |

Spökpotten var alltså 2,7 gånger större än hela Topptipsets omsättning, och
spelläget visade "jackpot — spela" i stället för "avstå" (70 %).

**Åtgärd.** Effekten nycklas på OMGÅNGEN, inte på värdet, och sätter 0 när
payloaden inte matchar produkten vi står på. Omsättningsöverstyrningen har en
egen effekt som bara beror på omgången — annars raderas en manuell siffra så
fort rullpotten ändras mitt i omgången.

**Mönster att leta efter:** per-omgångsvärden i panelstate utan
omgångsnycklad återställning. Det finns fler paneler.

---

## 4. b1024 borttagen ur Topptipset-familjen

Budgeten är ANTAL RADER, och vad den betyder beror på utfallsrummet:
Topptipset har 8 matcher ⇒ 3^8 = 6 561 rader, så 1 024 rader är **15,6 % av
hela rummet** mot 0,06 % på ett 13-matchsspel. Samma `config_key` mätte två
olika saker.

`pool_system_ledger.benchmarks_for(product)` är nu ENDA källan till vad som
mäts — frysning, championrapport och översikt läser samma familj. Detaljer,
skript, backup och ärlighetsnot (uteslutningen beslutades efter att raderna
var synliga) i `docs/db-atgarder.md` 2026-08-09.

---

## 5. Topptipset Dagens samlades inte alls — TYST sedan 2026-08-04

Det här hittades under punkt 4 och är den allvarligaste av dagens fem.

Topptipset saknar listnings-API och hittas genom nummerscanning
(`_scan_draws`, **80 nummer framåt** från ett hint). `main.py` läste hintet ur
meta (`latest_topptipset` = 4259). `cli.py` anropade `open_draws(product)`
UTAN hint och fick kodens statiska seed **4177** → scanfönster 4169–4248,
medan Dagens omgångar låg på **4256–4259**.

Appen visade omgångarna. Varvet såg dem inte. Inga snapshots, inga
PIT-captures, inga systemfrysningar för Topptipset Dagens på fem dygn. Stryk
(975 mot seed 966) och Extra (1856 mot 1840) låg kvar innanför fönstret och
fortsatte fungera, vilket dolde felet fullständigt.

**Åtgärd.** `Storage.seed_hint()` / `store_seed()` — en definition som båda
vägarna delar. Varvet läser hintet OCH skriver tillbaka det, så det håller
sig färskt även utan API-trafik. Hintet går bara FRAMÅT.

**Eftergranskning:** larmvägen är nu byggd; se punkt 6. Den mäter snapshots,
frysningar och settlement änd-till-änd i stället för enbart scanfönstrets
marginal.

---

## 6. Codex-eftergranskning — åtgärdad 2026-08-09

Fyra luckor hittades trots 607 gröna tester och är nu stängda. Paketet avslutas med 614 gröna backendtester:

1. **Gamla frontend-svar kunde vinna efter omgångsbyte.** `PoolV3` hade ingen
   request-identitet; ett sent payout-svar från föregående draw kunde skriva
   över den nya omgången. Alla laster har nu sekvensvakt, gamla svar
   ogiltigförklaras vid själva klicket och pottdata används bara när både
   `product` och `draw_number` matchar. Det skyddar rubrik, systembyggare,
   systemvy och kupong — inte bara jackpotfältets lokala state.
2. **Ensiding friendly-matchning var för bred.** Regeln använde samma ±2 h
   som tvåsidig identitet och parsefel på starttid föll öppet. Ensidig matchning
   har nu eget fönster ±15 min och kräver två giltiga tider. Tvåsidig matchning
   behåller sin äldre tolerans. Regressionstest täcker två separata matcher
   samma dag och trasig tid.
3. **UI och `kallhalsa` bar en egen gammal källista.** Backendens livepayload
   skickar nu `sources=[flashscore,fotmob]`; UI och hälsorapport läser den
   aktiva radarkonfigurationen. Sofascore finns bara kvar i den retrospektiva
   dubblettjakten, där historiken fortfarande behövs.
4. **Poollarmet mäter nu utfallet, inte scanfönstrets avsikt.** En ren
   hint-marginal hade inte säkert fångat originalfelet — meta-hintet var rätt,
   men `cli.py` ignorerade det. `app.pool_health` kontrollerar därför färsk
   `pool_draw_snapshot` per öppen omgång, komplett benchmarkfamilj efter h3/m20,
   scanhint bakom observerad draw och settlement vars `retry_after` passerats.
   Rapporten är rent läsande och visas i Idag, `/api/health` och
   `cli.py kallhalsa`.
5. **Frontendens React-lint är åter grön.** Tio äldre synkrona stateändringar
   i effekter är borttagna utan att stänga av regeln. Liga- och historikval
   återställer nu sin panel i användarens valhandling, omgångsbundna paneler
   remountas med stabil nyckel och asynkrona svar ignoreras efter cleanup.
   Därmed är rättningen också ett extra skydd mot gamla svar i Sharp, steam,
   CLV, Bomben, lagstyrka och systemhistorik.

Statusblocket överst i `docs/plan.md` och den aktiva delen av
`docs/backlog.md` är uppdaterade till radar v7/två källor och V2.2-manifest
v6. Äldre status ligger kvar uttryckligen märkt historisk.

---

## Kommandon

```bash
cd backend && .venv/bin/python -B -m unittest discover -s tests   # 614 gröna
cd backend && .venv/bin/python -B cli.py pool-tick                # settlement varje tick
cd backend && .venv/bin/python -B cli.py live-tick                # radar
cd backend && .venv/bin/python -B cli.py lanklucka [timmar]       # dubblettjakt
cd backend && .venv/bin/python -B cli.py kallhalsa [timmar]       # live + pool E2E
cd frontend && npm test                                           # 5 gröna UI-test
cd frontend && npm run lint                                       # 0 fel/varningar
cd frontend && npm run build
```

Backend har ingen auto-reload — starta om enligt CLAUDE.md efter ändring.
