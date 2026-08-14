# PH5 täthetssvep 4096/8192 — förregistrering 2026-08-14

**Status:** specificerad, ej körd. Skriven FÖRE körning.

## Frågan

PH5 v2 (`docs/ph5-radvalsablation-256-512-2026-07-26.md`) mätte att vårt radval
är SÄMRE än slump för Stryktipset, men att underskottet krymper monotont med
tätheten: **−8,2 → −5,0 → −2,3 pp**. Vid 512 rader var metoden i bästa fall
likvärdig folk-/favoritrad. Kurvan testades aldrig längre.

**Korsar underskottet noll vid högre täthet, och i så fall var?**

Svaret avgör vilken budget en framtida forward-nyckel i PH3 ska ha. Saman
föreslog 5 000 kr; det talet är i dag valt utan mätning.

## Varför inte bara köra forward-testet

Uppmätt 2026-08-14 på de öppna omgångarna: 5 000 rader ger 1,475 % chans till
13 rätt per omgång på Stryktipset och 0,680 % på Europatipset. Med 1,0
respektive 1,8 omgångar per vecka (mätt över 90 dygn) ger två veckor sex
omgångar och **94,5 % sannolikhet för noll toppvinster**. Promotionsgrinden
kräver dessutom 40 parade omgångar — 40 veckor för Stryktipset.

Ablationen har 8 324 settlade omgångar i stället för sex.

## Vad som körs

```
.venv/bin/python -B scripts/ph5_radvalsablation.py \
    --product stryktipset --budget 4096 --json docs/ph5-svep-stryk-4096.json
```

Fyra körningar: `{stryktipset, europatipset} × {4096, 8192}`.

- **Bara 13-matchsspelen.** Topptipsetfamiljen har tak 512
  (`EIGHT_MATCH_MAX_BUDGET`) eftersom 8 matcher ⇒ 3^8 = 6 561 rader; 4 096 vore
  62 % av hela utfallsrummet. Kör dem inte.
- **1024 och 2048 hoppas över** på Samans begäran. Kurvan från v2 (256/512)
  plus två punkter långt ut räcker för att se om den vänder.
- **Runtime:** cirka 1,5 h per körning, alltså ~6 h totalt. Kör i bakgrunden.
- **Per-omgångs-ROI sparas i JSON** så omräkning aldrig kräver ny körning.

## Vad som INTE får ändras

- **Byggaren.** Ablationen mäter den befintliga `build_ev_system` vid högre
  täthet. Ändras ranking och budget samtidigt går effekterna inte att skilja åt.
  (Observation för senare, inte del av detta: vid 256 rader spelar systemet 1 på
  96 % av raderna i en match som modellen ger 35/29/36 — koncentrationen kommer
  ur streck-EV, inte ur sannolikhet. Det är en egen fråga med en egen ablation.)
- **v2:s metod.** Parad jämförelse per omgång, winsoriserad differens ±200 pp,
  och andel omgångar där vi slår baslinjen som svansimmun rangstatistik.
  Huvudsiffra och KI måste vara samma estimand — v1 föll på just det.
- **Kohorten `final_only`.** Hålls utanför pit-v3-manifestet och får aldrig
  blandas in i det frysta forward-experimentet.

## Vad ablationen INTE svarar på

- **Absolut ROI.** Alla armar matas med SLUTSTRECKET, som inte var känt när
  raden byggts på riktigt. Absoluta tal är en ÖVRE gräns, inte en prognos.
  Jämförelsen mellan armar är ändå rättvis eftersom alla får samma optimistiska
  information — det är hela poängen med den parade designen.
- **Lönsamhet.** Uttaget är 40 % på Stryktipset (hurdle +67 % mot fältet). Ingen
  budget vänder det utan jackpot. Frågan här är relativ: slår vårt radval de
  naiva baslinjerna?

## Beslutsregel, satt före körning

1. **Underskottet krymper men korsar inte noll vid 8192** ⇒ ingen ny
   forward-nyckel. Täthet är inte lösningen, och nästa fråga är rankingen.
2. **Korsar noll mellan 512 och 8192** ⇒ registrera EN forward-nyckel på den
   lägsta budget där den parade differensen har positiv nedre KI-gräns. Lägsta,
   inte bästa punktskattning — den högsta punkten på en brusig kurva är vald av
   bruset.
3. **Slumpen ligger bäst igen** (som fällde v1) ⇒ resultatet är ogiltigt, inte
   intressant. Undersök estimanden före tolkning.

## Ärlighetsnot som MÅSTE följa med nyckeln

Budgeten väljs på `final_only`-kohorten, alltså PÅ data. Det är samma sorts val
som modellens temperatur T, och samma regel gäller: **forward-ledgern är beviset,
ablationen är det inte.** Ablationens resultat får aldrig senare citeras som
validering av forward-utfallet, och nyckelns registrering ska säga i klartext
att budgeten valdes historiskt — samma not som b1024-uteslutningen fick
(`docs/db-atgarder.md` 2026-08-09).

FDR-kostnaden ska också nämnas: utmanarfamiljen är 60 jämförelser i dag, och
varje ny nyckel kostar styrka för alla andra.
