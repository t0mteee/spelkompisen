# Överlämning från Codex till Claude — 2026-07-24

Detta är den aktuella arbetsöverlämningen till Claude. Läs först
`CLAUDE.md` och statusblocket överst i `docs/plan.md`. Använd
`docs/overlamning-2026-07-23.md` som historisk changelog; duplicera inte dess
äldre detaljer här.

> **Codex 2026-07-24 — aktuell överlämning, läs denna ruta först.**
>
> **Tillägg 2026-07-26 — läs före äldre punkter.** FotMob-fallbacken visar nu
> hela sin skottserie även utan xG (`signal.stats_source`), verifierat live
> för GIF Sundsvall–Falkenberg. En färsk FotMob-serie blir även ett eget
> `fotmob:<id>`-kort när Sofascore saknar matchen helt. Källvalet rankar
> faktisk statistik, inte om FotMob råkar lämna minuten tom i halvtid; då får
> endast matchklockan kompletteras från den länkade raden. En allvarlig Oddset-identitetskrock
> (Karlsruhe–Inter sammanblandad med Novara–Internazionale U23) är härdad med
> per-lagströskel, write-once/globalt unika provider-id:n och
> `data_conflict`-karantän över värde/steam/modell/ledger/CLV/notiser.
> Sanering + backup är körd; `DATA_VERSION=3`. Ändra inte tillbaka till
> medelvärdesmatchning eller overwriting-upsert. Läs
> `docs/oddset-identitetsaudit-2026-07-26.md` och senaste posten i
> `docs/db-atgarder.md`. Aktiva versioner är nu sharp `s-95e14fca` och modell
> `m-c4ee7c5d`; förvänta 0 aktiva cases tills nästa capturefönster — bakfyll
> inte och återanvänd inte äldre version. Tvåankarpaketet är 13 mätta/9
> stängda efter att kontaminerade matcher togs bort. Ändringarna är ännu inte
> committade. Slutverifiering: 311 backendtester, grönt frontendbygge och
> grönt live-API efter backendomstart.
>
> Saman bad Codex genomföra samtliga sex eftergranskningspunkter. De är nu
> implementerade och verifierade; full metodrapport:
> `docs/pool-pit-v2-2026-07-24.md`. Ingen poolfeature eller κ-korrektion har
> promoverats till runtime.
>
> **1. PH2 presence + `pit-v2`.** Rotfelet var att
> `snapshots`/`sharp_snapshots` bara skriver vid förändring, medan PH0/PH2
> kallade senaste förändring för senaste observation. Ny
> `pool_market_capture` skriver varje lyckad SvS-/Pinnacle-läsning per event,
> även oförändrat; lyckad `not_listed` sparas, källfel gör det inte.
> `pit-v2` kräver capture före cutoff och timing h24/h3/m20 = 45/45/10 min.
> Stale värden finns diagnostiskt men blir inte features. Reversal kräver
> färsk capture även kring startpunkten. **Bakfyll aldrig pit-v1 till v2.**
>
> **2. PH3 kontrafaktiskt facit.** Utdelning räknas nu från observerad
> nivåtpottsproxy `winners×amount` och delas på `winners+egna_vinnarrader`.
> Publicerad bruttovinst sparas separat. Noll officiella vinnare = okänd
> rolloverpott, `payout/ROI=NULL`, aldrig nollförlust. Summary är per
> produkt×config×horisont; ROI använder endast timely, lösbara och komplett
> settlade rader. Sena/ofullständiga redovisas separat. GET
> `/api/pool/systems` är rent läsande; snapshotjobbet settlar.
>
> **3. Riktig forward-gate.**
> `docs/pool-ph4-forward-manifest.json` fryser experiment
> `pool-streckmove-v1`: `pit-v2`, h3, kandidat d mot b, forwardstart
> 2026-07-25, 15 tidigare v2-omgångar + minst 40 forward-evaluerade per
> produkt, hela KI90<0 på primärprodukten och ingen signifikant försämring
> på övriga. `ph4_ablationer.py` separerar development/forward i både volym
> och bootstrap, exkluderar missing i stället för nollimputering,
> standardiserar på training-only och redovisar konvergens. Statusfil:
> `docs/ph4-forward-status.json`, nu 0 v2/Promotion NEJ.
>
> **4. Jackpotproveniens.** Jackpot-endpointen hämtas före capture/frysning.
> Ingen fallback till `draw.jackpot/fund`. Proveniens:
> verified_endpoint/missing/endpoint_error. Första livevarvet gav 2
> verifierade och 10 missing; 109 äldre draw-snapshots är
> legacy_unverified.
>
> **5. PH4/UI/API.** Eraanalysen jämför nu icke överlappande före-2024 mot
> 2024+ (`docs/ph4-kalibrering-era-v2.json`); lägre modern κ är association,
> inte automatiskt trendbevis. V3 uppdaterar Idag varannan minut, sorterar
> nästa omgång efter stängning, visar historik-KPI över hela DB:n och senaste
> 400 som tabell, har korrekt payouttext/per-produkt-ROI och bättre
> tangentbordsstöd. V3 lazy-loadas så App↔AppV3 inte är en synkron cirkel.
>
> **6. Liveinsamling startad.** Migrationen kördes via
> `scripts/migrera_pool_capture_v2.py`, backup + DB-logg finns i
> `docs/db-atgarder.md`. Första ordinarie snapshotvarvet skrev 212
> presence-rader (106 SvS; Pinnacle 95 matched + 11 not_listed).
> `pit-v2=0` och `pool_system_ledger=0` är just nu KORREKT: passerade cutoffs
> före införandet får inte bakfyllas och nästa frysning har ännu inte nått
> T−3h.
>
> **Verifierat:** 163 backendtester, frontend production build,
> `git diff --check`, browser klassisk→v3/Idag/Historik utan console-fel,
> produktions-DB `integrity_check=ok`. Backend är omstartad på 8002 med nya
> koden. Ändringarna är **inte committade** eftersom Saman inte bad om commit
> i denna beställning.
>
> **Det Claude bör göra härnäst:**
>
> 1. Låt launchd arbeta; ändra inte manifest/toleranser efter första
>    forwarddata.
> 2. Efter första passerade horisont: auditera att capture-lagg,
>    `svs_eligible`/`sharp_eligible` och featurevärden är rimliga.
> 3. Efter första T−3h-frysning och settlement: verifiera rows_hash,
>    jackpot_source, egen utspädning och att summary endast räknar
>    `n_evaluable`.
> 4. Kör `scripts/ph4_ablationer.py` som statusrapport vid behov; 0/låg volym
>    är väntat och får inte “lösas” med bakfyllning.
> 5. Nästa fristående forskningsfråga är `startOdds`-semantik. Håll den borta
>    från rörelsefeatures tills providerbetydelsen bevisats.
> 6. Ingen runtimeändring för nivå-κ, svansmodell eller streckrörelse före
>    respektive gate och PH3-championjämförelse.

