# Spelkompisen — färdplan

## STATUS (2026-11-08 — pool-name-v14 apostrofer och Instituto mot Newell's; 2026-11-07 pool-name-v13 Sarmiento mot Tigre; 2026-11-06 V2.2 v10 och poolstyrkan avslutade per 2026-11-05 09:30Z; Betfair Exchange och BetInAsia via Betexplorer som mätta referensböcker; bet365 via Betexplorer som referensbok i Oddset-vyn; Pinnacle spärrar Sverige; Smarkets och SBOBET ankrar värdemotorn (anchor-v1); SBOBET ny referenskälla och Smarkets synlig igen; 2026-11-05 Big 9: valet hög EV i appen; egen kupong i appen; Big 9 mäts även på 512 kr från SP96 554; 2026-11-04 Big 9 bara fulla system (ATG:s enskilda utfall) från SP96 554; Big 9 i appen (Poolspel → Big 9); pool-name-v12 LD Alajuelense; pool-name-v11 Slavia/Sparta Prag; livekassans alias Sporting Lissabon och Manchester United/Roma; 2026-11-02 Altenar borttagen som källa; 2026-10-25 livekassans resultat för matcher över svensk midnatt; 2026-10-24 Big 9 från ATG på facitsidan, SP96 mäts som Big 9; 2026-10-18 livekassan till 0 kr, byggaren och poolvarianterna städade, pool-name-v10; 2026-10-16 färre poolnotiser; 2026-10-15 livesidan för poolspelen)

Projektets aktuella kontrakt står här; historiska statusblock finns i
`docs/status-historik.md`. Senaste överlämning:
`docs/overlamningar/overlamning-2026-11-06-v22-poolstyrka-avslutade.md`.

**Nytt 2026-11-08:**
- **pool-name-v14** (beslut driften-2026-11-07-topptipset-4436-instituto-newells-alias,
  val 0): poolmatcharen tar bort apostroferna ´ (U+00B4) och ’ (U+2019) före
  jämförelsen, som ' redan togs bort (`odds_provider._POOL_APOSTROPHES`, bara i
  `_norm_team`; Oddsets globala `norm_team` är orörd), plus kontextaliaset Instituto de
  Cordoba → Instituto, BARA när SvS-motparten är Newells Old Boys. Topptipset 4436 match 8
  (Instituto de Cordoba–Newell´s Old Boys, 2026-11-08 01:00Z) fick ingen Pinnacle och
  vakten larmade `pool_pinnacle_saknas`: "Instituto – Newells Old Boys" vid exakt avspark
  gav sidopoäng 0,0/0,97 (SvS skriver "Newell´s"). Med ändringen länkas paret på nivå A.
  Instituto mot andra motparter prövas som förut (v8:s nivå D kräver exakt motpart).
  Pinnacle spärrar Sverige, så ändringen verkar först när Pinnacle svarar igen; larmet
  kan återkomma av spärren. Inget bakfyllt.

**Nytt 2026-11-07:**
- **pool-name-v13** (beslut driften-2026-11-07-topptipset-4433-sarmiento-alias, val 0):
  kontextaliaset Sarmiento → Sarmiento de Junin, BARA när SvS-motparten är Tigre.
  Topptipset 4433 match 2 (Tigre–Sarmiento, 2026-11-07 01:00Z) fick ingen Pinnacle och
  vakten larmade `pool_pinnacle_saknas`: "CA Tigre – Sarmiento de Junin" vid exakt avspark
  gav sidopoäng 0,0/0,0. Sarmiento ensamt är tvetydigt (Junín och Resistencia), därför
  inget globalt alias. Pinnacle skriver motparten "CA Tigre", så kontextaliaset bär
  Pinnacles egen motpartsform (`_POOL_CONTEXT_OPPONENTS`, bara för paret); med det länkas
  paret på nivå D (Tigre-sidan är ett icke-generiskt delnamn). Ingen ny regel i övrigt;
  4418 Sarmiento–Rosario länkas fortfarande inte. Omgång 4433 är stängd och Pinnacle
  spärrar Sverige, så ändringen verkar först när Pinnacle svarar igen. Inget bakfyllt.

**Nytt 2026-11-06:**
- **V2.2 v10 och poolstyrkans manifest v2 AVSLUTADE per 2026-11-05 09:30Z** (beslut
  2026-11-06-v22-manifest-pinnacle, val 0). Båda var frysta mot Pinnacle, som spärrar
  Sverige; missat är missat. `ENDED_COHORTS` i `oddset_v22`/`pool_strength_shadow`
  (nyckel = shadow_version `v22-fed39cbd`/`ps-8cbcf320`; manifestfilerna orörda): ingen
  ny capture, inga rader ändrade (V2.2 1 611 rader/1 250 eligible med träningsgrinden
  NÅDD — `underlag klart` står kvar, en skörd är ett eget beslut; poolstyrkan 2 419
  captures/545 eligible, under grinden, senaste 2026-11-04 22:02Z). Idag larmar inte längre för V2.2
  (`/api/health` → `v22.status = ended`) eller styrkeshadowen; `cli.py gater` och
  Tester visar `avslutad`, Poolstyrka ligger i testarkivet, Labb visar V2.2 som avslutad.
  Ny kohort mot anchor-v1 bara efter ett eget förregistrerat beslut. "För lite färsk
  Pinnacle" på poolomgångarna står kvar — poolens sharp är ett eget beslut.
- **Betfair Exchange och BetInAsia som referensböcker** (beslut
  driften-2026-11-06-betexplorer-per-bok, val 0; `app/betexplorer.py`). Samma
  Betexplorer-svar som bet365 bär båda böckerna, så de kostar inga egna anrop: 1X2,
  Ö/U exakt 2,5 och handikappets huvudlina, källor `betfair_ex`/`betinasia` i
  `oddset_odds` och presence-ledgern. Takten är gemensam och högst ett anrop per match
  och marknad och timme (bet365:s 25 min inom 3 h blev 60 min). I `REFERENCE_BOOKS`
  (aldrig bok att slå, aldrig ankare, signalversionerna oförändrade); Oddset-vyn visar
  raderna `BFX`/`BIA`. **Mätningen:** `cli.py betexplorer-matning [--sedan ISO]` parar
  varje capture med Smarkets (1X2, Ö/U 2,5) och SBOBET (handikapp, samma lina) som de
  var vid observationen (≤ 45 min bekräftelse, inget senare pris) och visar avvikelse,
  snedhet, marginal och bokens prisålder. Beskrivande — ett ankarbyte är ett eget beslut.
- **bet365 som referensbok** (beslut 2026-11-06-betexplorer-bet365, val 0;
  `app/betexplorer.py`). Betexplorers publika fixtursidor och sidans egen
  `/match-odds/`-JSON ger bet365:s 1X2, Ö/U och handikapp (huvudlinan = mest balanserad)
  med bokens egen ändringstid per tecken. Femton belagda ligor (14 ligor 130/130 matcher
  parade, Champions League 18/18), matcher inom 7 dygn, sist i djupvarvet med ≤ 240 s och
  3 s mellan anropen (~22 matcher per varv i provkörningen). Oddset-vyn visar raden `365`
  bredvid Sm/SBO och tooltipen när bet365 senast ändrade priset. I `ANCHOR_SOURCES` via
  `REFERENCE_BOOKS`: aldrig bok att slå, aldrig ankare; signalversionerna oförändrade.
  Europa/Conference League beläggs när vi har matcher där. Betfair Exchange/BetInAsia
  läses sedan samma dag ur samma svar (punkten ovan).
- **Pinnacle spärrar Sverige** sedan 2026-11-05 09:30Z (Cloudflare 403 på allt, även
  www.pinnacle.com). Ingen väg runt (källgränsen). Värdemotorn, CLV, steam, poolens
  sharp-underlag och liveblindtestets Pinnacle-del står still. Betfair lämnade Sverige
  2025-07-16 och är stängd av samma skäl.
- **SBOBET** (`app/sbobet.py`, i drift 2026-11-06T00:17:05Z, första djupvarv 00:30Z) samlar
  1X2 och handikappets huvudlina ur de publika datumsidorna, sex dagar framåt, för fjorton
  ligor med belagda liga-id:n (127 matcher i första varvet). Referenskälla i
  `ANCHOR_SOURCES`, aldrig en bok att slå. 1X2-marginal ~15 %, handikapp ~4,7 %.
