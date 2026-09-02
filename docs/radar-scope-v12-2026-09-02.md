# Metodkontrakt: live-radarns ligascope v12

**Version:** `chance-gap-shadow-v12`
**Ren start:** `2026-09-02T22:00:00Z` (midnatt CEST)
**Föregående:** `chance-gap-shadow-v11`, oförändrad historik
**Beslut:** Saman bad 2026-09-02 att Championship ska följas live eftersom
ligan ofta ingår på Stryktipset och Europatipset.

## Varför ligan saknades

Championship fanns bara i `FD_SEASON_CODES` som historisk resultat-/matarliga.
Den saknades i `oddset.LEAGUES` samt Flashscores och FotMobs explicita
livekartor. Det var alltså ett gammalt scopebeslut, inte källbrist. Effekten
var att en Championship-match kunde få poolodds men aldrig komma in i den
ordinarie Oddset-listan eller liveradarns två bärande providerserier.

## Verifierade identiteter

Varje identitet nedan lästes ur källans eget aktuella svar 2026-09-02. Inga
id:n eller sökvägar är mönsterhärledda.

| Projektnyckel | UI | Pinnacle | Kambi/SvS | Ninja/Altenar | Smarkets | Flashscore | FotMob | Resultat |
|---|---|---:|---|---:|---|---|---|---|
| `championship` | Championship | 1977 | `football/england/the_championship` | 2937 | `england-championship` | `ENGLAND: Championship` | `ENG`, `Championship` (938218) | football-data `E1` |

Kontrollbevis i det aktuella utbudet:

- Pinnacle: `England - Championship`, 61 matchups; 5938 är den separata
  hörnligan och används inte som huvudidentitet.
- Kambi/Svenska Spel: 16 event med riktiga Championship-lag.
- Ninja: id 2937 gav 12 engelska event; id 2962 gav skotska lag och
  förkastades.
- Smarkets: bettable event under `/sport/football/england-championship/`.
- Flashscore: exakt ligarubrik `ENGLAND: Championship`.
- FotMob: exakt `(ccode, name) = (ENG, Championship)`; skotska Championship
  delar namn men har `SCO` och kan därför inte läcka in.

Första produktionsvarvet skapade 15 rader och avslöjade två rena
presentationspar trots samma liga, motståndare och avspark:
`Queens Park Rangers`/`QPR` samt
`Birmingham City`–`Wolverhampton`/`Birmingham`–`Wolves`. De tre namnen har
lagts som explicita alias före v12:s rena start. Den globala fuzzy-tröskeln
har inte lättats.

## Vad som ändras

- Championship blir synlig och actionable i Oddset med Pinnacle, SvS/Kambi,
  Ninja/Altenar och den interna Smarkets-insamlingen.
- Flashscore är fortsatt liveradarns ankare och FotMob sekundär. Ligan får
  samma strukturella källval, färskhetskrav, matchtak och signaltrösklar som
  övriga ordinarie ligor.
- Prematchmatchen i Oddset ger liveradarn den kanoniska länken som krävs för
  att signaljournalen ska kunna observera samtidiga livepriser.
- Befintliga football-data-resultat `E1` fortsätter vara resultatunderlag.

## Vad som inte ändras

- Signalnivåer, xG-/proxytrösklar, prisprocess, källrankning, identitetsregler
  och liveoddsens 90-sekunderskrav är oförändrade.
- Sofascore kopplas inte tillbaka som bärande livekälla.
- `MODEL_LEAGUES`, `SOFA_UT` och V2.2:s `SCOPE_LEAGUES` ändras inte.
  Championship får alltså inte automatiskt en okalibrerad målmodell bara för
  att live- och oddsunderlaget öppnas.
- Historiska livepriser, presence eller signaler bakfylls aldrig.

## Varför en ny radarversion

En ny liga ändrar populationen som kan producera Följer-/Stark-signaler.
Att lägga den i v11 hade blandat två populationer i samma blindtest.
`RADAR_V12_STARTED_AT` ligger därför framåt från kodändringen. Observationer
producerade av v12-kod före gränsen blir `transitional`; efter gränsen kan de
ingå i den rena v12-kohorten. `live_settlement` har uppdaterats explicit och
vägrar som tidigare att settla en okänd radarversion.

## Uppföljning

Efter driftsättning ska följande kontrolleras:

1. ett fullvarv skapar Championship-matcher och priser från tillgängliga
   källor utan kvarvarande identitetskonflikt;
2. nästa pågående Championship-match ger presence/capture från Flashscore
   och/eller FotMob;
3. `cli.py lanklucka` körs efter första riktiga liveomgången;
4. Championship utvärderas separat i v12-facitet och blandas aldrig med v11.
