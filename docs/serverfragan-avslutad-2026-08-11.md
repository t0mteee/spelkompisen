# AWS-testet 2026-08-11 — korrekt omtest genomfört

> **Korrigering 2026-08-11:** den första rapporten drog en för bred slutsats.
> Den testade Sofascores **live-endpoint**, inte de endpoint-typer som matar
> modell, xG, frånvaro och lagstyrka. Den visade att den provade AWS-adressen
> blockerades från live-endpointen, men kunde inte avgöra om Spelkompisens
> övriga Sofascore-insamling hade fungerat. Frågan återöppnades därför och
> testades samma dag på en ny AWS-adress med rätt endpoint-uppsättning.

## Slutresultat från korrekt omtest

Ny Lightsail-instans i Stockholm, publik IP `51.20.96.34`, provades
`2026-08-11T13:59Z`. Resultatet var entydigt:

| kontroll | resultat |
|---|---|
| Svenskaspel | OK |
| Pinnacle | OK, 5 290 objekt |
| Kambi | OK |
| **Sofascore modell** | **0/8 OK — status 403 på samtliga** |
| Sofascore live | status 403 |
| Flashscore | OK, chansdata i 1/2 mätbara livematcher |
| FotMob | OK |
| Altenar | OK |

De åtta Sofascore-proven omfattade säsongslista, avslutade matcher, kommande
matcher, xG/matchstatistik, laguppställning, lagdata, laghistorik och
spelarstatistik. Det var inga DNS- eller installationsfel; svaren var
omedelbara 403 från källan.

**Beslut:** just den nya AWS-adressen är diskvalificerad och något
72-timmarstest ska inte startas. Tillsammans med den tidigare AWS-adressens
live-403 ger det stark evidens mot Lightsail/AWS Stockholm för den nuvarande
arkitekturen. Det bevisar inte att alla andra molnleverantörer eller
regioner är blockerade, men nästa försök ska i så fall vara ett billigt
engångsprov hos en annan leverantör — inte flera dagars AWS-test.

Första Flashscore-körningen markerade felaktigt en tom 200-statistikfeed som
transportfel. Verktyget rättades och omprovet bekräftade att Flashscore
fungerar: en tom match räknas nu som täckningslucka och övriga matcher provas.

## Vad första testet faktiskt visade

AWS Lightsail-instansen låg i Stockholm (`eu-north-1a`) och hade adressen
`51.21.134.29`. `backend/scripts/kalltest_ip.py` kördes var 20:e minut.

Det giltiga ursprungliga mätfönstret var `2026-08-01T10:58Z` till
`2026-08-06T13:40Z`, **2 542 mätpunkter**. Kontrollkörningen den 11 augusti
är sju separata punkter och ingår inte i tabellen.

| källa | roll | OK | av |
|---|---|---:|---:|
| svenskaspel | kritisk | 100,0 % | 364 |
| kambi | kritisk | 100,0 % | 364 |
| flashscore | kritisk | 100,0 % | 360 |
| pinnacle | kritisk | 96,2 % | 364 |
| **Sofascore live** | diagnostik | **0,0 %** | **364** |
| fotmob | stöd | 100,0 % | 363 |
| altenar | stöd | 100,0 % | 363 |

Sofascores `/sport/football/events/live` svarade 403 varje gång. Det är ett
äkta och stabilt resultat för just den adressen och endpointen. Däremot
testades inte säsongslistor, avslutade/kommande matcher, matchstatistik,
laguppställningar, lagdata, laghistorik eller spelarstatistik. Påståendet att
”samma endpoints som appen” testades var därför fel.

Det här spelar roll eftersom live-radarn numera använder Flashscore och
FotMob. En server kan vara användbar för hela nuvarande appen även om
Sofascore live är stängt, förutsatt att Sofascores **modell-endpoints** och de
övriga kritiska källorna fungerar.

## DNS-incidenten — korrigerade fakta

Det första säkra DNS-felet inträffade `2026-08-07T07:40:02Z`, inte den 6
augusti. Från den tidpunkten till omstarten finns **302 hela körningar**. I
varje körning föll samtliga sju källor:

- 1 812 `httpx ConnectError: Temporary failure in name resolution`
  (sex källor × 302 körningar).
- 302 `curl_cffi DNSError: Could not resolve host` från Sofascore.
- Totalt 2 114 DNS-fel; detta var ett totalt lokalt DNS-bortfall, inte cirka
  86 procent källa-fel eller en resolver som lyckades var sjunde gång.

Den tidigare rapporten missade `curl_cffi`-felets klass och blandade dessutom
kontrollkörningen den 11 augusti med det äldre fönstrets totalsiffror.

## Vad som nu är åtgärdat i testverktyget

`backend/scripts/kalltest_ip.py` har fått ett nytt loggformat och testar nu:

1. `sofa_model` — åtta verkliga endpoint-typer för säsonger, matcher, xG,
   laguppställning, lag, laghistorik och spelare. Denna är kritisk.
2. `sofa_live` — den tidigare live-endpointen, nu separat och icke-kritisk.
3. De tidigare kontrollerna för Svenskaspel, Pinnacle, Kambi, Flashscore,
   FotMob och Altenar.

Varje mätomgång får ett gemensamt `run_id`. Både httpx och curl_cffi-DNS-fel
klassas som lokala infrastrukturfel, tas bort ur källornas nämnare och
redovisas separat. Om mer än fem procent av körningarna har DNS-fel
underkänns servermiljön — inte källorna. `--logg` gör att varje kandidat-IP
kan få en egen arkiverbar fil.

## Beslutsregel för en eventuell annan leverantör

Kör först **ett engångsprov** och läs resultatet så här:

- `sofa_model 8/8 modell-endpoints OK`: fortsätt 72-timmarstestet.
- `sofa_model` får 403 på någon endpoint: avveckla instansen; adressen duger
  inte för Spelkompisen och ska avvecklas direkt.
- `sofa_live` får 403 men `sofa_model` är helt grön: det är acceptabelt för
  nuvarande app och ska inte stoppa 72-timmarstestet.
- `⚠️` och namnuppslagningsfel: serverns DNS/infrastruktur måste fungera innan
  källorna kan bedömas.

Efter minst 72 timmar krävs minst 72 användbara prov per källa, över 95
procent transport-OK och högst fem procent körningar med lokala DNS-fel.

## Bevis och historik

- Rådata från första AWS-adressen:
  `docs/kalltest-bevis/kalltest-logg-51.21.134.29-2026-08-11.jsonl`
  (5 009 rader).
- Korrekt omtest från den nya AWS-adressen:
  `docs/kalltest-bevis/kalltest-logg-51.20.96.34-2026-08-11.jsonl`
  (två körningar; den sista är efter Flashscore-rättningen).
- Testverktyg: `backend/scripts/kalltest_ip.py`.
- Enhetstester: `backend/tests/test_kalltest_ip.py`.
- Ursprunglig öppna tråd: `docs/overlamning-2026-08-01-flashscore.md`,
  punkt 2.

**Båda instanserna är avvecklade 2026-08-12** (Saman, i Lightsail-konsolen).
Inget AWS-beroende finns kvar i drift; mätdatan i `docs/kalltest-bevis/`
behålls som evidens. Resultaten gäller de två provade AWS-adresserna och säger
inte säkert hur exempelvis en Hetzner-/Netcup-adress eller en annan region
beter sig.
