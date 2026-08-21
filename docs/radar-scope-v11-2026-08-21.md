# Metodkontrakt: live-radarns ligascope v11

**Version:** `chance-gap-shadow-v11`
**Ren start:** `2026-08-21T22:00:00Z`
**Föregående:** `chance-gap-shadow-v10` (2026-08-18T00:00:00Z →), oförändrad
som historik — inga rader flyttas.
**Beslut:** Saman bad 2026-08-21 att modellen skulle täcka de stora ligorna:
"Xg finns garanterat … Fixa för samtliga ligor." Ligue 1 var den enda av dem
som saknades helt.

## Verifierat scope

Ligue 1 läggs till. Varje identitet lästes ur källans EGET svar, aldrig gissad
ur ett mönster:

| Projektnyckel | UI | Pinnacle | Kambi/SvS | Sofascore UT | Flashscore | FotMob | Smarkets | football-data |
|---|---|---:|---|---:|---|---|---|---|
| `ligue_1` | Ligue 1 | 2036 | `football/france/ligue_1` | 34 | `FRANCE: Ligue 1` | `FRA`, `Ligue 1` | `france-ligue-1` | `F1` |

Matarligan `ligue_2` läggs in som resultatliga (`F2`) men INTE i `SOFA_UT`:
den fittas inte, så den ska inte kosta statistikanrop. Samma linje som
Championship, Serie B, Segunda och 2. Bundesliga.

`LEAGUE_PRIORITY["ligue_1"] = 0` — samma prioritet som de fyra övriga
Europaligorna. Utan raden faller radarn på `KeyError` i stället för att
sortera, vilket är avsiktligt: en ny liga ska inte kunna glida in i scopet
utan att någon tagit ställning till dess plats.

## Frysta delar

- Flashscore ankare, FotMob sekundär. Sofascore är resultat-/statistikkälla,
  inte bärande signalserie — oförändrat sedan v6.
- Signalnivåer, xG- och proxytrösklar, färskhet, källrankning, namnlänkning
  och matchtak är **oförändrade**. v11 ändrar enbart populationen.
- Live är fortsatt shadow: ingen påverkan på tips, Kelly, notiser, CLV eller
  systemförslag.
- Ligue 1 får sharp-värdering direkt (ren oddsjämförelse, ingen modellhypotes)
  men står ännu **utanför `MODEL_LEAGUES`** — se nedan.
- Ligue 1 ingår **inte** i V2.2:s `SCOPE_LEAGUES`.

## Varför v11 och inte en tyst utökning

Populationen som kan producera en signal ändras. Kohortregeln säger att en rad
hör till vN bara om vN-koden producerade den OCH den observerades i vN:s
deklarerade fönster; en utökning inne i v10 hade blandat två olika
populationer i samma blindkohort. `RADAR_V11_STARTED_AT` sattes framåt i tiden
(22:00Z) så att fönstret öppnar efter att koden är i drift, inte före.

`live_settlement` bär en egen spärr som vägrar settla när radarversionen inte
finns i dess capture-tidslinje. Den föll som avsett vid bytet och släppte
igenom först när `RADAR_V11_VERSION` skrevs in — spärren gjorde alltså sitt
jobb och ska inte tas bort.

## Modellstatus: ännu inte modelliga

Ligue 1 samlar resultat och xG men står utanför `MODEL_LEAGUES`. Skälet är
samma empiriska som spärrade de fyra Europaligorna fram till 2026-08-07: en
xG-viktad modell utan xG är sämre än ingen. Täckningen är i skrivande stund
**578/613 (94,3 %)**. De 35 luckorna är 34 Reims-matcher i 2024/25 plus en, och
alias-fixen som löser dem ligger i koden — bakfyllningen kunde inte köras klart
eftersom Sofascore började svara 403 efter kvällens anrop. Källans gräns
respekteras; luckorna fylls vid nästa körning.

Inträdet i `MODEL_LEAGUES` kräver därutöver en per-liga-kalibrerad `T`, och en
ny kalibrering är i sig en ändrad datagenererande process som kräver ett nytt
V2.2-manifest. Båda görs därför i EN ändring när täckningen är hel, inte i två.
