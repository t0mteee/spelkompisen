# Metodkontrakt: live-radarns ligascope v13

**Version:** `chance-gap-shadow-v13`
**Ren start:** `2026-10-03T08:45:00Z` (10:45 CEST, förmiddagsluckan utan pågående
match i scopet)
**Föregående:** `chance-gap-shadow-v12`, oförändrad historik
**Beslut:** Saman frågade 2026-10-02 under landslagsuppehållet varför liveodds och
matcher för landskamper saknades, och beställde 2026-10-03 att de läggs till i
Oddset och liveradarn.

## Varför landslagen saknades

Oddsets ligalista (`oddset.LEAGUES`) och providrarnas livekartor innehöll bara
klubbligor, Europacuperna och klubblagens träningsmatcher. Det var ett gammalt
scopebeslut, inte källbrist: Pinnacle, Svenska Spel, Flashscore och FotMob har
alla landskamperna.

## Verifierade identiteter

Varje identitet lästes ur källans eget aktuella svar 2026-10-03, för FotMob och
Flashscore över dagslistorna 3–6 oktober. Inga id:n eller rubriker är
mönsterhärledda.

| Projektnyckel | UI | Pinnacle | Kambi/SvS | Smarkets | Flashscore | FotMob |
|---|---|---|---|---|---|---|
| `nations_league` | Nations League | 200719, 200721, 200726, 200727 (A–D) | `football/uefa_nations_league` (23 event) | saknas (0 av 50 event) | `EUROPE: UEFA Nations League - League A/B/C/D` | `INT`, `UEFA Nations League A–D Grp. n` (14 rubriker, primaryId 9806–9809) |
| `landskamper` | Landskamper | 2117 | `football/international_friendly_matches` (5 event) | saknas | `WORLD: Friendly International` | `INT`, `Friendlies` (114) |

Medvetet utanför: damernas `WORLD: Friendly International Women`, CONCACAF:s
Nations League och ungdomslandslag (U21-kval, U20).

## Vad som ändras

- **Populationen:** Nations League (prioritet 0, som ordinarie ligor) och
  landskamper (prioritet 1, som träningsmatcher) kan nu producera livesignaler.
- **Identitet:** `_same_team` avgör på FIFA-landskod (`app/landslag.py`) när BÅDA
  namnen är kända landslag. Oddset visar Svenska Spels svenska namn ("Kroatien"),
  providrarna engelska ("Croatia"), och "Irland" ligger inuti "Nordirland". Ett
  klubbnamn är aldrig ett exakt landsnamn, så klubbligornas länkning är oförändrad;
  `test_landslag_lankas_pa_landskod_och_klubbar_som_forut` låser båda.
- **Spärr:** landskamper går genom samma Oddset-spärr som klubbarnas
  träningsmatcher (`GATED_LEAGUES`). Flashscores dagsfeed bar 24 landskamper,
  Oddset 5–7; utan spärren hade obskyra matcher ätit matchtaket.

## Vad som inte ändras

Signalnivåer, xG-/proxytrösklar, providers, källrankning, prisprocess (ROI-priset
från v10) och matchtaket. Sofascore är fortfarande urkopplad ur radarn.

## Oddset-sidan (samma dag)

Ligorna samlas som ren sharp-väg utan modell (ingen landslags-Elo eller xG) med
egna utforskande facitgrupper. Kopplingen mellan källorna sker på landskod i alla
steg, aldrig namnlikhet; okända namn rapporteras som `okanda_landslag`. Prov mot
tom databas: 26 av 31 matcher kopplade till båda källorna; de övriga saknades hos
en källa (Ryssland och Belarus utan Svenska Spel-utbud, Sri Lanka–Djibouti, två
matcher 6/10 som Pinnacle inte listat än).

## Gränsen

Koden gäller i samma sekund filen sparas. Driftsättningen sker 10:30 CEST,
strax före 08:45Z; observationer mellan driftsättningen och gränsen blir `transitional` och
hör till ingen kohort. Ingen match i scopet pågick då.
