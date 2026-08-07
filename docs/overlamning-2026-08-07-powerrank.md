# Överlämning 2026-08-07 — powerrank, drift och ligor

**LÄS FÖRST i ny session.** Ersätter `overlamning-2026-08-01-codex-hardening.md`
som aktuell överlämning; den gäller bara som historik.

## Vad som gjordes 2026-08-06/07

Allt ligger på grenen `flashscore-primar-och-signaljournal` (PR #1), pushat.

| Område | Version | Dokument |
|---|---|---|
| Sofascore urkopplad ur radarn, Flashscore ankare | radar **v6** | `live-radar-v6-2026-08-06.md` |
| Proxysignalen på fält som finns | radar **v7** | `radar-proxy-v7-forregistrering-2026-08-07.md` |
| Driftjusterad closing-estimat | sharp **v8** | `closing-drift-v8-forregistrering-2026-08-07.md` |
| Kalibrering, Europaligor, powerrank | — | `plan-powerrank-och-ligor-2026-08-07.md` |

Kortfattat, med de mätningar som motiverade besluten:

* **Radar v6/v7.** Sofascore rapporterade `xg=0.0` i stället för att utelämna
  (Paide–SK Rapid: 0,0/0,0 mot Flashscores 0,09/0,81) — urkopplad ur radarn,
  men lever kvar i resultat, modellstatistik och frånvaro. Länkningen fick
  tre steg (strikt → kontext → ett lag räcker); truppmarkörer spärrar i alla.
  Proxysignalen krävde fält som bara finns när xG finns och tillförde därför
  NOLL matcher; den använder nu `farliga skott` = på mål + blockerade.
  Klockan fryses vid 45 i paus (`STAGE_FROZEN`) i stället för att censureras —
  annars föll matchen ur "starkt chansgap" just när gapet var intressant.
* **Sharp v8.** `fair` är inte Pinnacles pris NU utan en skattning av var det
  STÄNGER. Mätt på 10 908 parade observationer: favoriter driftar −0,61 pp,
  outsiders +0,32 pp, mitten inte alls. Följden i facitet var att
  favoritflaggor gav +0,29 % close-EV (KI rymmer noll) mot outsiders +5,96 %.
  Momentum är dött (R² = 0,000) och ska inte byggas.
* **Smarkets** bortkopplad som andra ankare (56 030 priser på 1X2, NOLL på
  AH/Ö/U/hörnor). **Spärren i `ANCHOR_SOURCES` står kvar** — utan den blir den
  en spelbar bok igen (184 av 476 felaktiga flaggor 2026-07-25).
* **Europaligorna** (PL, Serie A, La Liga, Bundesliga) är fullt följda.
  `RESEARCH_LEAGUE_KEYS` är tom. De ligger utanför `MODEL_LEAGUES` eftersom
  0 av 2 897 matcher har xG.
* **MLS kalibrerad** (T=1,0, n=744). Superettan/OBOS kan INTE kalibreras —
  `FD_URLS` saknar stängningsodds för dem, de ärver poolens huvudliga.
* **Källhälsan** filtreras på `active_sources()`, härledd ur BOOKS/ANCHOR/
  SHADOW/LIVE. Både backend och UI följer den listan.

## KVARSTÅENDE — Samans fyra punkter på powerranken

Fliken 🏋 Lagstyrka finns (`/api/oddset/powerrank`, `PowerRankPanel` i
App.jsx, `oddset_model.powerrank`). Följande är beställt men INTE gjort:

### 1. Matcher utan xG ska inte räknas alls (METODFEL som måste rättas)

Nuvarande `powerrank()` räknar `points` på **alla** matcher men `xpts` bara på
xG-täckta, och jämför dem via skalningen
`pts_on_xg = pts * (n_xg / matches)`. Det är en approximation som antar att
poängen fördelar sig jämnt över täckta och otäckta matcher — vilket inte är
givet.

Samans invändning är riktig: *"det är ointressant hur många poäng vissa lag
tog för några säsonger sedan om vi inte har någon xG-data att köra det mot."*

**Åtgärd:** räkna BÅDE poäng och xPts enbart på matcher som har xG. Då blir
avvikelsen exakt i stället för skalad, och `matches` i tabellen ska visa
antalet xG-täckta matcher. Lag utan xG-matcher ska falla ur tabellen helt,
inte visas med `–`. Ingen bakfyllning av xG (`MODEL_DATA_VERSION`-regeln).

### 2. Säsongsfilter

Fitten har exponentiell tidsvikt (halveringstid 166 d) men tabellen summerar
poäng/xPts över HELA historiken, så innevarande säsong blandas med förra.
Lägg ett säsongsval (innevarande / föregående / allt) som filtrerar raderna
före aggregeringen. Säsongsgräns kan härledas ur `date` — nordiska ligor är
vår–höst, MLS likaså, medan Europaligorna är höst–vår.

### 3. Läsbar tabell

Raderna flyter ihop. Lägg zebra-nyans per rad i `.powerrank` (App.css).

### 4. Riktiga lagnamn

Tabellen visar den normaliserade nyckeln (`djurgarden`, `ifk norrkoping`).
`powerrank()` returnerar redan `aliases` med de RÅA namnen ur
resultathistoriken — använd det första aliaset som visningsnamn och behåll
nyckeln som fallback.

## Regler som gäller allt ovan

* Powerranken är **AMBER**. Modellen förutsäger inte Pinnacles drift till
  stängning (r = −0,120, 90 % KI [−0,252, +0,034], R² = 1,4 %), så den får
  inte ge stödchip, lyfta ett spelkort eller påverka edge, urval eller
  notiser. Actionability kräver egen förregistrering och grind.
* **Backend har ingen auto-reload** och ägs numera av launchd:
  `launchctl kickstart -k gui/$(id -u)/com.saman.spelkompisen.backend`.
  Kill + nohup krockar med jobbet (det har `keepalive`).
* Tester: `cd backend && .venv/bin/python -B -m unittest discover -s tests`
  (570 gröna i skrivande stund).