- **Smarkets** visas igen (`UI_HIDDEN_SOURCES` tom); Smarkets och SBOBET står som
  referensrader i Oddset-vyns matchrad. Källprovet har båda som stödkällor och Pinnacle som
  stödkälla.
- **anchor-v1** (Samans beslut 2026-11-06, i drift 00:52:15Z, `ANCHOR_SWITCH_AT`
  00:48Z): Smarkets ankrar 1X2 och SBOBET handikappets huvudlina i värdemotorn, steam,
  notisvakten, CLV-stängningen och WP5-ledgern. Ö/U och hörnor har inget ankare. Ingen
  driftjustering (band-v8 är Pinnacle-kalibrerad). Ny sharp-version `s-2bd0ddd1` och
  modellversion `m-d3d8e5d0` — facitet börjar om. Första API-svaret: 462 1X2-poster mot
  Smarkets, 144 handikapp mot SBOBET. **Står kvar på Pinnacle (stilla):** poolens sharp
  (bygge, PH3, pit-v4, X-skyddets total, m20-reserven), modellens totalankring och
  Ö/U-sharp. V2.2 v10 och `pool-strength-blend` manifest v2 (ingen capture sedan
  2026-11-04 22:02Z, baslinjen är Pinnacle) är avslutade (punkten överst). Poolens
  ankare är ett eget beslut.
- **pool-reference-v1** (Samans val "bara visning" 2026-11-06): poolanalysen visar
  Smarkets (`Sm`) eller SBOBET (`SBO`) där Pinnacle-raden stod, kopplat exakt på Kambi-id.
  Underlagsvarningen blir `info` ("Pinnacle spärrad — Smarkets/SBOBET som referens i N/M")
  när varje match utan Pinnacle har referens. Bygget, PH3, PIT, X-skyddet och CLV orörda.
- **pool-draw-risk-v2** (Samans val "X-skydd via Kambi" 2026-11-06): där Pinnacle-totalen
  saknas styr Svenska Spels/Kambis Ö/U-lina X-skyddet (samma ≤ 2,25-regel) i appen, PH3
  och spelai-standarden. Inför varje frysning hämtas omgångens linor direkt (~0,1 s/anrop);
  läsningen är as-of med 90 min färskhet. Datumnot i PH3, nycklarna oförändrade. SBOBET:s
  publika sidor saknar Ö/U; Smarkets Ö/U (bara halva linor) blir visning.

**Nytt 2026-11-05:**
- **Big 9: valet hög EV** (beslut 2026-11-04-big9-hog-ev-i-appen-omforsok, val 0).
  Byggaren i Poolspel → Big 9 har ett tredje val, **hög EV** = värdevikt 1,0 (celler på
  p/q, max EV, samma `build_full_system`), märkt "färre rätt, sällsynta stora vinster".
  Medel förblir standard; ett hög EV-bygge bär aldrig `standard_key`. Facitsidan mäter
  inte hög EV (ingen ny nyckel eller frysning) — skuggan per SP96-omgång följer
  Forskaren i agentens repo. `docs/spelai-facit.md` § 19.4.
- **Big 9: egen kupong** (beslut 2026-11-04-big9-lagg-till-i-kupong-omforsok, val 0).
  Poolspel → Big 9 har sektionen **Egen kupong** (öppna omgångar utan Wild Card): tryck
  på en ruta (1 Ö … 2 U) per match för att lägga till eller ta bort; varje ruta visar
  folkets streck och modellens % (ATG:s odds utan marginal), en vald ruta även kvoten
  modell/streck (grön över 1, röd under 1). Kupongen visar form (4·2·1…), rader,
  kostnad, chans för 9 rätt enligt modellen (produkten av valda rutors sannolikhet,
  struken match = rätt) och folkets andel för samma rader (produkten av strecken,
  matcherna oberoende); saknas modell eller streck visas `–`, aldrig en gissning.
  Byggarens system läses in som start ("Läs in byggarens system"/"Ändra i egen kupong")
  och sparas per öppen omgång i `localStorage` (`big9_kupong`). Ren frontend
  (`lib/big9.js`: `couponStats`, `toggleCell`, `couponFromSystem`), samma API-svar som
  förut; backend, insamling, standard och facitsidans mätning orörda. Inga spel läggs.
- **Big 9 på 512 kr** (beslut 2026-11-04-big9-niva-512-omforsok, val 0). Facitsidan
  mäter SP96 även på 512 kr = högst 1 024 rader, från omgång **554** (samma som fulla
  system; `nivaer.ATG_NIVAER_FRAN`, `nivaer_for(produkt, omgång)`). Standard
  `big9-fullsystem-v1-sp96-b512-medel` (samma `build_full_system`, medel), agenten
  får `nivaer: [256, 512]` och svarar på båda; facit per nivå i `per_niva_atg`.
  Omgångarna före 554 behåller bara 256 kr, inget bakfyllt. `docs/spelai-facit.md` § 19.3.

**Nytt 2026-11-04:**
- **Big 9: bara fulla system** (beslut 2026-11-04-big9-fullt-system, val 0). ATG tar
  inga reducerade urval och ingen radfil, bara "Spela enskilda utfall": valfria av de
  sex cellerna per match. Från **SP96 omgång 554** (`nivaer.FULLT_SYSTEM_FRAN`) gäller:
  standarden är `big9-fullsystem-v1-sp96-b256-medel`
  (`big9_builder.build_full_system`: en cellmängd per match, rader = korsprodukten ≤
  512), och agentens rader godtas bara som exakt hela korsprodukten (annars
  `ogiltigt`). Paketet säger det (`rader.fullt_system`, schema
  `spelai-indata-big9-v3`). Appens byggare bygger samma fulla system och visar
  **kupongen att markera hos ATG** (sex rutor per match, formel a × b × … = N rader).
  Omgång 546 (6h-fönstret 13:45Z, minuter efter driftsättningen) körs helt under de gamla reglerna;
  frysta rader är orörda och rättningen är oförändrad. Serierna `big9-varderader-v1-*`
  och `big9-fullsystem-v1-*` jämförs aldrig som en serie. `docs/spelai-facit.md` § 19.2.
- **Big 9 i appen** (beslut 2026-11-04-big9-i-byggaren, val 0): Poolspel har fliken
  **Big 9** (`src/big9/Big9View.jsx`, `POOL_TABS`) med ATG-omgångarna (öppna först,
  annars de senaste stängda), matcherna med ATG:s odds (1X2 + Ö/U 2,5), vår sannolikhet
  och folkets streck för de sex cellerna (värdefärg 1,08/0,92) och byggaren:
  `big9_builder` via facitsidans paket (`app/big9_view.py`, `/api/big9/system`), strategi
  medel/säker (värdevikt 0,5/0,2), budget 16–1 024 kr. Raderna visas som kupongbild
  (täckning per match + rad för rad) eller text (kopiera/ladda ned .txt) med länk till
  atg.se/sport/big9 — ATG:s radfilsformat är overifierat, inga spel läggs. Bara rena
  läsningar av ATG-tabellerna; insamling, standard och facitsidans mätning orörda
  (`build_payload` tar `horizon=None` för appen, facitsidans paket byte-identiska).
- **pool-name-v12** (beslut drift-2026-11-04-topptipset-4429-alajuelense-alias, val 0):
  poolaliaset LD Alajuelense → Alajuelense. Topptipset 4429 match 8 (CD Escorpiones
  Belen–LD Alajuelense, 2026-11-05 02:00Z) fick ingen Pinnacle och vakten larmade
  `pool_pinnacle_saknas:topptipset:4429`: `pool_match_diagnostic` gav "Escorpiones Belen
  – Alajuelense" vid exakt avspark sidopoäng 0,0/0,0. Med aliaset länkas paret på nivå D
  (Escorpiones-sidan är ett icke-generiskt delnamn). Krockprov mot 2 379 namn i
  diagnostiken: bara LD Alajuelense fick ny nyckel. Frysta kuponger orörda, inget bakfyllt.
- **pool-name-v11** (beslut 2026-11-04-europa-2622-slavia, val 0): poolaliasen Slavia
  Prag/Slavia Prague → Slavia Praha och Sparta Prag/Sparta Prague → Sparta Praha.
  Europatipset 2622 match 1 (Slavia Prag–Arsenal, 20:00Z) fick ingen Pinnacle:
  `pool_match_diagnostic` gav "Slavia Prague – Arsenal" vid exakt avspark sidopoäng
  0,0/1,0. Krockprov mot 2 378 namn i diagnostiken: bara Slavia Prag, Slavia Prague och
  Sparta Prague fick ny nyckel. Frysta kuponger orörda, inget bakfyllt.
