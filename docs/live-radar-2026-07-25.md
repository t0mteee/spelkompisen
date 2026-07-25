# Live-radar v1 — observerat chansgap i shadow mode

Datum: 2026-07-25.

## Produktbeslut

Samans beställning är en observationsradar: hitta pågående matcher där
chanserna är större än målutdelningen medan det fortfarande finns tid kvar.
Den ska hjälpa användaren att välja vad som är värt att granska live. Den
lägger aldrig spel automatiskt.

Claudes offlineprov på 220 matcher visade att en enkel skottvikt inte
förutsade mål i nästa 15-minutersfönster. Det stoppar en grön spelsignal, men
inte en tydligt märkt informationsradar. Därför byggs radarn i shadow mode och
dess egna observationer samlas innan notiser eller modellstöd övervägs.

## Levererat

- `app/live_radar.py` läser Sofascores publika livefeed och kumulativa
  matchstats för projektets ligor.
- Observerade fält: xG, stora chanser, skott, skott på mål, skott i box,
  boxberöringar och hörnor. Coverage varierar per liga.
- Träningsmatchernas globala Sofascore-turnering filtreras mot matcher som
  redan finns i Spelkompisens Oddset-vy; radarn fylls inte med godtyckliga
  träningsmatcher från hela världen.
- `oddset_live_capture` sparar råa femminuterssnapshots. Inga härledda
  signaler lagras som facit.
- `/api/oddset/live-radar` räknar signalen vid läsning och är märkt
  `mode=shadow`.
- Oddset-vyn har en mobilanpassad Live-radar med minut, ställning, xG/proxy,
  chansmått och förklaring.
- Samma fasta femminutersjobb som poolinsamlingen kör `live-tick`. Det är
  förskjutet två minuter från Oddset-jobbet.

## Signalpolicy v1

`chance-gap-shadow-v1` använder i första hand:

- lagets `xG − mål`;
- matchens `total xG − totala mål`;
- ny xG sedan observationen cirka 15 minuter tidigare;
- minst tolv minuter kvar av ordinarie tid.

Om xG saknas används en strikt proxy av stora chanser, skott på mål, skott i
box och boxberöringar. Proxyflaggan visar uttryckligen varningen att historiken
ännu inte har visat någon prediktiv mållyft. Den får aldrig blandas ihop med
Oddsets gröna värdesignaler.

Inget i v1 påverkar:

- värdesignaler eller Kelly;
- Oddset- eller poolmodellen;
- CLV-/prediction-facit;
- pushnotiser;
- systemförslag.

## Databasåtgärd

Migration: `backend/scripts/migrera_live_radar.py`.

Backup:
`backend/data/backups/stryktips-2026-07-25-fore-live-radar.db`.

Första migreringen skapade 26 kolumner, 0 rader och gav
`PRAGMA integrity_check = ok`. Fem första globala träningsmatchsprober ligger
kvar som auditerbar `sofa-live-v1`, men är efter scope-rättningen exkluderade
från API och utvärdering. Aktuell captureversion är `sofa-live-v2`.

## Nästa konkreta actions

1. Samla minst 200 riktiga signalögonblick och minst 40 avslutade matcher per
   signaltyp (`xg` respektive `proxy`).
2. Settla två utfall utan efterhandsval:
   - mål i matchen under nästa 15 minuter;
   - minst ett ytterligare mål före full tid.
3. Jämför mot liga × minut × aktuell målställning, inte mot en global basrate.
4. Behåll UI-radarn även om prediktionen är neutral, men aktivera push först
   om undre 90-procentig bootstrapgräns för lyftet är över noll.
5. Om proxyspåret återigen är neutralt: visa bara xG-ligor som
   “granska”-signal och behåll proxydata som coverage.

## Acceptanskriterier före notiser

- minst 40 avslutade signalmatcher och minst 28 kalenderdagar;
- ingen dataläcka från händelser efter capture;
- resultat settlas från samma Sofascore-event-id;
- separat facit för xG och proxy;
- positiv undre 90-procentig KI-gräns mot konditionerad basrate;
- nytt uttryckligt beslut från Saman innan push aktiveras.
