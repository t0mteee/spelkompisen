# Överlämning 2026-09-21 — rätta Topptipsets Pinnacle-kopplingar

## Uppdrag och belägg

Saman: fixa bekräftade fel, lämna Vasalund–Assyriska, bedöm reservodds.
Topptipset 4346 hade 322 `not_listed`-captures per saknad match sedan
17/9. Serverns läsning av Pinnacles publika bulk 21/9 15:00:29Z fann:

| SvS | Pinnacle | Id / avspark UTC | 1/X/2 vid kontroll | Total |
|---|---|---|---|---|
| Lanús–Estudiantes | Lanus–Estudiantes de La Plata | 1636054672 / 22/9 00:15 | 2,26 / 2,95 / 3,97 | 1,75 |
| Cuiaba Esporte–Nautico | Cuiaba–Nautico | 1636640777 / 22/9 00:30 | 2,16 / 3,26 / 3,71 | 2,25 |

Matchup-svarets Age var 358 s, marknadssvarets 240 s. Detta är
diagnostiska nutidspriser, INTE historiska captures eller odds att bakfylla.
Rätt motståndare och exakt avspark fanns även i sparad diagnostik.
Vasalund saknades i indexet; ingen fortsatt utredning enligt Samans besked.

## Levererad kod: pool-name-v4

- `Cuiaba Esporte` → `Cuiaba` är ett poolspecifikt alias.
- **Estudiantes är inte ett globalt alias.** Kortnamnet löses bara med
  motståndaren exakt Lanus på båda källsidorna, känd avspark inom 15 min,
  och kandidaten exakt Estudiantes de La Plata. Caseros, Rio Cuarto och
  andra trupper får inte godkännas genom fuzzy eller landskodsalternativ.
- Båda orienteringar stöds; entydighetsvakten, hörn-/kortvetot och övriga
  namn-/tidsregler behålls. 1X2 och Ö/U följer samma provider-id.
- Globala modellalias, modellparametrar, V2.2-manifest och radar är orörda.
  Poolmatcharens semantiska version bumpad. PIT-datumnoter uppdaterade
  enligt befintligt insamlingsbeslut; inga gamla priser/frysningar ändras.
- Fem regressionstester: riktiga par + total, fel klubbar/trupper,
  saknad/fel tid och motståndare, spegling/tvetydighet, Cuiaba/hörnspärr.

## Reservkälla — rekommendation, inte inkopplad

1X2 är redan tillgängligt från SvS på alla åtta matcher i 4346. Analysens
bas är SvS → Pinnacle → streck. Att Pinnacle saknas betyder därför inte
att hela matchen saknar odds. Varningen ska fortsätta skilja på det.

Den verkliga tilläggsnyttan är främst **Ö/U när Pinnacle saknas**. Befintliga
klienter kan läsa Kambi/SvS (`kambi.event_markets`) och Ninja/Altenar
(`altenar.league_events`), men deras täckning för just de saknade poolmatcherna
är inte verifierad. Detta arbete startar inga nya insamlare.

Föreslagen separat leverans:

1. Samla kandidatpriser i befintligt varv, i separat provider-märkt serie:
   källa, event-id, avspark, marknad, lina, båda odds, hämtningstid och Age.
   Gör ingen HTTP-hämtning i UI-anrop eller per kupongbygge.
2. Matcha båda lagen och avspark med trupp-/entydighetsvakter. Källfel skiljs
   från lyckad frånvaro. Ingen gammal prisändringstid får bli färsk presence.
3. Visa dem först som **reservunderlag**, med tydlig käll-/färskhetsmarkering.
   En soft bookmaker får ALDRIG fylla `sharp_odds`, Pinnacle-CLV,
   `pit-total-v1` eller få Pinnacle-varningen att försvinna.
4. Om reserven därefter ska styra byggarens Ö/U-regel: nytt explicit
   källvalskontrakt, versionsmärkt bygginput och separat forward-jämförelse.
   Ingen mixning med gamla frysningar eller automatisk modellpromotion.

Källor kontrollerade i kod, inte påstådd ny live-täckning. `not_listed`
är fortfarande en blandad legacy-status; den får inte beskrivas som
bevisat saknat utbud. Finklassning bör skilja möjlig namnmiss, tvetydighet,
listad utan marknad och transportfel, med okänd orsak när bevis saknas.

## Verifiering och drift

21 riktade tester (nya par och befintliga poolnamn/insamlingsvakter) gröna.
Full push-kontroll grön (backendtester, frontendlint och frontendtester).
Kodcommit **3135dbb**, pushad och driftsatt på 192.168.50.100. Endast
serverns backend omstartad; ingen frontendändring eller gammal tjänst startad.
`/api/health`: status, pools, v22 och oddset samtliga `ok`.

**Faktisk efterkontroll 15:12:29Z:** ordinarie insamling har nu fyllt analysen
för 4346 med 1X2 och total för match 7 och 8 (samma priser/linor som tabellen
ovan). `input_health.missing_sharp` och `missing_total` har gått från 3 till
1; `missing_svs=0`, `missing_all=0`. Endast Vasalund–Assyriska återstår.
Dubbeltrafikspärren respekterades; ingen tvingad hämtning/bakfyllning.

Skrivskyddad täckningsrapport körd efter driftsättning:
`/tmp/pool-tackning-20260921-v4.md` och `.json` på servern. Rapportens
sluträttade omgång 4345 har oförändrade gamla horisonter; den är INTE
beviset för dagens förbättring, som kommer från analysen för öppna 4346.
