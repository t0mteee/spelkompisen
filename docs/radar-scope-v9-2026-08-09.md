# Metodkontrakt: live-radarns ligascope v9

**Version:** `chance-gap-shadow-v9`  
**Ren start:** `2026-08-09T18:00:00Z`  
**Beslut:** Saman bad 2026-08-09 att även ta med högstaligorna i Island och
Bolivia, särskilt för livebevakningen.

## Verifierat scope

Island fanns redan som `bestadeild` i ordinarie Oddset-vy och Flashscore-
radarn. Providerkedjan kontrollerades på nytt: Pinnacle 2102,
Kambi `football/iceland/urvalsdeild`, Sofascore UT 188, Flashscore
`ICELAND: Besta deild karla` och Smarkets observerade Island-slugs var rätt.
Kontrollen hittade däremot ett verkligt glapp: FotMobs aktuella namn är
`ISL` + `Besta deildin` (id 215), medan tabellen bara hade äldre varianter.
v9 lägger till namnet och UT 188 explicit i `TARGET_UT`. Ingen andra
Island-nyckel skapas.

Bolivia läggs till:

| Projektnyckel | UI | Pinnacle | Kambi/SvS | Sofascore UT | Flashscore | FotMob | Smarkets |
|---|---|---:|---|---:|---|---|---|
| `bolivian_primera` | Bolivianska Primera División | 5595 | `football/bolivia` | 16736 | `BOLIVIA: Division Profesional` | `BOL`, `Primera División` | `bolivia-primera-division` |

Alla identiteter utom ett aktivt SvS-event observerades direkt 2026-08-09.
Kambi-indexet hade inga Boliviaevent och inga av de provade specifika
ligavägarna fanns. Landsvägen är däremot giltig (200, tom roster), vilket gör
att insamlingen kan fånga framtida SvS-utbud utan att ett 404 gör ligan röd.
Pinnacle, Sofascore, Flashscore, FotMob och Smarkets bar aktuella ligor/event.

## Frysta delar

- Flashscore är fortsatt ankare och FotMob sekundär; Sofascore är endast
  roster/resultatkälla, inte bärande signalserie.
- Signalnivåer, xG-/proxytrösklar, färskhet, källrankning, länkning och
  matchtak ändras inte.
- Live är fortsatt shadow och får inte påverka tips, Kelly, notiser, CLV eller
  systemförslag.
- Bolivia får ren sharp-värdering men ingen målmodell och ingår inte i V2.2.
- Normaltidsfacit hämtas via `RESULT_ONLY_UT`; `SOFA_UT` och V2.2-manifest v6
  är oförändrade.

## Varför v9

Endast Bolivia är en faktisk scopeändring, men den ändrar populationen som kan
ge captures och signaler och kan påverka vilka matcher som ryms under
provider-/tidsbudgeten. Därför får v8 och v9 inte poolas. Kod som kör före den
deklarerade starten stämplar v9 men blir `transitional`; den rena v9-kohorten
börjar exakt vid gränsen ovan.

Blindgrinden är oförändrad: minst 200 oddssatta och avgjorda signalmatcher,
minst 60 dagar och undre KI90 över noll innan liveinformationen kan ge stöd.

## Observerad kodväxling

Ett redan startat v8-varv skrev färdigt efter att första v9-processen hade
börjat. Den verifierbara, entydiga växlingen låses därför till sista v8-capture
17:24:10Z och första v9-capture därefter 17:25:07Z. Processöverlappet och alla
v9-captures före den deklarerade starten 18:00Z är `transitional` och ingår
inte i någon ren kohort.

## Produktionskvitto efter ren start

Från 18:00Z samlade Flashscore/FotMob 207/199 Island-captures och 48/47
Bolivia-captures; alla Flashscore-rader bar xG. Island gav fyra signalögonblick.
Ett länkades till Oddset och fick SvS-livepris. Tre visades med stats men utan
pris eftersom providerparen `ÍA Akranes`/`Akranes`, `Stjarnan Gardabae`/
`Stjarnan` och `FH Hafnarfjördur`/`Hafnarfjordur` medvetet föll stängt.
De bidrar inte till odds-ROI. Att lägga alias är en identitetsändring och måste
förregistreras under en ny radarversion; v9 ändras inte i efterhand.