- **Livekassans resultatalias Sporting Lissabon** (beslut
  drift-2026-11-03-alias-sporting-lissabon, val 0): spel 173 (Shakhtar Donetsk–Sporting
  Lissabon, CL 2026-11-03) låg orättat eftersom Flashscores resultat heter "Sporting CP".
  `livekassa.RESULTAT_ALIAS` fick `sporting lissabon` → `sporting cp`; nästa `ratta`
  rättar spelet och släcker `livespel_orattat:livekassa`. `docs/spelai-facit.md` § 16.
- **Livekassans resultatalias Manchester United och Roma** (beslut
  drift-2026-11-04-alias-manchester-united, val 0): spel 174 (Manchester United–Roma,
  CL 2026-11-03) låg orättat eftersom Flashscores resultat heter "Manchester Utd"–"AS
  Roma" (3–2). `RESULTAT_ALIAS` fick `manchester united` → `manchester utd` och `roma` →
  `as roma`; nästa `ratta` rättar spelet. Serie A:s `roma` träffar på de råa namnen och
  når aldrig aliaset. Inga historiska rader ändras. `docs/spelai-facit.md` § 16.

**Nytt 2026-11-02:**
- **Altenar borttagen som källa helt** (beslut 2026-11-02-altenar-pausa, val 1). Hela
  Altenar-värden har svarat 403 sedan 2026-10-21 — Betinia i källprovet (larmet
  `kalla_nere:altenar` rött i 12 dygn) och Ninja Casino (`ninjacasinose`) i
  Oddset-insamlingen, livejournalen och poolens liverättning; att runda skyddet är
  stängt. Borta: `app/altenar.py`, `ninjacasino` ur `oddset.BOOKS` och ligornas
  `altenar`-id, Ninja ur `live_signal_ledger` (prisval nu färsk Pinnacle → Kambi) och ur
  `pool_played.attach_live_odds` (Kambi → Pinnacle), `check_altenar` ur källprovet (inget
  veckoprov), N-raden och Ninja-källhälsan i Oddset-vyn. Larmet släcks vid nästa
  källprov. Historiska `ninjacasino`-/`ninja`-rader orörda och visas som historik.
  Iakttagelse (ej ändrad): radarns löpande kohort `chance-gap-shadow-v14` (från
  2026-10-15T22:00Z) har 31 signaler prissatta av Ninja 16–20/10; från 2026-10-21 gav
  Ninja bara `source_error`, så prisvalet efter borttagningen är detsamma som de senaste
  tolv dygnen. Ingen ny radarversion — det är ett eget beslut om någon vill ha det.

**Nytt 2026-10-25:**
- **Flashscore-resultat för matcher över svensk midnatt** (beslut
  livekassa-saknat-resultat-nyrb-miami-2026-10-25, val 0): spel 111 (New York Red
  Bulls–Inter Miami CF) rättades inte eftersom matchen låg i både dagsfeed −1 och 0
  med samma id, och två kopior bröt entydighetskravet i `refresh_recent_results`.
  `flashscore_data._unique_finished` slår ihop identiska kopior (samma id, lag,
  avspark, stadium, ställning); motstridiga kopior avvisas som förut. Gäller
  livekassan och radarns signaljournal (facit). xG-/frånvarovägarna orörda
  (iakttagelse). `docs/spelai-facit.md` § 16.

**Nytt 2026-10-24:**
- **Big 9 från ATG på facitsidan** (beslut driften-2026-10-24-big9-atg, val 0).
  `app/atg.py` samlar in ATG:s publika offering-lista (BIG9 och SP96) append-only
  med egen kadens först i pool-tick; `app/big9_builder.py` är standarden
  (`big9-varderader-v1-b256-medel`: värderader medel, sex celler 1X2 × Ö/U 2,5,
  Wild Card, 7–9 rätt, 512 rader à 0,50 kr); `app/spelai/big9.py` fryser 6h/30m
  ur samma fönster som poolspelen och rättar mot ATG:s publicerade potter (regeln
  återger alla 101 avgjorda omgångars belopp exakt). Big 9 räknas separat
  (`per_niva_atg`). `docs/spelai-facit.md` § 19.
- **SP96 mäts som Big 9** (beslut 2026-10-24-sp96-ar-big9, val 0): `atg.MEASURED`
  = `("sp96",)`; gamla BIG9 samlas in om den dyker upp igen men mäts inte. Standard
  `big9-varderader-v1-sp96-b256-medel` = samma byggare utan Wild Card, 6–9 rätt
  (35/15/15/35 %), 512 rader à 0,50 kr, strategi medel, frysning 6h/30m.
  Återbetalningsandelen läses ur omgångens publicerade potter (omgång 517: 72,75 %,
  inte uttagets 75 %), annars 1 − uttag; paketschema `spelai-indata-big9-v2`.
  `W` är ogiltigt i SP96. Rättningen oförändrad; att den stämmer för SP96 prövas
  vid första rättningen (`payout_kr` mot `published_payout_kr`). Omgång 517:s
  6h-fönster öppnade före `facit_start_big9` och räknas inte. `docs/spelai-facit.md`
  § 19.1.
- **Tidskänsligt CDN-Age-test rättat** (beslut 2026-10-23-tester-roda-cdn-age, val 0):
  `test_book_cdn_age_backdates_confirmation` fällde nattkörningen 2026-10-23. Orsaken var
  den UNDRE gränsen: `report["at"]` sätts när `collect()` startar, så avdraget är 120 s
  minus tiden fram till bokanropet, och gränsen 119 s föll så fort det tog över en sekund
  (uppspelat med fördröjning: 114 s). Gränserna är nu `120 − elapsed − 1 ≤ avdrag ≤ 121`
  med `elapsed < 60 s`. Bara testet ändrat; insamlingen orörd.

**Nytt 2026-10-21:**
- **Livekassans resultatalias för spel 80** (beslut livekassa-alias-sabah-dortmund-2026-10-20,
  val 0): `RESULTAT_ALIAS` översätter Sabah FK → Sabah Baku och Borussia Dortmund →
  Dortmund (Flashscores namn), så spel 80 rättas av nästa `ratta`. Inget bakfyllt
  utöver settlat resultat; radarns och Oddsets alias orörda. `docs/spelai-facit.md` § 16.

**Nytt 2026-10-18:**
- **Livekassan spelar till 0 kr** (beslut koordinatorn-2026-10-18-livekassa-till-noll, val 0): `livekassa.SPARR_KR`
  = 0, så ett fiktivt livespel godkänns så länge tillgänglig kassa efter spelet är
  minst 0 kr; avslagsskälet heter nu "kassan skulle hamna under 0 kr". Spärren låg
  vid 7 500 kr. Historiska rader och tidigare nekade spel orörda; agentens egen
  spärr vid 8 500 kr och livegränserna för en förbättring (≥ 200 spel, ≥ 60 dagar,
  undre KI90 > 0) påverkas inte. `docs/spelai-facit.md` § 16.
- **Byggaren städad** (beslut koordinatorn-2026-10-18-stada-byggaren-2, val 0; underlag
  spel-ai-kompisens P3, Granskarens dom 2072939). Poolspelets byggare erbjuder bara
  Värderader (förval), Reducerat och Matematiskt; Färgreducering, Egen reducering,
  Svenska Spels R-system, radprofilerna Träffsäkrare/Radform v1/Täckningstest v1 och Två
  kompletterande kuponger är gömda. Värdevikten är låst på 50 % och reglaget gömt — även
  vid säker (PH3:s säker-nycklar mäts med 0,2, så säker i appen motsvarar ingen mätt
  nyckel). Ett sparat dolt val börjar om på Värderader. `builder.py`, API:t, PH3 och
  historiska kuponger med sina etiketter orörda. Iakttagelse (ej ändrad): R 3-3-24 byggs
  med `_greedy_cover`, som inte är optimal och bryter lika lägen i mängdens
  iterationsordning — 36–41 rader beroende på `PYTHONHASHSEED` (uppmätt 12 frön), aldrig
  Svenska Spels 24; Forskarens 39 och CLAUDE.md:s 38 är två dragningar av samma slump.