## Historisk logg från tidigare pass

Avsnitten nedan beskriver tidigare leveranser och ska läsas som bakgrund.
Vid konflikt gäller den aktuella överlämningen ovan, `CLAUDE.md` och
statussammanfattningen i `docs/plan.md`.

> **Claude 2026-07-24: Beställning 1 LEVERERAD** (se sektionen nedan för
> ursprungskraven). Genomförande: `visible_in_ui`-flagga på de fyra
> forskningsligorna i `oddset.py`; `VISIBLE_LEAGUE_KEYS` respektive
> `ACTIONABLE_LEAGUE_KEYS` (f.d. `PUBLIC_LEAGUE_KEYS`) håller synlighet och
> actionability isär. Ordinarie payload visar research-matcher med odds/
> prisålder/rörelser, `research=True` och strippade värde-/modellfält;
> `_research_next_round` visar ligans nästa omgång när 10-dagarsfönstret är
> tomt (annars hade premiärerna 16/8+ varit osynliga till 6/8). UI: 🔬-badge
> på filterknappar/matchrader/radar, legendtext, `Bara signaler` exkluderar
> research, spelkort/amber-lista/notiser/CLV orörda. Insamlingsvägen
> (`include_research=True`), V2.2-versioner och v22audit är byte-oförändrade;
> ledgern gav redan research enbart sharp+V2.2-capture. Alla acceptanskriterier
> uppfyllda: 135 backendtester gröna (3 nya synlighet≠actionability-tester),
> frontendbygge grönt, browser-verifierat desktop + 390 px utan sidscroll,
> `v22audit` fortsatt `actionable nej · notiser nej`.
>
> **PH0 är också klar samma natt** (läsande, inga modell-/DB-ändringar):
> `backend/scripts/ph0_kallaudit.py` → `docs/ph0-kallaudit-2026-07-24.md`
> (+ JSON med per-omgång-matris). Kort: kohort A = 86 passerade omgångar med
> stark T−20m/close-täckning (sharp T−24h är svagast, redovisas som lagg);
> kohort B = result/slutstreck/omsättning åtkomliga hela vägen till 2013
> (Stryktipset, exakt gräns #4267) resp. ≥2014/2016/2024 för övriga, aktuella
> odds flyktiga (kan aldrig bakfyllas), `startOdds` t.o.m. ~2022 och
> osemantiserad, API-drawState korrekt trots frusen lokal `draws.state`,
> 0 × 429 på 157 requests @ 0,35 s. PH1-schemaförslaget med testfall ligger i
> `docs/ph1-settlement-schema-forslag-2026-07-24.md`.
>
> **PH1 GENOMFÖRD 2026-07-24** (Samans "kör vidare med backloggen" = grönt
> ljus, förslagets rekommendationer följda: fullt backfill-djup + framåtriktad
> settlement i snapshotvarvet): `app/pool_settlement.py`, migration med backup,
> resumable backfill, 10 tester, `/api/pool/history`. Rapport och slutsiffror:
> `docs/db-atgarder.md`. **UI v3-experimentet** levererades samtidigt
> (`frontend/src/AppV3.jsx`, växel i v2-headern, v2 orörd/default): Idag-
> översikt, Poolspel-stegflöde med återanvända komponenter, Oddset, Historik
> (settlementlagret synligt med KPI:er/sparkline/matchfacit).
>
> **PH2 + PH3 GENOMFÖRDA 2026-07-24** (samma natt, efter Samans "kör
> vidare"): `app/pool_dataset.py` (PIT-features `pit-v1`: 256 horisontrader
> / 98 observerade omgångar; horisont utan observation byggs aldrig;
> `pool_draw_snapshot` = framåtriktad omsättningsserie) och
> `app/pool_system_ledger.py` (förregistrerad benchmarkmatris fryses vid
> T−3h/T−20min i snapshotvarvet, settlas mot riktiga utdelningsnivåer,
> `/api/pool/systems`; toleranser 30/10 min per varvkadens; Bomben ingår
> ej). 11 nya tester (156 totalt).
>
> **PH4-analyspasset kört 2026-07-24** (Samans "kör klart PH4"):
> `scripts/ph4_kalibrering.py` + `scripts/ph4_ablationer.py` →
> `docs/ph4-analys-2026-07-24.md` (+ JSON-rådata). Huvudfynd: favoriter
> överstreckade i alla produkter; κ>1 överallt (EV:s medvinnarterm
> optimistisk, effekten avtagit men kvar 2024+); U-formad folkkorrelation
> (fetare svansar); ablationerna slår inte rå marknad (streckrörelse =
> hypotes). Ingen runtime-ändring — förregistrerad gate + challengers via
> PH3-ledgern. Samma dag: scanfönster-fix i `_scan_draws` (back 4→8 —
> dagens topptipsomgångar föll UNDER hint-fönstret och saknades i
> omgångsväljaren), Idag-kortet väljer tidigaste framtida spelstopp, och
> Systemfacit fick egen UI (Idag-kort + panel i Historik med djuplänk).
> Kvar: `startOdds`-semantikverifiering, gate-omprövning i höst.

## Kort lägesbild

Senaste genomförda arbetspaketet är commit:

`b596295 Utöka V2.2 med forskningsligor`

V2.2 omfattar nu Allsvenskan, Premier League, Serie A, La Liga och Bundesliga.
De fyra nya ligorna är i nuläget `research_only`: de samlas in, men filtreras
ur ordinarie Oddset-API/UI och får inte skapa vanliga modellprediktioner,
värdesignaler, notiser eller CLV-facit.

För Europaligorna finns:

- 6 292 historiska fria resultatrader över toppliga + respektive andradivision;
- 78 lag med verifierade Sofascore-identiteter och basarenor;
- 3 441 lag-event för PIT-säker vila, belastning och reseproxy;
- 39 aktuella premiärmatcher från Pinnacle + Kambi efter identitetsmigrering;
- 38/39 kompletta V2.2-rader. Bayern–Stuttgart saknar giltiga ClubElo-
  intervall och ska förbli explicit missing tills källan publicerar data.

Andradivisionerna är fit-only: Championship, Serie B, Segunda och
2. Bundesliga hjälper nyuppflyttade lag men är inte egna V2.2-målligor.

Frysta versioner:

- V2.2-shadow `v22-7450a9ff`;
- features `f22-9c205e9c`;
- forskningsmodellkälla `m22-957459bc`;
- WP9c-policy `wp9c-5d1a7ddb`.

Ordinarie signalversioner ändrades inte:

- sharp base/signal `s-776ca0e0` / `s-a4e45b6c`;
- modell base/signal `m-c00f8a09` / `m-d82792f7`.

132 backendtester och frontendbygget är gröna. V2.2-API:t redovisar fem ligor,
men `actionable=false`, `notifications=false` och `regular_ui=false`.
Före träningsgaten är `p_v22 == p_sharp` exakt. Träningsgaten är 300 avgjorda
kompletta matcher per horisont, minst 50 per liga och minst 42 dagars span.

Viktiga filer:

- `docs/model-v2.2-multileague-forward-manifest.json`
- `docs/v2.2-multileague-start-2026-07-23.md`
- `backend/app/oddset_v22.py`
- `backend/scripts/auditera_v22_multiliga.py`
- `backend/scripts/forbered_v22_multiliga.py`
- `backend/scripts/migrera_v22_research_identitet.py`

## Samans två nya beställningar

### 1. Visa Europaligorna i den vanliga Oddset-vyn

Saman vill nu se Premier League, Serie A, La Liga och Bundesliga tillsammans
med Allsvenskan, Superettan och övriga ligor i ordinarie liga-/matchvy. De ska
alltså inte bara vara osynlig V2.2-shadowdata.

Detta är ett produktbeslut om **synlighet**, inte ett automatiskt beslut om att
V2.2 är godkänd som spelmodell.

#### Gör inte bara `research_only=False`

Den flaggan används i dag som flera olika skydd samtidigt. Ett naket byte kan
oavsiktligt släppa in de nya ligorna i:

- ordinarie modelledger och signalgrupper;
- värdelistor, Kelly och “Bara signaler”;
- notiser;
- CLV-facit;
- dyr deep-/frånvaroinsamling.

Separera i stället minst dessa begrepp:

1. `visible_in_ui`: matcherna och ligafiltren visas i vanliga Oddset-vyn;
2. `collect_research`: V2.2 fortsätter samla sitt frysta forskningsunderlag;
3. `actionable`: får skapa spelbar signal, Kelly, notis och CLV.

Rekommenderad första leverans:

- visa de fyra ligorna som vanliga valbara ligafilter och matchkort;
- visa befintliga Pinnacle-/SvS-odds, prisålder och oddsrörelser;
- märk ligan/kortet diskret med exempelvis “Forskningsliga” eller
  “V2.2 samlar data”;
- håll V2.2-sannolikheter, Kelly, notiser och CLV icke-actionable;
- låt inte forskningsmatcherna försvinna när “Bara signaler” är av;
- behåll V2.2-manifest, horisonter och versionsidentiteter oförändrade.

Om rena marknadsjämförelser mellan färsk direkt Pinnacle-1X2 och SvS ska visas
som informationspills går det bra, men de får inte se ut som metodgodkända
gröna spel eller loggas i facitet utan ett separat uttryckligt beslut. V2.2:s
modelloutput ska fortfarande inte läsas av ordinarie UI-vägar.

Aktuella kodställen:

- `backend/app/oddset.py`: `research_only`, `PUBLIC_LEAGUE_KEYS`,
  `RESEARCH_LEAGUE_KEYS`, `matches_payload(include_research=False)` samt
  public/research-splitten i collect;
- `backend/app/oddset_ledger.py`: research ska fortsatt få V2.2-capture men
  inte ordinarie model-capture;
- `frontend/src/App.jsx`: ligafilter, Oddset-listor, tomtillstånd och
  “Bara signaler”;
- `frontend/src/App.css`: desktop + 390 px.

Acceptanskriterier:

- `/api/oddset/matches` listar de fyra nya ligorna och deras kommande matcher;
- ordinarie sex ligor fungerar oförändrat;
- forskningsligorna syns på desktop och 390 px utan sidscroll;
- `v22audit` och `/api/oddset/v2-shadow` är fortsatt icke-actionable;
- forskningsligorna skapar inga ordinarie model-captures, notiser eller
  CLV-rader;
- test täcker att synlighet och actionability är två oberoende egenskaper;
- frontendbygge och hela backend-sviten är gröna.

### 2. Historiska slutomgångar för Stryktipset, Europatipset och Topptipset

Saman vill analysera förhållandet mellan:

- odds och oddsrörelser;
- streck och streckrörelser;
- matchutfall;
- omsättning, vinnare och faktisk utdelning;
- vilka automatiska systemförslag som hade fungerat bäst.

Ja, detta är ett bra nästa dataspår. Det kan förbättra flera olika lager, men
de får inte blandas ihop:

1. utfallssannolikheten per match;
2. modellen för hur spelarkollektivet streckar;
3. omsättnings-/medvinnare-/utdelningsmodellen;
4. portfölj- och radvalet för automatiska system.

En hög utdelning är inte en prematch-feature. Den är facit för lager 2–4.

## Vad som redan finns för poolspelen

`snapshots` lagrar observerade förändringar i SvS-odds och streck.
`sharp_snapshots` lagrar observerade Pinnacle-rörelser. Därför finns redan ett
värdefullt forward-material:

| Produkt | observerade omgångar | passerat spelstopp | snapshotrader | sharp-rader |
|---|---:|---:|---:|---:|
| Stryktipset | 8 | 7 | 7 457 | 4 026 |
| Europatipset | 13 | 12 | 16 020 | 7 239 |
| Topptipset | 58 | 49 | 47 183 | 15 960 |
| Topptipset Extra | 12 | 11 | 10 756 | 4 939 |
| Topptipset Stryk | 7 | 6 | 5 777 | 2 811 |
| **Totalt** | **98** | **85** | **87 193** | **34 975** |

Av de 85 omgångarna som passerat spelstopp har 82 en lokal snapshot högst tre
timmar före stopp. Materialet är alltså redan användbart för riktiga rörelser,
även om Stryk/Europa fortfarande har få omgångar.

Viktiga begränsningar:

- `draws.state` står ofta kvar som `Open`, eftersom raden inte uppdateras efter
  avgörande. Använd inte fältet som settlement-facit. Kontrollera
  `reg_close_time` och resultat-endpointen.
- `value_log` innehåller facit bara för tidigare flaggade selektioner, inte en
  fullständig settlement av varje match, prisnivå och system.
- `SvenskaSpel.get_result()` kan redan läsa ut matchfacit, strukna matcher,
  slutomsättning, vinnare och utdelning per nivå, men uppgifterna lagras inte
  som ett komplett immutable facit.
- befintligt `cli.py backtest` hämtar äldre omgångar ad hoc. Det är användbart
  som kontroll men inte ett versionerat PIT-dataset.

## Metodregel: två historikkohorter

Håll två kohorter tydligt åtskilda:

### A. Lokalt observerade omgångar

De 85 passerade omgångarna har verkliga tidsstämplade snapshots. För dessa får
features rekonstrueras “as of” fasta horisonter, till exempel T−24 h, T−3 h och
T−20 min. Välj senaste faktiskt observerade punkt före horisonten och redovisa
coverage/timing.

### B. API-bakfyllda äldre omgångar

Äldre slutomgångar kan ge slutodds, slutstreck, facit, omsättning, vinnare och
utdelning. De kan användas för statisk kalibrering, produktbias, κ och
utdelningsanalys.

De får **inte** påstås ha odds- eller streckrörelser. Ett finalvärde får aldrig
kopieras bakåt till en låtsad T−24h-snapshot. `startOdds` får inte behandlas som
en tidsstämplad rörelsepunkt innan dess exakta providersemantik verifierats.

Alla rapporter och modellrader ska bära `cohort=observed_pit` eller
`cohort=final_only`.

## Föreslaget arbetspaket för poolhistorik

### PH0 — käll- och coverage-audit, läsande

- verifiera hur många äldre draw- och result-endpoints som är åtkomliga för
  varje produkt/variant och hur rate limiting beter sig;
- inventera kompletta events, odds, streck, utfall, turnover och distribution;
- bygg en coverage-matris per produkt, omgång och potentiell horisont;
- redovisa inställda/strukna matcher, namnbyten och Topptipset-varianter;
- gör inga modelländringar i detta steg.

### PH1 — immutable settlementlager

Lägg till nya tabeller via migrationsskript, backup och rapport i
`docs/db-atgarder.md`. Ändra inte semantiken i befintliga `snapshots`.

Rekommenderad normalisering:

- `pool_draw_settlement`: produkt, omgång, spelstopp, tid då settlement först
  observerades, slutomsättning, radpris, källversion, hämtad tid och
  payload-hash;
- `pool_event_settlement`: eventnummer, lag, avspark, utfall, cancelled samt
  slutvärden från leverantören med tydlig provenance;
- `pool_payout_tier`: rättnivå, antal vinnare och belopp;
- vid behov separat råpayload eller reproducerbar payload-hash, men inga
  tysta overwrite.

Backfill ska vara idempotent och resumable. Misslyckade omgångar ska förbli
retrybara. Produkt-sluggen måste bevaras för `topptipset`,
`topptipsetextra` och `topptipsetstryk`; gruppera dem först i analyslagret.

### PH2 — PIT-dataset med fasta horisonter

Bygg en läsande dataset-builder som fryser per omgång/horizont:

- devigad SvS-/Pinnacle-sannolikhet och avvikelsen mellan dem;
- oddsens första→as-of-rörelse i sannolikhetspunkter;
- strecknivå och streckrörelse;
- gapet `p_marknad − p_folket`, dess förändring och eventuell sen reversal;
- kupongens koncentration/entropi, favorittryck och uppskattade svårighet;
- omsättningsprognos och jackpot endast om de verkligen var kända vid `as_of`;
- källtäckning, ålder och alla missing-fält.

Använd aldrig finalodds, finalstreck, facit, vinnare eller utdelning som input
till en tidigare horisont.

### PH3 — automatisk systemledger och champion-baseline

Frys vad dagens byggare faktiskt hade föreslagit före spelstopp:

- produkt, omgång, horisont, budget, strategi och `value_weight`;
- kod-/modell-/dataversion;
- systemtyp och hash av de konkreta raderna;
- input-coverage och orsaken om förslag inte kunde byggas.

Förregistrera en liten benchmarkmatris i stället för att optimera alla UI-
reglage i efterhand. Förslag: 50 kr som primär budget och högst ett fåtal
sekundära budget-/risklägen. Samma konkreta rader ska kunna återskapas.

Settla varje system mot riktigt matchfacit och faktisk vinstplan/utdelning.
Jämför alltid med dagens oförändrade byggare som champion.

### PH4 — modellförsök först efter baseline

Testa separata, begripliga ablationer:

- dagens modell;
- endast marknad;
- marknad + strecknivå;
- marknad + streckrörelse;
- marknad + odds-/sharp-rörelse;
- full kombination.

Använd walk-forward i omgångsordning, aldrig slumpmässig train/test-split.
Redovisa per produkt först och aggregat bara som översikt. Stryktipset och
Europatipset har 13 matcher/flera prisnivåer; Topptipset har 8 matcher och en
annan vinstplan, så ett totalsnitt får inte dölja produktskillnader.

Primära mått bör vara:

- logloss/Brier/kalibrering för matchutfall;
- sannolikhetsmassa täckt och korrektnivåer för systemen;
- faktisk return och pluschans, men med blockbootstrap per omgång;
- kalibrering av prognostiserade medvinnare och utdelningar;
- coverage och antal oberoende omgångar.

ROI och enstaka jackpotomgångar har mycket hög varians. Ingen ny runtime-policy
ska promoveras på bara ett positivt medelvärde eller samma material som användes
för att välja features/trösklar. Förregistrera gate och håll ett senare
out-of-time-fönster.

## Rekommenderad ordning för Claude

1. Gör Europaligorna synliga i vanliga vyn med separat actionability-vakt.
2. Kör PH0-auditen och skriv en kort käll-/coverage-rapport.
3. Föreslå exakt settlement-schema och testfall.
4. Genomför PH1 med skript + backup + `docs/db-atgarder.md`.
5. Bygg PH2/PH3 och producera en baseline-rapport innan någon modellparameter
   ändras.
6. Låt V2.2:s existerande forwardinsamling fortsätta orörd under arbetet.

## Regler som gäller under hela fortsättningen

- inga automatiska spel;
- endast gratiskällor;
- rör aldrig `/Users/saman/svs` eller `/Users/saman/vm`;
- notifieringsspåret förblir pausat;
- DB-ändring = skript + backup + rapport, aldrig ad hoc-SQL;
- resultat/utdelning är facit, inte prematch-input;
- missade historiska snapshots bakfylls aldrig;
- synlig liga betyder inte automatiskt grön eller actionable;
- uppdatera `docs/plan.md` och denna överlämningskedja efter avslutat
  arbetspaket.
