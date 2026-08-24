# Överlämning 2026-08-24 — 5 000-testvy, X-audit och livehardening

## Utfört

### Egen sida för PH5:s 5 000-kronorstest

Appen har en ny huvudflik **5 000-test**. Den visar varje automatisk
researchfrysning separat i stället för att gömma den bland Historiks alla
benchmarkgrupper:

- Stryktipset/Europatipset, omgång och datum;
- h3 eller m20 och om frysningen skedde i tid;
- metod (`varderader`, `maxev`, `favoritrad`, `byggarslump`, pensionerad
  `folkrad`);
- bästa antal rätt, kontrafaktisk utdelning och ROI;
- X-andel och antal matcher där X saknas helt.

Knappen **Visa exakt kupong** hämtar först då de tunga 5 000 raderna. Detaljen
visar också teckenvikt per match, sharpodds, SvS-odds, streck vid frysning,
streckrörelse till stopp och facit. Öppna tester visar de frysta raderna redan
innan facit finns; tidigare returnerade detalj-API:t en tom radlista tills hela
omgången var avgjord.

Ny lätt endpoint: `GET /api/pool/ph5`. Exakta rader använder fortsatt
`GET /api/pool/systems/detail` och skickas aldrig i översiktssvaret.

### Odds och streck är verkligen point-in-time

Ingen ny eller retroaktiv DB-kolumn behövdes. `snapshots` och
`sharp_snapshots` är append-only förändringsserier och sparades redan under
insamlingen. Detaljen läser sista observation vars `fetched_at <= frozen_at`.
Den visar dessutom observationstiden. Ett odds efter frysningen kan därför
inte råka presenteras som testets pris.

### X-misstanken är bekräftad som mekanism, inte ännu som modellbevis

Det nya skrivskyddade skriptet `backend/scripts/auditera_ph5_x.py` kördes mot
produktions-DB:n. För appens balanserade `varderader` över fyra oberoende
omgångar:

- 33 av 104 frysta matchbeslut saknade X helt;
- 32 matchbeslut hade X som facit;
- i 7 av dessa 32 saknades X helt.

Talen dubblar samma fotbollsmatch när både h3 och m20 finns, så de är inte 104
oberoende matcher. Favoritradens bortfall var större, maxev:s mindre. Slutsats:
binära kandidatval kan systematiskt skapa 1+2-hörn och Samans observation är
reell. Fyra omgångar räcker inte för att välja en ny regel efter facit.

**Viktigt för nästa assistent:** ändra inte `ph5-v3-*` i efterhand. Om nästa
steg ska prova mer X, skapa en femte, förregistrerad arm med ny config- och
metodnyckel, exakt X-regel och start på en ännu ofryst omgång. Rekommenderad
fråga är inte ”lägg alltid till X”, utan ”ersätt vilket tecken eller vilken
gardering när marknadens X-sannolikhet och folkstrecket motiverar det?”. Den
ska jämföras parat mot oförändrade `varderader`.

### Spelade kupongers liveväg

Historikpanelen hämtar först liverättning utan chans och sedan full
chansberäkning. De två HTTP-anropen gjorde tidigare två kompletta
källhämtningar. Backend delar nu en 20 sekunders single-flight-livebild för
samma öppna produkt/omgångar. Kupongrader och sannolikhet räknas fortfarande
separat; bara källobservationen återanvänds. Frontend använder AbortController
och request-id så ett gammalt svar aldrig kan skriva över en ny laddning.

`event_state` litar nu på `Fulltime` först när ordinarie tid är över. Ett
förifyllt 0–0 kan inte längre maskera `Current` 1–0 under första halvlek.

### xG-bakfyllning och dokumentdrift

`backfill_xg_ligor.py` läser som standard upp till 20 sidor per säsong i
stället för 14. Det täcker MLS:s 522–540 matcher; mindre ligor bryter vid första
tomma sida. Ligue 1-dokumenten är rättade till serverns verkliga status efter
retry: 621/622 xG, enda luckan Nantes–Toulouse 2026-05-17.

## Verifiering

- backend: 781 tester gröna (varav 103 riktade mot de ändrade poolvägarna);
- frontend: 12 tester, lint och produktionsbygge gröna;
- ny X-audit är skrivskyddad och körd mot produktionsdata.

## Berörda huvudfiler

- `backend/app/pool_system_ledger.py`
- `backend/app/pool_played.py`
- `backend/app/main.py`
- `backend/scripts/auditera_ph5_x.py`
- `backend/scripts/backfill_xg_ligor.py`
- `frontend/src/App.jsx`
- `frontend/src/AppV3.jsx`
- `frontend/src/AppV3.css`

Ingen databasfil, hemlighet eller historisk testfrysning ändrades.
