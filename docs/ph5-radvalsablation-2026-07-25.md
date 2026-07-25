# PH5 — slår vårt radval baslinjerna? (2026-07-25, Opus 5)

## Problemet PH5 löser

PH3-ledgern mäter rätt sak men kan inte svara i tid. Poolspel ger ~1 datapunkt per
omgång, toppvinster är sällsynta, och i dag finns **6 settlade system med ROI
−100 %** — informationsfritt. En ROI-signifikans för radvalsmetoden dröjer i
praktiken år.

Samtidigt ligger 7 754 kompletta omgångar i settlementlagret med slutstreck,
öppningsodds, facit **och faktiska vinnarantal/utdelningar per nivå**. Det räcker
för att jämföra radvalsMETODER mot varandra med n i tusental — inte för att
förutsäga vad vi tjänar, men för att avgöra om vår metod är bättre än att spela
folkets rad.

## Vad detta är — och absolut inte är

* **Relativ jämförelse.** Alla armar ser exakt samma information (slutstreck +
  öppningsodds). Rättvist mellan armarna.
* **Ingen spelbar ROI.** Slutstrecket var inte känt när raden byggts på riktigt,
  och öppningsodds ≠ stängningsodds. Absoluta tal är en ÖVRE gräns. PIT-frågan
  mäts av `pit-v3` — aldrig här.
* **Egen kohort `final_only-radval-v1`**, hålls utanför pit-v3-manifestet.
* **Ofullständig utdelning räknas inte som noll.** Utvärderingen använder
  `pool_system_ledger.counterfactual_payout`, samma egna vinstutspädning som
  PH3: nivåer med 0 officiella vinnare gör facitet ofullständigt och omgången
  faller ur.
* **Ingen tredje EV-implementation.** Arm 1 anropar den riktiga
  `builder.build_ev_system` på ett `Draw` rekonstruerat ur settlementlagret.
  `build_ev_system` och frontendens `evalRows` ska hållas konsistenta; en tredje
  variant i ett analysskript hade garanterat drivit isär.

## Armarna (samma budget, samma antal rader)

| arm | rankning |
|---|---|
| `varderader` | vår metod: P(rad)^k × EV med κ, `value_weight=0.5`, strategi medel |
| `folkrad` | mest streckade kombinationerna (folkets rad) |
| `favoritrad` | högst sannolikhet enligt devigade odds |
| `slump` | slumpade rader ur samma kandidatmängd — golvet |

Kandidatmängden är topp-2 tecken per match (samma andas cap som byggaren);
`slump` sanity-checkar att uppsättningen kan skilja bra från dåligt.

## v1 UNDERKÄNDES AV SITT EGET SANITY-KRAV (körd 2026-07-25, 4 000 omgångar)

Krav 3 sa: *"`slump` MÅSTE ligga klart sämst. Gör den inte det mäter uppsättningen
ingenting och resultatet får inte tolkas."* Utfallet:

| produkt | n | slump | sämsta övriga | krav |
|---|--:|--:|---|---|
| stryktipset | 223 | −66,3 % | favoritrad −75,5 % | **faller** |
| europatipset | 505 | −24,2 % | varderader −75,6 % | **faller** |
| topptipset | 2 496 | −21,1 % | folkrad −34,3 % | **faller** |
| topptipsetstryk | 229 | **+45,5 %** | folkrad −48,0 % | **faller** |
| topptipsetextra | 523 | −68,2 % | favoritrad −50,8 % | ok |

**Ingen ROI-slutsats får dras ur v1.** Slumpen är inte bättre — den är tyngre i
svansen: KI för slump i Topptipset Stryk var [−69,7..+197,7]. ROI per omgång är
golvad vid −100 % och obegränsad uppåt, så en enda toppvinst bär hela
medelvärdet. Det är exakt den estimand-fällan som en gång gav "+6,6 %" när
sanningen var +2,65 %.

Att jag skrev sanity-kravet i förväg är enda skälet att felet syns nu i stället
för att bli ett publicerat "vår metod slår folket".

## v2 — parad design (specificerad före körning)

Omspecifikationen är motiverad av ett **validitetsbrott**, inte av att resultatet
inte passade. Den skrevs och kördes i denna ordning.

1. **Parad jämförelse per omgång.** Omgångens tur/otur delas av alla armar, så
   differensen `varderader − baslinje` tar bort den helt.
2. **Winsoriserad differens ±200 pp** — huvudsiffra och KI samma estimand.
3. **Andel omgångar där vi slår baslinjen** — rangstatistik som inte kan bäras av
   en enda toppvinst.
4. **Per-omgångs-ROI sparas i JSON**, så framtida omräkning aldrig kräver en ny
   1,5-timmarskörning.

Provkörning (Topptipset Stryk, n = 60) visar att designen fungerar:
`vs slump +16,6 pp [+1,8..+32,1]` — KI utan noll i rätt riktning, dvs
uppsättningen KAN skilja bra radval från slump när svansen inte styr.
`vs favoritrad/folkrad −6,4 pp` med KI över noll.

## Beslutsregel (förregistrerad, gäller v2)

Estimand: **parad winsoriserad differens** per omgång, omgången som
bootstrap-block, 90 % KI.

1. **Metoden är bättre** om `varderader` slår BÅDE `folkrad` och `favoritrad` och
   skillnadens undre KI-gräns > 0.
2. **Metoden är inte bättre** om den ligger i nivå med eller under baslinjerna.
   Då är dagens radval en komplicerad väg till folkets resultat, och den enkla
   åtgärden är att sänka komplexiteten — inte att leta fler features.
3. **Sanity-krav:** `slump` MÅSTE ligga klart sämst. Gör den inte det mäter
   uppsättningen ingenting och resultatet får inte tolkas.

## Preliminärt (n = 40, Topptipset — får INTE tolkas som facit)

| arm | ROI | 90 % KI | toppnivåträffar |
|---|--:|---|--:|
| favoritrad | +10,9 % | [−46,2..+78,9] | 11 |
| folkrad | +10,9 % | [−46,2..+78,9] | 11 |
| **varderader** | **+3,8 %** | [−42,4..+60,2] | **12** |
| slump | −55,7 % | [−94,2..+7,0] | 3 |

Sanity-kravet är uppfyllt: slump är golvet med marginal. Två observationer värda
att bekräfta i full körning:

* **`folkrad` och `favoritrad` gav identiska tal.** För Topptipsets 8 matcher
  ligger folkets mest streckade rad och marknadens favoritrad alltså på samma
  kombinationer. Om det håller i hela materialet betyder det att "slå folket" på
  RADNIVÅ inte kan göras genom att följa oddsen — de är samma sak.
* **Vår metod hade FLEST toppnivåträffar men lägre ROI.** Det är förenligt med
  att den sprider ut sig och därför har färre vinnande rader per träffad omgång.
  Om mönstret består är frågan inte "träffar vi" utan "hur många enheter har vi
  på träffen" — en portföljfråga, inte en signalfråga.

KI:na överlappar helt vid n = 40. Ingenting av detta är ett resultat än.

## Körning

```
cd backend && .venv/bin/python -B scripts/ph5_radvalsablation.py \
    --json ../docs/ph5-radvalsablation-2026-07-25.json
```

~0,17 s per omgång ⇒ hela materialet (alla fem produkter) på ~20 minuter.
Läser DB:n read-only och stör inte insamlingsjobben. `--product` och `--limit`
finns för delkörningar.
