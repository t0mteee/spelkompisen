# Close-drift-facit v2 — förregistrering

Datum: 2026-07-26 (Fable 5, godkänd av Saman). Uppföljning av v1
(`docs/close-drift-facit-2026-07-26.md`). Måtten är skrivna INNAN utfallen
räknats. Ingen runtime-ändring oavsett utfall.

## Tre delfrågor

### (a) Reverseringshypotesen — FORWARD, ny kohort

v1 fann att h24→h3-skift går UNDER 50 % riktningsträff mot close för AH/Ö/U.
Att vända hypotesen på samma data är forking paths; därför förregistreras nu:

- **Hypotes:** för AH och Ö/U (och utforskande 1X2) ger h24→h3-skiftet
  ≥ 0,5 pp en prediktion om REVERSERING: drift h3→close åt motsatt håll.
- **Kohort:** endast målhorisontrader med `captured_at > 2026-07-26T21:00Z`
  (efter denna förregistrering). Samma filter som v1 i övrigt.
- **Utvärdering:** samma riktningsträff/dödzon/kluster-bootstrap som v1;
  läses på VECKOKADENS av samma skript, tolkas först vid ≥ 100 aktiva
  selektioner ("SAMLAR" innan dess). Gate till 🔮-radar: undre 90 %-KI för
  reverseringsträffen > 0,5 och ≥ 30 matcher, per marknad.

### (b) Linjeflytt-som-drift — parmarknaderna, befintlig data

v1 exkluderade ~500 AH-/Ö/U-selektioner där LINAN bytt mellan horisonterna —
bytena är parmarknadernas verkliga drift och deras utfall har aldrig
granskats (ny fråga ⇒ befintlig data OK).

- **Enhet:** match × marknad (en representativ sida: 'H' för AH, 'O' för
  Ö/U) × målhorisont h3 (källa h24), krav: `line_key(h24) ≠ line_key(h3)`,
  `closing_line` känd på h3-raden.
- **Mått (TVÅSIDIGT, ingen riktning förregistreras):** andel där
  close-linan fortsatt åt SAMMA håll som h24→h3-flytten
  (fortsättningsandel), mot andel reverserade och andel stilla
  (`closing_line == line(h3)`). Kluster-bootstrap per match, 90 % KI.
  Tolkningströskel: KI:t för fortsättning mot reversering (bland flyttade)
  skilt från 50/50.

### (c) Frånvaro med större fönster — befintlig data, UTFORSKANDE

v1:s cell hade 28 selektioner (krävde absence-captures vid exakt båda
horisonterna). Riktningshypotesen (drift MOT drabbat lag) var förregistrerad
redan i v1 och ändras inte; endast aktiveringsfönstret vidgas för styrka:

- **Aktivering:** ny ETABLERAD frånvaro (≥ 5 matcher eller okänd) på exakt
  EN sida mellan tidigaste absence-capture inom 72 h före avspark (måste
  vara ≥ 6 h äldre än målcapturen) och målhorisontens captured_at.
- Märkt UTFORSKANDE: oavsett utfall krävs replikering i forward-kohorten
  (a-spårets kadens) före någon gate.

## Gemensamt

Estimand som v1: dödzon |d| < 0,25 pp, winsorisering ±5 pp på signerad
drift, kluster-bootstrap per match, 90 % KI, seed 42, 2 000 replikat.
Alla celler redovisas. Skript: `backend/scripts/close_drift_facit_v2.py`.

## Resultat (första körningen 2026-07-26, efter förregistreringen)

**(a) Reversering forward: SAMLAR** — kohorten börjar nu (0/100 aktiva);
läses om på veckokadens av samma skript.

**(b) Linjeflytt h24→h3 (tvåsidigt, befintlig data):**

| marknad | flyttade vidare till close | stilla | fortsättningsandel |
|---|---|---|---|
| AH | 77 | 126 | 46,8 % [36,4..55,8] — neutralt |
| **Ö/U** | 72 | 139 | **23,6 % [15,3..31,9]** |

**Ö/U-linjeflyttar REVERSERAR**: bland linor som rör sig vidare går 76 %
TILLBAKA mot hållet de kom ifrån, med hela KI:t klart under 50 % — och
därtill står 2 av 3 stilla efter flytten. Tvåsidigt förregistrerat ⇒ äkta
fynd, samstämmigt med v1:s prisreversering. AH är neutralt.

**(c) Frånvaro brett fönster (utforskande):** →h3 46,2 % [25,0..68,0]
(n=26), →m20 n=6 — ingen signal; fortsätter samla.

## Tolkning och nästa steg

Mönstret är nu konsistent över två oberoende mått: **Pinnacles tidiga
Ö/U-rörelser (pris OCH lina) överreagerar och dras tillbaka mot close.**
Praktisk innebörd om det håller: när totallinan just flyttat är det gamla
hållet oftare värt att ta än att jaga flytten — en fade-signal, inte en
följa-signal. INNAN något syns som tips krävs: (1) forward-replikering i
(a)-kohorten (även linjeflytt-cellen läggs till veckoläsningen), (2)
ekonomisk storleksmätning i PRIS-EV mot close (riktning räcker inte), (3)
vanliga trappan med signal_version-disciplin. Frånvarospåret förblir
utforskande. Ingen runtime-ändring nu.