- **pool-name-v10** (beslut drift-2026-10-18-pool-perez-zeledon-alias, val 0):
  poolaliasen Perez Zeledon → Municipal Perez Zeledon och CS Herediano → Herediano
  (Topptipset 4394 match 8 fick `not_listed`, sidopoäng 0,0/0,0 i
  `pool_match_diagnostic`). Krockprov mot 2 025 namn i diagnostiken: bara de två
  avsedda namnen fick ny nyckel. Frysta kuponger orörda, inget bakfyllt.
- **Poolvarianterna städade** (beslut koordinatorn-2026-10-18-stada-poolvarianter,
  val 0; underlag spel-ai-kompisens P2-granskning). PENSIONERADE (fryses inte
  längre, historiken kvar som pensionerad, inga nycklar ändrade): tuff på alla
  budgetar, `dr1-b144-*`, `dr1-b1024-*`, `dr1-b512-saker`, `dr1-b256-medel-sharp`
  och de tre `poolopt-v1`-armarna (grinden `avslutad`, ingen sista avläsning vid
  120). DOLDA men frysta: `dr1-b256-saker`, PH5:s byggarslump/favoritrad/maxev,
  `reducedmax-v2-…-ev80` och `mathmax-v2-…-ev80` — `hidden` i API-svaren, borta ur
  Tester/Autopool, prövas igen vid n ≥ 40 (kring mitten av december). SYNLIGA:
  standarderna `dr1-b256-medel`, `dr1-b512-medel`, `ph5-v4-dr1-b5000-medel`,
  `reducedmax-v2-dr1-b20000-ev50`, `mathmax-v2-dr1-b39366-ev50`. Byggaren erbjuder
  bara säker/medel (ett sparat tuff-läge börjar om på medel). Championens
  utmanarfamilj är nu 256 säker och 512 medel, så FDR-familjen är mindre än förr;
  pensionerade utmanares historik ingår inte i rapporten. Facitsidan, standarden
  per nivå och historiska rader orörda. Ingen förbättring påstås.

**Nytt 2026-10-16:**
- **Notislänken öppnar beslutssidan** (beslut koordinatorn-2026-10-16-notislank,
  val 0): `SPELAI_NOTIS_LANK` = `http://100.106.151.124:5175/` (Tailscale-IP,
  Tailscale måste vara på i telefonen). `notis.lank_for`: beslut → `#/beslut/<id>`,
  övriga notiser → agentens app på 5176. Testnotis: `cli.py spelai-testnotis`
  (journalen `notis_test`). `docs/spelai-facit.md` § 9.
- **Färre poolnotiser** (beslut koordinatorn-2026-10-16-notiser-pool, val 0):
  `notis.aviseras` i `notis.kandidater` styr både ntfy och chattbudet. 6 h-
  versionen ger ingen notis; Topptipset-familjen aviseras bara när spelstoppet
  ligger 12:00–22:00 svensk tid (inklusive); Stryktipset/Europatipset som förut;
  missade och ogiltiga förslag alltid. Frysning, facit och mätning orörda
  (`docs/spelai-facit.md` § 9 och § 15).

**Nytt 2026-10-14/15:**
- **Livesidan `#/live`** (Samans önskemål 2026-10-15): alla pågående poolomgångar
  sida vid sida med ställning, klocka, livepris, prognos per rad, folkets andel med
  allt rätt och för egna kuponger levande rader per nivå, chans och vad som krävs
  för alla rätt. `app/pool_live_view.py` räknar i bakgrunden var 20:e s;
  `GET /api/pool/live` läser bara. Idag visar "Live nu" ur samma svar och räknar
  inte längre liverättning själv; Mina kuponger återanvänder hubbens kupongbild;
  `/api/payouts` cachas 60 s.
- **vakt-v5** (beslut koordinatorn-2026-10-14-sofascore-larm, val 0): Sofascore
  ur källprovet, tyst veckoprov i egen logg som bara säger till när källan svarar
  igen. `KANDA_FEL` är tom.
- **pool-name-v9** (beslut koordinatorn-2026-10-15-pinnacle-alias, val 0): svenska
  klubbnamn jämförs utan IF/BoIS/FK/BK och utan genitiv-s på ordet framför formen
  (Topptipset 4390 Sandviken–Östersund, 4395 Varberg–Helsingborg), plus poolaliaset
  SC Delhi → Sporting Club Delhi (4386). Krockprov mot 2 011 namn i
  `pool_match_diagnostic`: bara de tre avsedda namnen fick ny nyckel.
- **pool-name-v8** fick aliaset Sheffield U → Sheffield United (beslut
  driften-2026-10-14-sheffield-u-alias, val 0; Europatipset 2616 gick utan
  Pinnacle för matchen innan det var på plats).
- **Livekassan** länkar Flashscores färdigresultat ensidigt (samma liga, avspark
  ≤ 15 min, ett lag lika, en kandidat): "Derby County"/"Lincoln City" mot
  "Derby"/"Lincoln" rättades annars först av nattens modelldata.
- **Automatiskt genomförande av besvarade beslut** (beslut koordinatorn-2026-10-14-
  genomfor-beslut-automatiskt, val 1) är på main sedan 2026-10-15 (`3d0bbfb`):
  `app/spelai/genomforande.py` kör `claude -p` per besvarat beslut efter
  2026-10-14T23:00Z, status på beslutssidan och i chatten (facit § 18). Jobbet
  `spelai-genomfor` aktiveras när plisten ligger i `~/Library/LaunchAgents/` och
  `tools/tjanster.sh start spelai-genomfor` körts; tills dess larmar vakten om jobbet.
- **Resultat för alla livematcher** (beslut forskaren-2026-10-15-resultat-alla-
  livematcher, val 0): steget `liveresultat` i spelai-tick skickar högst en gång i
  timmen alla matcher med livepriser (avspark 100 min–36 h bakåt) till samma
  Flashscore-hämtning som livekassans spel. Bara `oddset_results`; rättningen orörd.
  Landskamper kan missa när engelska och svenska namn skiljer (facit § 16).
- **Liveradarn v14, Europacupernas ligafas hos Flashscore** (beslut
  koordinatorn-2026-10-15-flashscore-cuper, val 0): Flashscores rubrik är
  `EUROPE: Champions League - League phase` (EL/ECL likadant), inte det antagna
  nakna cupnamnet, så cuperna saknades i `oddset_live_flashscore` och i
  resultatsteget sedan kvalet (livekassan avstod alla cupmatcher). Ändrat
  källval ⇒ `chance-gap-shadow-v14`, ren start 2026-10-15T22:00:00Z. Prov mot
  54 kommande cupmatcher: 51 får Flashscores resultat (24 strikt, 27 ensidigt).
  `docs/radar-scope-v14-2026-10-15.md`.
- Väntar medvetet: granskaren-2026-10-08-v8-utanfor-1x2 (Samans val: vänta).

**Drift:** endast MacBook-servern 192.168.50.100, backend 8002 och byggd
frontend 5175. Launchd och `tools/tjanster.sh` gäller; ny tjänst `backup`
(04:15). Full kontroll via `tools/kontroll.sh`, som sätter `SPELKOMPISEN_DB`
till en temporär fil så att testerna aldrig öppnar produktionsdatabasen.

**Kontrakt oförändrade:** live-radar chance-gap-shadow-v14 (cupernas ligafas hos Flashscore, 2026-10-15T22:00Z), V2.2 manifest
v10/sharp s-2f14f9a6 (AVSLUTAD per 2026-11-05 09:30Z, ingen ny kohort), amber-modell, powerrank-v2. Poolens champion
dr1-b256-medel, radprofiler, pool-draw-risk-v1, matematiskt max v2 och
reducerat max v2 oförändrade (PH3-utmanarna städade 2026-10-18, se ovan).
Inga modellpromotioner.

