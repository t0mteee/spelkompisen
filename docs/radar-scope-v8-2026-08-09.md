# Metodkontrakt: live-radarns ligascope v8

**Version:** `chance-gap-shadow-v8`  
**Ren start:** `2026-08-09T17:15:00Z`  
**Beslut:** Saman bad 2026-08-09 att börja med högsta ligan i Danmark,
Belgien och Portugal, särskilt för livebevakningen.

## Ändringen

Tre ordinarie ligor läggs till:

| Projektnyckel | UI | Pinnacle | Kambi | Sofascore UT | Flashscore | FotMob |
|---|---|---:|---|---:|---|---|
| `danish_superliga` | Danska Superliga | 1913 | `football/denmark/superligaen` | 39 | `DENMARK: Superliga` | `DEN`, `Superligaen` |
| `belgian_pro_league` | Belgiska Pro League | 1817 | `football/belgium/jupiler_pro_league` | 38 | `BELGIUM: Jupiler Pro League` | `BEL`, `Belgian Pro League` |
| `primeira_liga` | Primeira Liga | 2386 | `football/portugal/primeira_liga` | 238 | `PORTUGAL: Liga Portugal` | `POR`, `Liga Portugal` |

Smarkets-identiteterna är `denmark-superliga`,
`belgium-first-division-a` och `portugal-primeira-liga`. Samtliga bar riktiga
kommande bettable event vid verifieringen 2026-08-09.

## Vad som inte ändras

- Flashscore är fortsatt ankare och FotMob sekundär; Sofascore är inte en
  bärande livekälla.
- Signalnivåer, xG-/proxytrösklar, färskhet, källrankning, länkning och
  matchtak är oförändrade.
- Live är fortsatt shadow och får inte påverka tips, Kelly, notiser, CLV eller
  systemförslag.
- Ligorna får ren sharp-värdering men ingen målmodell och ingår inte i V2.2.
- `SOFA_UT` ändras inte. Normaltidsfacit hämtas via `RESULT_ONLY_UT`, så
  V2.2-manifest v6:s featurefingeravtryck förblir intakt.

## Varför ny radarversion

Ett större ligascope ändrar populationen som kan ge captures och signaler och
kan påverka vilka matcher som ryms under ett provider-/tidsbudgetsvarv. Därför
får v7 och v8 aldrig slås ihop trots att trösklarna är identiska. Kod som kör
före den deklarerade starten stämplar v8 men blir `transitional`; den rena
v8-kohorten börjar först vid gränsen ovan.

Blindgrinden är oförändrad: minst 200 oddssatta och avgjorda signalmatcher,
minst 60 dagar och undre KI90 över noll innan liveinformationen kan ge stöd.

## Produktionskvitto

Första ordinarie varvet efter gränsen, 17:15Z, gav tre Flashscore- och tre
FotMob-captures med xG: Danmark, Belgien och Portugal en vardera. De länkades
till exakt tre kort. Belgienkortet nådde Följer och signaljournalen sparade
ett samtidigt observerat öppet live-Ö/U-pris. Därmed är hela kedjan verifierad
från providerliganamn via capture/länk till synlig signal och prisjournal.
