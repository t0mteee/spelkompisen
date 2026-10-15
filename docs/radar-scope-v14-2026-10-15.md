# Metodkontrakt: live-radarns Flashscore-scope v14

**Version:** `chance-gap-shadow-v14`
**Ren start:** `2026-10-15T22:00:00Z` (midnatt CEST; kvällens sista cupmatcher
startade 19:00Z och inget annat i scopet pågår vid gränsen)
**Föregående:** `chance-gap-shadow-v13`, oförändrad historik
**Beslut:** koordinatorn-2026-10-15-flashscore-cuper, val 0 (Samans svar på
beslutssidan): lägg Champions League, Europa League och Conference League i
Flashscore-insamlingen och resultatsteget. Nations League och landskamper
(val 1) ingick inte i valet — de var redan i scopet sedan v13.

## Varför cuperna saknades hos Flashscore

`flashscore.LEAGUE_NAMES` hade kvalrubrikerna (`EUROPE: Champions League -
Qualification` osv., avlästa i augusti) och de nakna cupnamnen
(`EUROPE: Champions League`), som var ANTAGNA för ligafasen och aldrig
verifierades när den startade i september. Flashscores rubrik är
`EUROPE: Champions League - League phase` (Europa League och Conference League
likadant). Därför:

- `oddset_live_flashscore` har inga cupserier efter kvalet (sista
  2026-08-27); radarns cupbild kom bara från FotMob, som har ligafasen.
- Resultatsteget (`flashscore_data.refresh_recent_results`, livekassans
  rättning och timsteget `liveresultat`) fick aldrig någon cupkandidat.
- Agentens livekassa avstod alla cupmatcher med "inget matchläge från
  Flashscore" (18 CL-, 8 EL- och 10 ECL-matcher med livepriser, 0 spel).

## Verifierade identiteter

Avlästa ur Flashscores egna dagsfeeds 2026-10-15 (offset 0 och 7: EL/ECL
15/10 och 22/10, 18 matcher vardera; offset 5–6: CL 20–21/10, 9 per dag):

| Flashscore-rubrik | Projektnyckel |
|---|---|
| `EUROPE: Champions League - League phase` | `champions_league` |
| `EUROPE: Europa League - League phase` | `europa_league` |
| `EUROPE: Conference League - League phase` | `conference_league` |

Medvetet utanför: `EUROPE: UEFA Youth League - League phase`, damernas och
ungdomslandslagens turneringar, `UEFA Regions' Cup` och `Premier League
International Cup`. Slutspelets rubriker (februari) läggs till först när de
syns i feeden — aldrig gissade. De nakna cupnamnen står kvar i tabellen
(ofarliga, och en ändring vore en ändring i en annan kohorts kod).

## Vad som ändras

- **Källvalet för cupmatcherna:** Flashscore kan nu väljas före FotMob enligt
  den oförändrade regeln (strukturell fälttäckning, sedan Flashscore →
  FotMob). Det ändrar den datagenererande processen för cupernas signaler och
  kräver en ren kohort, fast cuperna redan var i scopet.
- **Resultatsteget:** cupmatcherna får Flashscores färdigresultat. Prov
  2026-10-15 mot de 54 kommande cupmatcherna i Oddset (15–22/10): 24 länkas
  strikt på båda lagen, 27 ensidigt (livekassans steg: samma liga, avspark
  ≤ 15 min, ett lag lika, en kandidat), 3 inte alls — KAA Gent–AGF Aarhus
  (Flashscore "Gent"/"Aarhus"), FC Köpenhamn–S.C. Braga ("FC Copenhagen"/
  "Braga") och Sabah FK–Borussia Dortmund ("Sabah"/"Dortmund"). De rättas av
  nattens modelldata eller ett namnalias i ett senare beslut.

## Vad som inte ändras

Signalnivåer, xG-/proxytrösklar, providers, källrankning, identitetsregler
(`_same_team`, `LIVE_TEAM_ALIASES`), prisprocess, matchtaket (60) och
`LEAGUE_PRIORITY` (cuperna har haft prioritet 0 sedan 2026-07-28). Sofascore är
fortfarande urkopplad ur radarn. Oddsets ligor, V2.2 och modellen rörs inte.

## Gränsen

Koden gäller i samma sekund filen sparas i serverns arbetskopia (driftsatt
cirka 18Z 2026-10-15). Kvällens cupmatcher 19:00Z observeras alltså redan av
Flashscore, men som `transitional` — de hör till ingen kohort. Livekassan får
matchläget ändå; kohortregeln gäller radarns facit, inte agentens indata.