**Nytt 2026-10-01, driftvakten vakt-v1 (i drift 14:40:28Z):** `cli.py vakt` körs var
30:e minut (launchd `com.saman.spelkompisen.vakt`) och kontrollerar källprovet, jobben,
insamlingens livstecken i append-only-tabellerna, backendloggarna, driftkopian mot GitHub,
testsviten varje natt i en temporär worktree, disken och testernas avläsningspunkter —
utan AI, utan källanrop och med databasen `mode=ro`. Fel och varningar visas under
"Driften behöver tillsyn" och "Drift att se över" på Idag; trösklar i `docs/vakt.md`.
Första fyndet: **Sofascore svarar 403 med antibot-utmaning sedan 2026-09-25T10:43Z** och är
stängd enligt källgränsen. Sedan dess saknas Sofascores resultat, xG/statistik och frånvaro
(veckan 18–24/9: 111 resultatrader i 15 ligor och 96 statistikrader). Flashscore täcker
frånvaron och en del statistik. Landslagsuppehållet gör att bara träningsmatcherna hittills
saknar resultat (3 av 18); från nästa ligaomgång saknar ligor utan football-data resultat.
⚖ ersättning i backlog 21. **spel-ai-kompisen godkänd av Saman 2026-10-01:** en självständig agent
i ett privat sidoprojekt, mätt av en betrodd facitsida i Spelkompisen. Kontraktet och byggordningen
står i `docs/spel-ai-kompisen-design.md`.

**spel-ai-kompisen i drift 2026-10-01T19:34:31Z (fas B och D, delar av G):** facitsidan (`app/spelai/`, tabellerna `spelai_*` via migrering med backup) fryser agentens och standardens poolförslag 6 h och 30 min före spelstopp på alla nivåer (256 alla poolspel; 512/5 000/20 000/39 366 Stryktipset och Europatipset) och rättar dem som PH3. Agentens startstrategi `standard-v1` ger exakt standardens rader (provat i sandboxen på Stryktipset 4973, alla fem nivåer). Beslutssidan `#/beslut` och raden "N beslut väntar" på Idag; agentens app (5176) och agent-API (8003) kör i Spelkompisens sandbox. **Fas F i drift 2026-10-01T21:17Z:** `com.saman.spelai.roller` (var 5:e min) startar agentens rollkörningar (`claude -p --agent <roll>` i agentrepot, ren miljö, högst en åt gången, tak 8/dygn och absolut 12) — morgonrunda 07, forskningspass 10, motiveringar när agenten avviker från standarden, larm från vakten och söndagens UI-genomgång med skärmbilder som facitsidan tar — och speglar agentrepot till GitHub via en betrodd bar spegel. Gränsprovet av Claude-sandboxen (19 prov) nekade alla förbjudna försök. Chattservern (`com.saman.spelai.chatt`, Remote Control) är i drift sedan 2026-10-02 00:14. Sedan 2026-10-02 lämnar facitsidans chattbud beslut, officiella poolförslag och rollkörningar i chatten i Claude-appen (`docs/spelai-facit.md` avsnitt 15); pushen till telefonen går via ntfy, som Saman prenumererar på sedan samma dag. **Fas E (livekassan) i drift 2026-10-03** (Samans beslut 3): facitsidan lägger agentens fiktiva livespel mot Svenska Spels liveodds för över/under. Reglerna: 10 000 kr, 50–200 kr, högst 3 spel och 600 kr per match, spärr vid 0 kr sedan 2026-10-18 (7 500 kr före), priset högst 60 s gammalt. Spelen rättas mot radarns resultatkälla och visas under Live i agentens app (`docs/spelai-facit.md` avsnitt 14 och 16).

**Landslag i Oddset 2026-10-03 (Samans beställning under landslagsuppehållet):** Nations League (Pinnacle A–D 200719/200721/200726/200727, Kambi `football/uefa_nations_league`) och landskamper (Pinnacle 2117, Kambi `football/international_friendly_matches`) samlas som ren sharp-väg utan modell, med egna utforskande facitgrupper. Svenska Spels svenska och Pinnacles engelska namn kopplas på FIFA-landskod (`app/landslag.py`, 202 landslag), aldrig på namnlikhet; okända namn rapporteras som `okanda_landslag`. Prov mot tom databas 2026-10-03 cirka 10:00: 26 av 31 matcher kopplade till båda källorna. De övriga fem saknades hos en källa (Ryssland och Belarus utan Svenska Spel-utbud, Sri Lanka–Djibouti, två matcher 6/10 som Pinnacle inte listat än). Liveradarn följer med sedan v13, ren start 2026-10-03T08:45Z, med landskodsidentitet i `_same_team` och landskamper bakom samma Oddset-spärr som träningsmatcherna (`docs/radar-scope-v13-2026-10-03.md`).

**Smarkets-skuggan lagad 2026-10-03:** Smarkets ger sedan 2026-09-19 (mellan 16:00Z och 16:14Z) högst 50 event per svar och pekar vidare med `pagination.next_page`. Klienten läste bara första sidan, alltså de 50 äldsta eventen. Från 22/9 gav nästan alla ligor 0 rader med ok-status (tyst fel), och kandidater utan rad märktes `unavailable` fast deras sida aldrig lästes. `smarkets.upcoming_events()` bläddrar nu till slutet (19 sidor, 918 event, 1,5 s). Om sidtaket nås blir det ett fel, aldrig en kortare lista. Cupernas ligafas (`uefa-champions-league`, `uefa-europa-league`, `uefa-europa-conference-league`, kvalslugsen behållna) och landslagen (Nations League A–D, `international-friendlies`) är avlästa ur Smarkets egna `full_slug`. Skuggserien har ett hål från 2026-09-19T16:00Z till driftsättningen; Smarkets-frånvaro i det fönstret bevisar ingenting. Andra ankaret är fortfarande bortkopplat från värderingen, och `ANCHOR_SOURCES`-spärren står kvar.

**Oddsets delade identiteter 2026-10-03 (rättelse i drift 2026-10-03T20:45:28Z, datumnot):** `collect()` länkade bara mot listfönstret (10 d). Matcher som Pinnacle och Svenska Spel listade tidigare, i olika varv, fick en `pin:`- och en `svs:`-rad som de write-once käll-id:na höll isär: 30–33 % av matcherna 7–20/9 och 71–100 % efter landslagsuppehållet (301 av 308 par sedan juli). Svenska Spels odds låg då utan Pinnacle-ankare. Nu länkas mot ligans alla kommande rader (`link_cands`) med oförändrade regler. De 170 kommande paren slogs ihop 2026-10-03T20:46:40Z efter Samans godkännande (`scripts/migrera_oddset_identitetspar.py`, backup före, `integrity_check` ok, 0 identitetskonflikter); 138 passerade par lämnas. 2026-10-04 (Samans beslut): datumnoten gäller utan versionsbyte; PSG kopplas via källkopplingens eget alias (`ODDS_LINK_ALIASES`, inte `TEAM_ALIASES`, som hade ändrat radarns v13-länk), och de tre PSG-paren är sammanslagna; driftvakten vakt-v3 larmar med `oddset_delad_identitet` när en kommande match får två rader. `docs/overlamningar/overlamning-2026-10-03-oddset-identitet.md`, backlog 22.

**Nytt 2026-09-24 (statusauditen och Samans beslut samma dag):**
- **pool-sharp-freshness-v1** (i drift 14:11:09Z): ett cachat Pinnacle-pris
  används bara om det är högst 90 min gammalt och ingen observation efter
  priset sagt att länken tappats. Gäller analys, bygge, PH3-frysningar,
  rörelser/steam, poolens CLV-logg, notiser och Ö/U-reserven. Oddsvarningen
  visar orsaken; poolhälsan varnar när under 70 % av en omgångs matcher har
  färsk Pinnacle inom 48 h före stopp. CLV-stängningen kräver en bekräftad
  länk högst 90 min före avspark eller spelstopp.
- **pool-name-v5** (i drift 14:30:53Z, beslut 1A): tidsankare ±15 min,
  nivåer A/B/C/F, landsnamn bara för landslag och bara exakt. De öppna
  omgångarna gick från 62 till 94 av 106 länkade matcher (Stryktipset 4972
  från 0 till 13) utan ändrade eller förlorade länkar, bekräftat i drift i
  basvarvet 14:57Z. m20-reserven
  använder redan hämtade svar när budgeten är slut. pit-v4 och pit-total-v1
  fortsätter med datumnot.
- **Styrkeshadowen**: manifest v2 (`ps-8cbcf320`, fryst 14:13:13Z, beslut 3A)
  efter tyst stopp 2026-08-21. Stopp syns nu i rapport, gater och poolhälsa.
- **Pooloptimeraren** avläst vid 40 parade omgångar (beslut 5aA): ingen cell
  passerad, ingen utmanare. Sista avläsning vid 120 framåtomgångar.
