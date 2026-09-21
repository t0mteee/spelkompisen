# Överlämning — synliga oddsluckor i poolen (2026-09-21)

Saman bad om en varning så att saknade poolodds inte påverkar förslagen
osynligt och kan skickas till Claude/Codex för granskning.

## Leverans

- Ny ren rapportfunktion `app/pool_input_health.py`, presentationskontrakt
  `pool-input-health-v1`. Används av `/api/analysis` OCH `/api/system`.
  Systemsvaret beskriver det egna bygganropets analys, inte UI:ts senaste
  analys. Numerik, teckenval, gamla frysningar och insamling är orörda.
- Gul varning före analystabellen när komplett SvS 1X2, Pinnacle 1X2 eller
  Pinnacle Ö/U saknas. Röd när en match saknar komplett 1X2 från BÅDA källorna.
  Ofullständiga trippelpriser räknas inte som komplett oddsunderlag.
- Matchlistan och källorna kan fällas ut. Faktisk `prob_source` visas:
  SvS/Pinnacle/folkets streck/inget. Inget påstående att ”Pinnacle erbjuder
  inte matchen”; orsaken är fortfarande en separat granskningsfråga.
- Vid byggt system finns dessutom en kompakt varning för underlaget just
  vid bygget. En senare analysuppdatering kan inte göra byggvarningen grön.
- **Kopiera för granskning** skapar text med exakt produkt (även Topptipset
  Stryk/Extra), omgång, analysens hämtningstid, räknare, matcher och källor.
  Texten kan klistras till en AI. Inga meddelanden skickas automatiskt.
  Vid http/LAN där Clipboard API saknas finns markerbar textruta och
  ärligt felmeddelande, inte falskt ”kopierat”.
- Mobilvänlig lista; inga nya breda tabeller. Bomben ligger utanför eftersom
  varningen gäller 1X2-poolspelen. Fullständig täckning = ingen varningsruta.

## Viktiga avgränsningar

Varningen gäller data som faktiskt finns i analysen, INTE färskhetsbevis.
Gamla cachepriser kan vara kompletta men inaktuella; UI och granskningsunderlag
säger uttryckligen att prisnärvaro inte garanterar färskhet. Där behövs en
separat presence-baserad förbättring, aldrig `fetched_at` för ett pris som
bara skriver vid förändring. Samma sak gäller historiska PIT-horisonter:
den här rutan uttalar sig inte om deras eligibility.

Priser kan legitimt saknas tidigt före spelstopp. Vi döljer inte det, men
orsaken presenteras inte som konstaterat insamlingsfel. Inga spel spärras
automatiskt och ingen modell ändras; användaren får ett synligt beslutsunderlag.

## Tester och drift

Sex backendtester: fullt/delvis/saknat underlag, ogiltiga priser, Ö/U,
analys-API och bygg-API. Två frontendtester: rubrikprioritering och exakt
granskningsunderlag. Ordinarie full kontroll körs i push-hooken.
Driftsättning sker på 192.168.50.100; inga gamla tjänster startas.