- **Sharp-utmanaren** fortsätter med samma nyckel (beslut 5bA). Primär
  jämförelse utesluter omgångar frysta med inaktuellt Pinnacle före
  färskhetsregeln: 8 av 49 vid 180 min och 6 av 49 vid 20 min.
- **Backup** (beslut "backup ja"): nattlig onlinekopia 04:15, 14 dagar lokalt
  och senaste kopian i det privata repot `spelkompisen-backup`.
  Återställningen är verifierad, och poolhälsan varnar om kopian blir äldre
  än 36 h eller inte når GitHub. `docs/backup.md`.
- Småfel rättade: settlementurvalet tolkar spelstopp som tid (facit för
  ospelade omgångar två timmar tidigare), κ-texten i portföljkortet och
  teckenandelar för spelade reducerade kuponger.

**Kväll 2026-09-24 ("fixa det också"), i drift 2026-09-24T19:51:01Z:** matcharen **pool-name-v6**
(truppmarkörer ur Pinnacles liganamn; inga av dagens länkar ändrade), omsättnings-
prognosen **tp2** (sann median, dagtypsläge, svensk veckodag; Europatipset 2610 gick
från 9,0 till 4,5 Mkr), utdelningsprognosen med minimiutdelning 15 kr och garanti på
egen rad, oddsrörelse per match (SvS-serie för olänkade matcher), Ö/U-reservens
gemensamma kö (pool-reserve-ou-v2), m20-reservens avslagsorsaker, kupongdetaljens
markering av inaktuella priser, ren läsning i `/api/external-odds`, avstängd
trådinsamlare och tidsjämförelser i sharp-serien. tp2 och rörelsen ändrar PH3:s
radval (datumnot).

**Nytt 2026-09-30, pool-name-v7 (i drift 2026-09-29T23:47:34Z, Samans beslut):** ligans
dammarkör är veto för landslag (SvS skriver alltid Dam) men bara skiljeregel för omärkta
klubbnamn — en damrad länkas när ingen herrrad kvalificerar inom ankaret, annars vinner
herrraden som i v6. SvS egna damformer (Dam, WFC, LFC, Ladies) är truppmarkörer som
gäller båda lagen. Alias: Sporting Jax, Junior de Barranquilla, Estudiantes mot Platense.
Bakgrund: damernas Champions League i Topptipset 4359 hade 2 av 8 länkade i v6 fastän fyra
rader fanns i Pinnacles index med exakt avspark. Första basvarvet med v7 (23:57:43Z):
4359 från 2 till 6 av 8, 4360 från 5 till 7 av 8, 4361 från 4 till 5 av 8; 38 av 45 matcher
i de öppna omgångarna oförändrade och de sju ändrade exakt de avsedda, ingen länk tappad.
Kvar olistade hos Pinnacle: Malmö FF–St. Pölten, Rangers LFC–Hammarby, Panama–Nya Zeeland
och tre landskamper 2/10.
`docs/overlamningar/overlamning-2026-09-30-poolnamn-v7.md`.

**PIT:** pit-v4 + pit-total-v1 med datumnoter 14/9, 15/9, 21/9, 24/9 och 30/9.
Redovisa regimerna vid skörd. Systemjämförelsens nycklar är oförändrade;
färskhetsregeln är en datumnot från 14:11:09Z.

**Grindar avlästa 2026-09-24:** poolopt 47/40 par, avläst vid 40 (ej
passerad). Sharp-utmanaren 49/40 par (41/43 efter uteslutning). PH3
Topptipset "ingen utmanare" 52/53. PH4 out-of-time Stryk 9/40, Europa 17/40.

**Nästa steg:** följ första dygnet med v5 i poolhälsan och
`pool_match_diagnostic`, och kör täckningsrapporten `--sedan 2026-09-24`
omkring 2026-10-01 som egen regim. Kvarvarande fynd står i backloggen
(punkt 19).

## Modellplan — vägen till en modell att lita på (efter backtest-domen)

**Ersatt 2026-07-16 av den förregistrerade marknadsankrade v2-planen i
`docs/modell-v2-plan.md`. Punkterna M1–M5 nedan bevaras som historik.**

Backtesten visade: DC-modellen är nära marknaden i Allsvenskan men slår den inte,
och är svag i Eliteserien. Att slå Pinnacles STÄNGNING på 1X2 är fel mål — planen
är att vinna där marknaden är svag:

- **M1 — xG-viktad fit ✅ MÄTT (backtest v2, 2026-07-12)**: backfill klar
  (978 nya matcher; totalt ~574+390 med xG). Dom: **xG lyfter modellen i BÅDA
  ligorna** (logloss 1.029→1.022 Allsvenskan, 0.991→0.980 Eliteserien; bättre
  kalibrering). Allsvenskan blev t.o.m. lönsam vid låga trösklar: **+13,4 % ROI
  vid edge ≥2 % (n=326), +10,4 % vid ≥5 %** mot Pinnacle-stängning — MEN bara
  ~1,4σ från noll (snittodds ~4) = inom bruset, och ≥8 % vänder negativt
  (modellens största avvikelser är dess största fel). Eliteserien fortsatt
  giftig (−16..−20 %). rho-grid: −0.01/−0.04 bekräftad. Beslut: amber kvarstår,
  modell-loggtröskeln sänkt till 2 % (2–8 %-bandet är det intressanta) så
  forward-facitet (M3) byggs snabbare.
- **M2 — Elo-prior för tunna lag ✅ (2026-07-12)**: lag som saknas i fitten eller
  har <8 viktade matcher får styrkor ur ClubElo relativt liga-medlet
  (q = 10^(Δelo/400); att = q^0.35, def = q^−0.35; tunna lag blandas
  proportionellt). `_ensure_priors` i oddset_model; ⚠-not i M-radens tooltip
  (`model.prior`). Grov mappning — forward-loggen utvärderar även denna.
- **M3 — forward-test i produktion (IGÅNG)**: modell-flaggor loggas live
  (tier='model', aldrig notis/spel) och jämförs med Pinnacle-stängningen.
  **Grönt-kriteriet per liga: ≥50 stängda modell-flaggor med positivt snitt
  close-EV.** Facitet avgör — inte känsla, inte backtest ensam.
- **M4 — marknader där böcker är slöa**: modellens realistiska nisch är inte
  Pinnacles 1X2 utan (a) tidiga linjer innan sharpen öppnat (redan synligt:
  modell + Elo finns för nästa omgång före Pinnacle), (b) hörnor/lagmål där
  vi har egen Sofascore-data, (c) mindre ligor. **Superettan TILLAGD som liga
  (2026-07-12)**: Pinnacle 2476 + Kambi `football/sweden/superettan` + Altenar
  4825 + Sofascore ut 46 (MED xG!); ingen football-data → Sofascore är
  resultatkälla (MODEL_LEAGUES-gaten). Egen flik, full värdemotor + modell.
- **M5 — blend som referens**: backtesten fann w=0.1 modell + 0.9 marknad ≥
  marknaden ensam i Allsvenskan — modellen bär EN nypa egen information.
  När M1–M2 höjt den kan blenden bli "husets fair" för matcher med tunn sharp.

## Beslut (Saman, 2026-07-12)

1. **Startpunkt:** kopia av svs som bas — poolspelen funkar dag 1, vm-moduler portas in.
2. **Datakällor:** enbart gratis. Undersök även återanvändbara öppna källor som Flashscore
   och ligornas officiella sajter. Rena betalspår (the-odds-api betald, API-Football) =
   framtida projekt.
3. **Framtid:** svs fryses (bara kritiska fixar) när spelkompisen nått paritet.
4. **Namn:** spelkompisen, katalog `/Users/saman/spelkompisen`.

## Mål

Behålla hela poolspels-analysen (Stryktipset/Europatipset/Topptipset/Bomben) och lägga
till en **Oddset-del**: enskilda matcher i tidsordning (visa/dölj ligor) med aktuella odds,
oddsrörelser, sharp-jämförelse och tips — 1X2, asian handicap, asian över/under, hörnor.
Start-ligor: **Allsvenskan, norska Eliteserien, träningsmatcher**. Tips kommer från två
håll: (a) snabba oddsrörelser där någon bok hänger efter (paradexempel: träningsmatch
där lineups läcker och sharpen rör sig före svenska böcker), (b) egen modell (styrkor,
xG-proxy, form, skador) — alltid med vm-lärdomen: modell utan sharp-ankare = amber-tier.

## Etapper

### Etapp 0 — Skelett ✅ (2026-07-12)
Klon, portar (backend 8002, frontend 5175, preview 5181), venv, DB-seed, namnbyte,
Oddset-flik (platshållare), detta dokument, CLAUDE.md omskriven.

### Etapp 1 — Matchlista + odds ✅ (2026-07-12)
- Porta från vm: `pinnacle.py`-utökningarna (matchups + straight för AH/ÖU, inte bara
  moneyline), Kambi-klienten (operator `svenskaspel`, listView + betoffer per event),
  `odds_snapshot`-tabellen med dedup (skriv bara när odds/linje ändrats) och `movement()`.
- Ligaupptäckt Pinnacle: VERIFIERAT (prober nedan) — Allsvenskan 1728, Eliteserien 2333,
  Club Friendlies 1863 (+ 1864 dam). Bygg ändå en `LEAGUES`-tabell (id, namn, Kambi-väg,
  ESPN-slug) så fler ligor bara är en rad till.
- Kambi-vägar: VERIFIERAT — `listView/football/sweden/allsvenskan`,
  `.../norway/eliteserien`, `.../club_friendly_matches` (alla 200; `football/matches` finns EJ).
- Matchnyckel: klubblag, inte landslag → matchning på normaliserat lagnamn + avsparkstid
  (vm:s iso2-matchning funkar inte för klubbar; kolla `names.py`-mönstret + fuzzy).
- Backend: `oddset_matches`-tabell + `/api/oddset/matches` (tidsordnad, liga-filter),
  `/api/oddset/match/{id}` (odds + rörelseserie).
- UI: matchlista i tidsordning, visa/dölj ligor (sparas i localStorage), odds + rörelse
  (samma hover-punktserie-mekanik som analysvyn), flaggor/loggor där de finns.
- Launchd: `com.saman.spelkompisen.snapshot` (30 min; förtäta nära avspark som svs
  snapshot-smart). Saman kör `launchctl load` själv.

### Etapp 2 — Värde + steam + notiser ✅ (2026-07-12)
- Porta `value.py`-mönstret: power-devigad Pinnacle = fair; edge mot Svenska Spel (Kambi)
  per marknad. AH/ÖU jämförs ENDAST på samma linje.
- Steam i devigade procentenheter (6/24/72 h) per match/marknad; 🔥-flaggor i listan.
- ntfy-notiser: (a) sharp-edge ≥ tröskel, (b) snabb sharp-rörelse nära avspark —
  träningsmatch-caset: Pinnacle flyttar ≥X pp inom 30–60 min medan Kambi står still →
  notis medan det höga oddset lever. EGET NTFY_TOPIC (inte svs:s).
- CLV-logg från dag 1 (first/best, stängning = sista devigade Pinnacle före avspark) —
  bara sharp-ankrade flaggor får logga.

### Etapp 3 — Egen modell ✅ (2026-07-12)
- Datainsamling per liga: resultat, tabeller, form. Kandidater: ESPN (`swe.1`, `nor.1` —
  scoreboard + `/summary` med skott/hörnor/possession), football-data.co.uk (SWE.csv,
  NOR.csv — resultat + historiska odds, perfekt backtest-facit), ClubElo (klubbstyrkor,
  täcker nordiska ligor).
- ~~Undersök fler källor~~ GJORT 2026-07-12 (se Prober): Sofascore valdes då
  som ensam xG-källa. **Det beslutet är historiskt:** FotMob kopplades in
  2026-07-25 och Flashscore 2026-08-01; modelldata v4 lagrar providers
  parallellt. FBref/football-data.org är fortsatt avförda.
- Modell: xG-viktad Poisson-styrkefit per liga med DC-korrektion i prediktionen
  (vm:s `model.py` som bas; rho refittas för klubbfotboll,
  vm fann −0.04 landslag vs litteraturens −0.13 klubbar), hemmafördel per liga,
  ClubElo som prior/korsreferens. Ursprungligen kom xG bara från Sofascore;
  aktuellt v4-kontrakt väljer ett komplett providerpar enligt fryst prioritet
  och redovisar proveniensen. ESPN-skottdata är fallback-proxy.
- μ kalibreras mot devigad sharp ÖU-linje där Pinnacle finns (linje ≈ median, inte medel).
- Output: modell-tips som AMBER-tier (bakom toggle, UR CLV) tills backtest (Etapp 5)
  visar att de håller. Sharp-ankrade tips förblir enda gröna.
- Träningsmatcher: modellen får låg vikt (rotationsrisk) — där är steam/lineup-signalen
  (Etapp 2/4) huvudverktyget.

### Etapp 4 — Skador, lineups, nyheter ⛔ SKIPPAD (beslut 2026-07-12: steam täcker caset)
- Google News RSS per lag/match (vm-mönstret: sv+en, dedup, cap).
- X syndication-flödet (vm `twitter.py`): klubbkonton + relevanta journalister; 429-paca.
- Lineup-bevakning: källa oklar — undersök gratis-vägar (klubbarnas konton är mest
  realistiskt; strukturerade lineups utan betal-API är svårt). Kopplas till notiserna:
  "lineup-nyhet + sharp-rörelse + bok står still" är guldsignalen för träningsmatcher.
- Skador: nyhetsbaserat (fritext-flaggor per lag), inte strukturerad data (betalspår).

### Etapp 5 — Backtest + kalibrering ✅ (2026-07-12 — resultat i STATUS-blocket)
- football-data.co.uk SWE/NOR: modell mot historiska stängningsodds — samma beslutsregel-
  validering som svs backtest. Kalibrera trösklar (edge-%, steam-pp) innan de blir "gröna".
- CLV-uppföljning: håller flaggorna mot stängningslinjen? (Facit växer från Etapp 2.)
- Först härefter kan modell-tips ev. flyttas från amber till grönt, marknad för marknad.

### Senare / backlog

- ~~Cross-liga-fit~~ ✅ KLAR (2026-07-12): fit_league tar nu rader från flera
  ligor — lagstyrkor delas, base + hemmafördel per liga (FIT_POOLS: Allsvenskan
  + Superettan = Sverige-pool; Eliteserien egen). Backtest v3 (xG + pool,
  Allsvenskan): samma precision (logloss 1.0216 vs 1.0217) men **+8 matcher
  täckta** = nyuppflyttades matcher som tidigare saknade prediktion. Behållen.
- **Hörn-förväntan (M4b)** ✅ (2026-07-12): `corner_model` per liga ur egen
  Sofascore-data (~1400 matcher med hörnor): liga-snitt-total + hemmaandel ~
  xG-supremacy (OLS). Visas som M-rad i Hörnor-kolumnen (modell-toggle).
  ENDAST förväntan — inga pills/logg (vm-lärdomen: hörn-värde kräver sharp linje).
  OBS: ClubElo täcker bara ~7/23 Superettan-lag, så M2-priorn når inte alla där.
- Hörnor: Pinnacle hörn-specials (units='Corners', ~nära avspark) = sharp referens;
  vm-lärdomen: totalen är nästan konstant (~8.5–10.6), lag-hörnor följer favoritskapet
  (0.507 + 0.108·supremacy, R²≈0.97) — lag-hörnor är den intressanta marknaden.
- Fler ligor (Superettan? Damallsvenskan? danska Superligaen?) när flödet är bevisat.
- Polymarket som andra sharp-källa (tunn täckning klubbfotboll — låg prio).
- Menyn: gruppera flikarna (Poolspel: Stryk/Europa/Topp/Bomben | Oddset) om det blir trångt.
- Betalspår (framtida projekt): the-odds-api betald (multi-book), API-Football (skador/
  lineups/xG strukturerat).

## Datakällor (gratis) — status

| Källa | Vad | Status |
|---|---|---|
| Pinnacle Arcadia | sharp 1X2/AH/ÖU (+hörn-specials nära avspark) | ✅ verifierad 2026-07-12 (liga-id:n nedan); Cloudflare-block i perioder, IP-nivå |
| Kambi (operator svenskaspel) | Svenska Spels sportsbok, alla marknader, milliodds | ✅ verifierad 2026-07-12 — vägar nedan |
| ESPN | scoreboard/tabeller/matchstats (skott, hörnor) för swe.1/nor.1 | ✅ verifierad 2026-07-12 — 5 matcher/liga i svaret |
| football-data.co.uk | historiska resultat + odds SWE/NOR | ✅ verifierad 2026-07-12 — `new/SWE.csv`/`new/NOR.csv`, Pinnacle-stängning (PSC*) sedan 2012 |
| ClubElo | klubbstyrkor, gratis API | ✅ verifierad 2026-07-12 — `api.clubelo.com/Hammarby` ger full historik; vm har `elo.py` |
| Google News RSS | nyheter per lag | ✅ beprövad (vm) |
| X syndication | klubbkontons flöden | ✅ beprövad (vm), 429-känslig |
| **Sofascore (browser-TLS)** | xG/hörnor/resultat/frånvaro + livechansdata | ✅ i drift via `curl_cffi`; egen livecapture, presence och source-health. Modelldata samlas parallellt med Flashscore; resultat-only-ligor använder normaltidsresultat. OBS: live-xG saknas ofta i Allsvenskan. |
| **FotMob** | live-xG/xGOT/open-play-xG/skott | ✅ i drift med `fotmob-live-v2`; egen tabell/presence/health, koherent ställning+stats och fristående kort vid unik identitet. Ingen providerblandning. |
| **Flashscore** | live-xG/xGOT/skott/stora chanser/hörnor + avslutad xG/hörnor/frånvaro | ✅ i drift med publik pipe-feed/persisted query inom källgränsen; `flashscore-live-v2`, egen tabell/presence/health och parallella providerobservationer i modelldata v4. Ingen säsongsbakfyllning. |
| allsvenskan.se / eliteserien.no | officiell statistik | 🟡 WordPress med wp-json — undersök vid behov, låg prio |
| FBref (browser-kontext) | tabeller/grundstats | 🟡 browser passerar Cloudflare (verifierat) men INGEN xG för Allsvenskan (22 tabeller kollade) — lågt värde, skippa |
| Blockerade (omtestade 2026-07-12; FotMob senare LÖST, se egen rad) | football-data.org (Allsvenskan i katalogen men datat kräver betald tier), Opta-webben (Akamai; gratisvägen = renderade bilder, feeds kräver betald outlet-nyckel — omkollat 2026-07-25) | ⛔ |
| ASA (American Soccer Analysis) | MLS: xG/xPass/Goals Added/löner/domare/arenor — oberoende MLS-kvalitetskontroll | 🔴 certfel 2026-07-13 (hostname mismatch, både httpx & Chrome-TLS) — verifiera åtkomst innan planering (WP9a). Blanda aldrig providers' xG i samma fält. |
| Sofascore shotmap | shot-xG + xGOT per skott | ✅ probat 2026-07-13: Eliteserien 30/30 skott med xG — Allsvenskan 0/31 (fältet saknas för SWE). Coverage-matrix (WP9b) innan features byggs. |
| Sofascore team-events | lagets ALLA tävlingar (cup/Europa) | ✅ WP9c i drift 2026-07-17: 94 lag, 3 329 unika event, PIT-first-seen, vila/belastning + basarena-reseproxy; ännu inte modellinput |
| Open-Meteo Historical Forecast | väder med äkta point-in-time-prognoser | 🟡 dokumenterat gratis-API; liten väntad effekt → P2 |
| Betfair Historical | exchange-stängningar | ⛔ skip tills konkret behov — kontokrav, marginell nytta över Pinnacle-close för våra ligor |

## Kända risker

- ~~xG för Allsvenskan/Eliteserien saknar gratiskälla~~ **LÖST 2026-07-12**: Sofascore har
  xG för båda ligorna, åtkomlig i browser-kontext (se Prober) — kräver Playwright-hämtare,
  vilket är ett nytt beroende (browser i insamlingskedjan = skörare än ren httpx; ESPN-
  skottproxy kvarstår som fallback om Sofascore stänger).
- Pinnacles täckning av träningsmatcher varierar (stora klubbar ok, mindre = tunt eller
  bara nära avspark) — utan sharp-ankare blir de matcherna steam/nyhets-drivna, inte modell.
- Klubbnamnsmatchning (Pinnacle ↔ Kambi ↔ ESPN ↔ ClubElo) är mer jobb än landslags-iso2 —
  bygg en `team_alias`-tabell tidigt, den behövs i varje etapp.

## Prober (körda 2026-07-12 — Etapp 1 kan lita på dessa)

- **Pinnacle** `GET /0.1/sports/29/leagues?all=false` (guest-key): Allsvenskan = **1728**
  (6 matchups), Eliteserien = **2333** (5), Club Friendlies = **1863** (11),
  Club Friendlies Women = 1864. Matchups per liga: `/0.1/leagues/{id}/matchups`
  + `/0.1/sports/29/markets/straight` (vm-mönstret).
- **Kambi** (operator svenskaspel, `eu-offering-api.kambicdn.com/offering/v2018/svenskaspel`):
  `listView/football/sweden/allsvenskan.json` ✅ (9 events), `.../norway/eliteserien.json` ✅,
  `.../club_friendly_matches.json` ✅. `football/matches.json` = 404.
  Param: `?lang=sv_SE&market=SE`. Per match: `betoffer/event/{id}.json`.
- **ESPN**: `site.api.espn.com/apis/site/v2/sports/soccer/{swe.1|nor.1}/scoreboard` ✅
  (dagens omgång komplett, korrekta avsparkstider). Matchstats via `/summary?event=` (vm-mönstret).
- **football-data.co.uk**: `www.football-data.co.uk/new/{SWE|NOR}.csv` ✅ — kolumner
  PSCH/PSCD/PSCA (Pinnacle closing), Max/Avg, säsonger från 2012. Perfekt backtest-facit.
- **ClubElo**: `api.clubelo.com/{Klubbnamn}` ✅ (CSV, full historik; namnformat utan å/ä/ö
  — alias-tabellen behövs här också).
- **Sofascore** (omtestad från hemma-IP 81.234.x, Telia — vm:s 403-tester gick via VPN):
  `api.sofascore.com` ger 403 för curl ÄVEN från hemma-IP (bot-skydd på klientnivå), men
  **riktig browser passerar**: `www.sofascore.com/api/v1/...` ger ren JSON i browser-kontext.
  Verifierade id:n: Allsvenskan = unique-tournament **40** (säsong 2026 = **87925**),
  Eliteserien = **20**. Flöde: `/unique-tournament/{ut}/seasons` →
  `/unique-tournament/{ut}/season/{sid}/events/last/{page}` →
  `/event/{id}/statistics` — innehåller **"Expected goals"** (verifierat: Örgryte–Häcken
  4–3, 2026-07-11 → xG 1.48–1.78) + Corner kicks + 41 fält till.
  Implementeras som Playwright-hämtare i Etapp 3 (körs efter avslutad omgång, ~16 matcher/
  vecka totalt — snällt tempo, paca anropen).
- **FBref**: curl 403, browser passerar Cloudflare — men INGEN xG för Allsvenskan
  (alla 22 tabeller sakna xG-kolumner). Skippa.
- **FotMob, historisk rekognosering:** gamla `/api/leagues` var borta (404),
  men slutsatsen att källan skulle skippas upphävdes 2026-07-25. Den nutida
  publika vägen används i `app/fotmob.py`; aktuellt capturekontrakt är v2.
- **Flashscore**: `d.flashscore.com/x/feed/...` svarar 200 med header `x-fsign: SW9D1eZo`
  — åtkomsten finns och feed-formatet är odokumenterat teckenprotokoll. Det
  parseras nu i `app/flashscore.py`/`flashscore_data.py` med fail-closed-
  koherensvakter; källan är i drift sedan 2026-08-01.
- **football-data.org**: `/v4/competitions` listar Allsvenskan (188 ligor, utan token) men
  match-datat svarar "check your subscription" — gratis-tiern täcker inte våra ligor. Skippa.

## Portar & processer

| Projekt | Backend | Frontend | Preview | launchd |
|---|---|---|---|---|
| svs (FRYST ARKIV 2026-07-20) | 8000 | 5173 | 5180 | urlastat (servrar stoppade, DB kvar) |
| vm (Boll boll kollen) | 8001 | 5174 | — | com.saman.vm.* (5 jobb) |
| **spelkompisen** | **8002** | **5175** | **5181** | com.saman.spelkompisen.{snapshot,pool,backend} |
