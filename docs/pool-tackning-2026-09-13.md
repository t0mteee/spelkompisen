# Pooltäckning: 1X2 och Ö/U från Pinnacle vid frysningarna

Genererad 2026-09-13T14:42:11Z av `backend/scripts/pool_tackning_rapport.py` (read-only). Omfattar 88 sluträttade omgångar med spelstopp från 2026-08-15, alla tre horisonter (h24=1440 min, h3=180 min, m20=20 min). Klasserna definieras i skriptets docstring.

## 1X2-täckning per produkt och horisont (andel matcher `ok`)

| produkt | h24 | h3 | m20 | vanligaste lucka vid m20 |
|---|---|---|---|---|
| europatipset | 82/104 (79 %) | 50/104 (48 %) | 57/104 (55 %) | capture_sen (38) |
| stryktipset | 47/65 (72 %) | 35/65 (54 %) | 39/65 (60 %) | aldrig_matchad (18) |
| topptipset | 112/496 (23 %) | 60/496 (12 %) | 294/496 (59 %) | capture_sen (148) |
| topptipsetextra | 29/64 (45 %) | 14/64 (22 %) | 28/64 (44 %) | capture_sen (29) |
| topptipsetstryk | 4/40 (10 %) | 18/40 (45 %) | 21/40 (52 %) | aldrig_matchad (14) |

### Samma sak för forwardtesternas omgångar (det testerna faktiskt frös på)

| produkt | h24 | h3 | m20 |
|---|---|---|---|
| europatipset | 33/39 (85 %) | 13/39 (33 %) | 20/39 (51 %) |
| stryktipset | 22/26 (85 %) | 10/26 (38 %) | 22/26 (85 %) |
| topptipset | 28/168 (17 %) | 16/168 (10 %) | 95/168 (57 %) |
| topptipsetextra | 0/16 (0 %) | 6/16 (38 %) | 0/16 (0 %) |
| topptipsetstryk | 0/16 (0 %) | 5/16 (31 %) | 13/16 (81 %) |

## Felklasser per produkt vid 180 min och 20 min

| produkt | horisont | ok | aldrig_matchad | listad_sent | ingen_1x2 | capture_sen | odds_ofullstandiga | ingen_capture | pit_byggd_fore_capture |
|---|---|---|---|---|---|---|---|---|---|
| europatipset | h3 | 50 | 9 | 0 | 0 | 45 | 0 | 0 | 0 |
| europatipset | m20 | 57 | 9 | 0 | 0 | 38 | 0 | 0 | 0 |
| stryktipset | h3 | 35 | 18 | 0 | 0 | 12 | 0 | 0 | 0 |
| stryktipset | m20 | 39 | 18 | 0 | 0 | 8 | 0 | 0 | 0 |
| topptipset | h3 | 60 | 37 | 6 | 0 | 354 | 0 | 24 | 15 |
| topptipset | m20 | 294 | 38 | 0 | 0 | 148 | 0 | 16 | 0 |
| topptipsetextra | h3 | 14 | 7 | 0 | 0 | 43 | 0 | 0 | 0 |
| topptipsetextra | m20 | 28 | 7 | 0 | 0 | 29 | 0 | 0 | 0 |
| topptipsetstryk | h3 | 18 | 14 | 0 | 0 | 8 | 0 | 0 | 0 |
| topptipsetstryk | m20 | 21 | 14 | 0 | 0 | 5 | 0 | 0 | 0 |

## Löser 20-minutersobservationen luckorna från 180 min? (samma match, samma omgång)

| klass vid 180 min | → klass vid 20 min | matcher |
|---|---|---|
| capture_sen | ok | 309 |
| capture_sen | capture_sen | 152 |
| aldrig_matchad | aldrig_matchad | 85 |
| ingen_capture | ingen_capture | 16 |
| pit_byggd_fore_capture | ok | 15 |
| ingen_capture | capture_sen | 8 |
| listad_sent | ok | 6 |
| capture_sen | aldrig_matchad | 1 |
| ok | ok | 109 |
| ok | capture_sen | 68 |

## Observationsfönstret: på vilken sida av as-of hamnar sharp-capturen?

pit-v4 räknar bara en capture i [as-of − tolerans, as-of]. `horizon_window_open` tvingar Pinnacle-hämtningen i (as-of, as-of + tolerans], alltså EFTER as-of; den räknas bara när CDN-Age backdaterar stämpeln förbi as-of. Utanför fönstret får bara den första produkten i varvet ordinarie sharp-captures — den globala dubbeltrafikspärren hoppar över resten.

| familj | horisont | omgångar | capture före as-of (räknas) | bara efter as-of (räknas inte) | ingen i fönstret |
|---|---|---|---|---|---|
| europatipset | h24 | 8 | 7 (88 %) | 1 | 0 |
| europatipset | h3 | 8 | 4 (50 %) | 4 | 0 |
| europatipset | m20 | 8 | 5 (62 %) | 3 | 0 |
| stryktipset | h24 | 5 | 5 (100 %) | 0 | 0 |
| stryktipset | h3 | 5 | 4 (80 %) | 1 | 0 |
| stryktipset | m20 | 5 | 4 (80 %) | 1 | 0 |
| topptipset | h24 | 75 | 22 (29 %) | 50 | 3 |
| topptipset | h3 | 75 | 16 (21 %) | 56 | 3 |
| topptipset | m20 | 75 | 48 (64 %) | 25 | 2 |

| produkt | dygn med sharp-capture | distinkta sharp-observationer per dygn (median) | max |
|---|---|---|---|
| europatipset | 25 | 6 | 40 |
| stryktipset | 32 | 48 | 55 |
| topptipset | 31 | 14 | 29 |
| topptipsetextra | 20 | 3 | 10 |
| topptipsetstryk | 20 | 2 | 7 |

## Ö/U-total där 1X2 var ok (pit-total-v1, fönster från 2026-09-02T16:00:00Z)

| produkt | horisont | total_ok | total_saknas | total_ogiltig | ingen_rad | rad_saknas |
|---|---|---|---|---|---|---|
| europatipset | h24 | 24 | 0 | 0 | 58 | 0 |
| europatipset | h3 | 13 | 0 | 0 | 37 | 0 |
| europatipset | m20 | 20 | 0 | 0 | 37 | 0 |
| stryktipset | h24 | 22 | 0 | 0 | 25 | 0 |
| stryktipset | h3 | 10 | 0 | 0 | 25 | 0 |
| stryktipset | m20 | 22 | 0 | 0 | 17 | 0 |
| topptipset | h24 | 28 | 0 | 0 | 84 | 0 |
| topptipset | h3 | 23 | 0 | 0 | 37 | 0 |
| topptipset | m20 | 102 | 0 | 0 | 192 | 0 |
| topptipsetextra | h24 | 0 | 0 | 0 | 29 | 0 |
| topptipsetextra | h3 | 6 | 0 | 0 | 8 | 0 |
| topptipsetextra | m20 | 6 | 0 | 0 | 22 | 0 |
| topptipsetstryk | h24 | 0 | 0 | 0 | 4 | 0 |
| topptipsetstryk | h3 | 5 | 0 | 0 | 13 | 0 |
| topptipsetstryk | m20 | 13 | 0 | 0 | 8 | 0 |

## Kompletta omgångar (alla matcher ok) — det grindarna räknar

| produkt | horisont | omgångar | alla matcher 1X2 ok | alla matcher total ok |
|---|---|---|---|---|
| europatipset | h24 | 8 | 3 | 1 |
| europatipset | h3 | 8 | 3 | 1 |
| europatipset | m20 | 8 | 2 | 0 |
| stryktipset | h24 | 5 | 0 | 0 |
| stryktipset | h3 | 5 | 0 | 0 |
| stryktipset | m20 | 5 | 0 | 0 |
| topptipset | h24 | 62 | 6 | 1 |
| topptipset | h3 | 62 | 4 | 2 |
| topptipset | m20 | 62 | 24 | 8 |
| topptipsetextra | h24 | 8 | 2 | 0 |
| topptipsetextra | h3 | 8 | 1 | 0 |
| topptipsetextra | m20 | 8 | 2 | 0 |
| topptipsetstryk | h24 | 5 | 0 | 0 |
| topptipsetstryk | h3 | 5 | 0 | 0 |
| topptipsetstryk | m20 | 5 | 1 | 1 |

## Luckor per liga vid 20 min (liga via Oddsets `svs:`-rader)

| liga | matcher | ok | aldrig_matchad | listad_sent | ingen_1x2 | capture_sen | ingen_capture |
|---|---|---|---|---|---|---|---|
| utanför Oddset | 334 | 180 | 58 | 0 | 0 | 84 | 12 |
| mls | 66 | 36 | 0 | 0 | 0 | 29 | 1 |
| premier_league | 65 | 48 | 12 | 0 | 0 | 5 | 0 |
| la_liga | 44 | 24 | 0 | 0 | 0 | 19 | 1 |
| allsvenskan | 43 | 26 | 0 | 0 | 0 | 17 | 0 |
| serie_a | 41 | 23 | 3 | 0 | 0 | 13 | 2 |
| championship | 30 | 18 | 7 | 0 | 0 | 5 | 0 |
| champions_league | 29 | 13 | 3 | 0 | 0 | 13 | 0 |
| ligue_1 | 24 | 20 | 0 | 0 | 0 | 4 | 0 |
| conference_league | 22 | 12 | 0 | 0 | 0 | 10 | 0 |
| superettan | 21 | 13 | 0 | 0 | 0 | 8 | 0 |
| europa_league | 18 | 8 | 2 | 0 | 0 | 8 | 0 |
| belgian_pro_league | 12 | 7 | 0 | 0 | 0 | 5 | 0 |
| bundesliga | 9 | 5 | 1 | 0 | 0 | 3 | 0 |
| primeira_liga | 5 | 4 | 0 | 0 | 0 | 1 | 0 |
| danish_superliga | 5 | 2 | 0 | 0 | 0 | 3 | 0 |
| eliteserien | 1 | 0 | 0 | 0 | 0 | 1 | 0 |

## Aldrig matchade vid 20 min: 86 rader, 64 unika matcher (Stryk/Topptipset Stryk och Europa/Topptipset Extra delar matcher)

Replayen kör `pinnacle.match` offline med Pinnacle-namnen som Oddset-sidan sparade för samma match (±2 h). `korrekt par fälls av tröskeln` betyder att Pinnacle listade matchen och att poolens egen matchare avvisade rätt par. `ingen Pinnacle-rad hos Oddset` betyder att vi inte kan avgöra om Pinnacle listade den (ligan följs inte av Oddset, eller så listades den aldrig). `listad före spelstopp, Pinnacles namnform ej sparad` betyder att Pinnacle bevisligen listade matchen i tid men att Oddset-raden bär Kambis namn, så vi vet inte vilket namn poolmatcharen avvisade.

| utfall | rader | unika matcher |
|---|---|---|
| ingen Pinnacle-rad hos Oddset | 63 | 51 |
| listad före spelstopp, Pinnacles namnform ej sparad | 17 | 9 |
| korrekt par fälls av tröskeln | 6 | 4 |

| produkt | omgång | match | liga | utfall | Pinnacle-namn | sidor | kombinerat |
|---|---|---|---|---|---|---|---|
| europatipset | 2600 | 3. KF Egnatia – Lilleström | europa_league | listad före spelstopp, Pinnacles namnform ej sparad | FK Egnatia - Lillestrøm (odds hos Oddset från 2026-08-15) | – | – |
| europatipset | 2603 | 3. Leeds – Brentford | premier_league | listad före spelstopp, Pinnacles namnform ej sparad | Leeds - Brentford (odds hos Oddset från 2026-08-22) | – | – |
| europatipset | 2603 | 6. Cagliari – Inter | serie_a | listad före spelstopp, Pinnacles namnform ej sparad | Cagliari - Inter (odds hos Oddset från 2026-08-23) | – | – |
| europatipset | 2604 | 4. West Bromwich – Charlton | utanför Oddset | ingen Pinnacle-rad hos Oddset | – | – | – |
| europatipset | 2604 | 7. Luton – Stockport | utanför Oddset | ingen Pinnacle-rad hos Oddset | – | – | – |
| europatipset | 2604 | 9. Wigan – Milton Keynes Dons | utanför Oddset | ingen Pinnacle-rad hos Oddset | – | – | – |
| europatipset | 2604 | 13. St. Truidense – Royale Union SG | utanför Oddset | ingen Pinnacle-rad hos Oddset | – | – | – |
| europatipset | 2606 | 5. Chelsea – Leeds | utanför Oddset | ingen Pinnacle-rad hos Oddset | – | – | – |
| europatipset | 2606 | 7. Derby – West Bromwich | championship | ingen Pinnacle-rad hos Oddset | – | – | – |
| stryktipset | 4966 | 3. Charlton – Derby | utanför Oddset | ingen Pinnacle-rad hos Oddset | – | – | – |
| stryktipset | 4966 | 7. Stoke – Swansea | utanför Oddset | ingen Pinnacle-rad hos Oddset | – | – | – |
| stryktipset | 4966 | 8. Blackpool – Wycombe | utanför Oddset | ingen Pinnacle-rad hos Oddset | – | – | – |
| stryktipset | 4966 | 11. Cambridge – Wigan | utanför Oddset | ingen Pinnacle-rad hos Oddset | – | – | – |
| stryktipset | 4966 | 13. Plymouth – Stockport | utanför Oddset | ingen Pinnacle-rad hos Oddset | – | – | – |
| stryktipset | 4967 | 4. Nottingham – Leeds | premier_league | listad före spelstopp, Pinnacles namnform ej sparad | Nottingham - Leeds (odds hos Oddset från 2026-07-23) | – | – |
| stryktipset | 4967 | 6. Derby – Cardiff | utanför Oddset | ingen Pinnacle-rad hos Oddset | – | – | – |
| stryktipset | 4967 | 7. Preston – Wolverhampton | utanför Oddset | ingen Pinnacle-rad hos Oddset | – | – | – |
| stryktipset | 4967 | 8. Queens Park Rangers – Bolton | utanför Oddset | ingen Pinnacle-rad hos Oddset | – | – | – |
| stryktipset | 4967 | 11. West Ham – Charlton | utanför Oddset | ingen Pinnacle-rad hos Oddset | – | – | – |
| stryktipset | 4968 | 1. Tottenham – Newcastle | premier_league | listad före spelstopp, Pinnacles namnform ej sparad | Tottenham - Newcastle United (odds hos Oddset från 2026-08-22) | – | – |
| stryktipset | 4968 | 3. Coventry – Hull | premier_league | listad före spelstopp, Pinnacles namnform ej sparad | Coventry City - Hull (odds hos Oddset från 2026-08-22) | – | – |
| stryktipset | 4968 | 5. Bolton – Lincoln | utanför Oddset | ingen Pinnacle-rad hos Oddset | – | – | – |
| stryktipset | 4968 | 8. Charlton – Preston | utanför Oddset | ingen Pinnacle-rad hos Oddset | – | – | – |
| stryktipset | 4969 | 2. Brighton – Leeds | premier_league | korrekt par fälls av tröskeln | Brighton - Leeds United (odds hos Oddset från 2026-08-24) | 1.0/0.588 | 0.794 |
| stryktipset | 4969 | 5. Nottingham – Tottenham | premier_league | korrekt par fälls av tröskeln | Nottingham Forest - Tottenham Hotspur (odds hos Oddset från 2026-08-24) | 0.741/0.692 | 0.716 |
| stryktipset | 4969 | 8. Millwall – Bolton | championship | listad före spelstopp, Pinnacles namnform ej sparad | Millwall - Bolton (odds hos Oddset från 2026-09-02) | – | – |
| stryktipset | 4970 | 11. Preston – Lincoln | championship | ingen Pinnacle-rad hos Oddset | – | – | – |
| topptipset | 4267 | 7. Bolton – Preston | utanför Oddset | ingen Pinnacle-rad hos Oddset | – | – | – |
| topptipset | 4268 | 3. Fortuna Sittard – Cambuur | utanför Oddset | ingen Pinnacle-rad hos Oddset | – | – | – |
| topptipset | 4271 | 7. Santos Laguna – Chivas | utanför Oddset | ingen Pinnacle-rad hos Oddset | – | – | – |
| topptipset | 4273 | 3. Gimnasia y Esgrima Mendoza – Talleres | utanför Oddset | ingen Pinnacle-rad hos Oddset | – | – | – |
| topptipset | 4278 | 5. Hapoel Be`er Sheva FC – Sabah Masazir | champions_league | listad före spelstopp, Pinnacles namnform ej sparad | Hapoel Beer Sheva - Sabah FK (odds hos Oddset från 2026-08-12) | – | – |
| topptipset | 4280 | 5. Athletic Club – CR Brasil | utanför Oddset | ingen Pinnacle-rad hos Oddset | – | – | – |
| topptipset | 4280 | 6. Novorizontino – America | utanför Oddset | ingen Pinnacle-rad hos Oddset | – | – | – |
| topptipset | 4283 | 2. Alianza FC Valledupar – Pereira | utanför Oddset | ingen Pinnacle-rad hos Oddset | – | – | – |
| topptipset | 4288 | 6. Junior – Once Caldas | utanför Oddset | ingen Pinnacle-rad hos Oddset | – | – | – |
| topptipset | 4290 | 5. Talleres – Rosario | utanför Oddset | ingen Pinnacle-rad hos Oddset | – | – | – |
| topptipset | 4290 | 7. Everton – Universidad de Concepcion | utanför Oddset | ingen Pinnacle-rad hos Oddset | – | – | – |
| topptipset | 4292 | 4. Stoke – Hull | utanför Oddset | ingen Pinnacle-rad hos Oddset | – | – | – |
| topptipset | 4292 | 6. Nottingham – Leeds | utanför Oddset | ingen Pinnacle-rad hos Oddset | – | – | – |
| topptipset | 4293 | 3. Juventude – CR Brasil | utanför Oddset | ingen Pinnacle-rad hos Oddset | – | – | – |
| topptipset | 4294 | 7. Preston – Everton | utanför Oddset | ingen Pinnacle-rad hos Oddset | – | – | – |
| topptipset | 4295 | 1. River Plate – Santa Fe | utanför Oddset | ingen Pinnacle-rad hos Oddset | – | – | – |
| topptipset | 4295 | 5. América De Cali – Junior | utanför Oddset | ingen Pinnacle-rad hos Oddset | – | – | – |
| topptipset | 4301 | 7. Toluca – Juarez | utanför Oddset | ingen Pinnacle-rad hos Oddset | – | – | – |
| topptipset | 4303 | 7. Deportivo Pasto – Pereira | utanför Oddset | ingen Pinnacle-rad hos Oddset | – | – | – |
| topptipset | 4303 | 8. Deportes Tolima – Cucuta Deportivo | utanför Oddset | ingen Pinnacle-rad hos Oddset | – | – | – |
| topptipset | 4305 | 1. Cagliari – Inter | serie_a | listad före spelstopp, Pinnacles namnform ej sparad | Cagliari - Inter (odds hos Oddset från 2026-08-23) | – | – |
| topptipset | 4306 | 3. Stoke – Norwich | utanför Oddset | ingen Pinnacle-rad hos Oddset | – | – | – |
| topptipset | 4306 | 4. Sheffield U – Bolton | utanför Oddset | ingen Pinnacle-rad hos Oddset | – | – | – |
| topptipset | 4306 | 6. Portsmouth – Derby | utanför Oddset | ingen Pinnacle-rad hos Oddset | – | – | – |
| topptipset | 4306 | 8. Preston – Bristol City | utanför Oddset | ingen Pinnacle-rad hos Oddset | – | – | – |
| topptipset | 4308 | 5. Santa Fe – Millonarios | utanför Oddset | ingen Pinnacle-rad hos Oddset | – | – | – |
| topptipset | 4316 | 4. Pereira – Millonarios | utanför Oddset | ingen Pinnacle-rad hos Oddset | – | – | – |
| topptipset | 4316 | 8. FBC Melgar – ADT Tarma | utanför Oddset | ingen Pinnacle-rad hos Oddset | – | – | – |
| topptipset | 4319 | 6. CR Brasil – America | utanför Oddset | ingen Pinnacle-rad hos Oddset | – | – | – |
| topptipset | 4320 | 1. Real Madrid – Inter | champions_league | listad före spelstopp, Pinnacles namnform ej sparad | Real Madrid - Inter (odds hos Oddset från 2026-08-29) | – | – |
| topptipset | 4321 | 2. Santa Fe – Vasco da Gama | utanför Oddset | ingen Pinnacle-rad hos Oddset | – | – | – |
| topptipset | 4321 | 8. Gwangju FC – Jeju United FC | utanför Oddset | ingen Pinnacle-rad hos Oddset | – | – | – |
| topptipset | 4323 | 2. Manchester United – Sabah Masazir | champions_league | korrekt par fälls av tröskeln | Manchester United - Sabah FK (odds hos Oddset från 2026-08-29) | 1.0/0.556 | 0.778 |
| topptipset | 4327 | 5. Santa Fe – Deportes Tolima | utanför Oddset | ingen Pinnacle-rad hos Oddset | – | – | – |
| topptipset | 4328 | 2. Bolton – Cardiff | championship | ingen Pinnacle-rad hos Oddset | – | – | – |
| topptipset | 4328 | 3. Derby – Birmingham | championship | ingen Pinnacle-rad hos Oddset | – | – | – |
| topptipset | 4328 | 8. Mainz – Frankfurt | bundesliga | korrekt par fälls av tröskeln | Mainz 05 - Eintracht Frankfurt (odds hos Oddset från 2026-08-30) | 0.769/0.643 | 0.706 |
| topptipset | 4329 | 8. Cambuur – Nijmegen | utanför Oddset | ingen Pinnacle-rad hos Oddset | – | – | – |
| topptipsetextra | 1859 | 3. KF Egnatia – Lilleström | europa_league | listad före spelstopp, Pinnacles namnform ej sparad | FK Egnatia - Lillestrøm (odds hos Oddset från 2026-08-15) | – | – |
| topptipsetextra | 1862 | 3. Leeds – Brentford | premier_league | listad före spelstopp, Pinnacles namnform ej sparad | Leeds - Brentford (odds hos Oddset från 2026-08-22) | – | – |
| topptipsetextra | 1862 | 6. Cagliari – Inter | serie_a | listad före spelstopp, Pinnacles namnform ej sparad | Cagliari - Inter (odds hos Oddset från 2026-08-23) | – | – |
| topptipsetextra | 1863 | 4. West Bromwich – Charlton | utanför Oddset | ingen Pinnacle-rad hos Oddset | – | – | – |
| topptipsetextra | 1863 | 7. Luton – Stockport | utanför Oddset | ingen Pinnacle-rad hos Oddset | – | – | – |
| topptipsetextra | 1865 | 5. Chelsea – Leeds | utanför Oddset | ingen Pinnacle-rad hos Oddset | – | – | – |
| topptipsetextra | 1865 | 7. Derby – West Bromwich | championship | ingen Pinnacle-rad hos Oddset | – | – | – |
| topptipsetstryk | 976 | 3. Charlton – Derby | utanför Oddset | ingen Pinnacle-rad hos Oddset | – | – | – |
| topptipsetstryk | 976 | 7. Stoke – Swansea | utanför Oddset | ingen Pinnacle-rad hos Oddset | – | – | – |
| topptipsetstryk | 976 | 8. Blackpool – Wycombe | utanför Oddset | ingen Pinnacle-rad hos Oddset | – | – | – |
| topptipsetstryk | 977 | 4. Nottingham – Leeds | premier_league | listad före spelstopp, Pinnacles namnform ej sparad | Nottingham - Leeds (odds hos Oddset från 2026-07-23) | – | – |
| topptipsetstryk | 977 | 6. Derby – Cardiff | utanför Oddset | ingen Pinnacle-rad hos Oddset | – | – | – |
| topptipsetstryk | 977 | 7. Preston – Wolverhampton | utanför Oddset | ingen Pinnacle-rad hos Oddset | – | – | – |
| topptipsetstryk | 977 | 8. Queens Park Rangers – Bolton | utanför Oddset | ingen Pinnacle-rad hos Oddset | – | – | – |
| topptipsetstryk | 978 | 1. Tottenham – Newcastle | premier_league | listad före spelstopp, Pinnacles namnform ej sparad | Tottenham - Newcastle United (odds hos Oddset från 2026-08-22) | – | – |
| topptipsetstryk | 978 | 3. Coventry – Hull | premier_league | listad före spelstopp, Pinnacles namnform ej sparad | Coventry City - Hull (odds hos Oddset från 2026-08-22) | – | – |
| topptipsetstryk | 978 | 5. Bolton – Lincoln | utanför Oddset | ingen Pinnacle-rad hos Oddset | – | – | – |
| topptipsetstryk | 978 | 8. Charlton – Preston | utanför Oddset | ingen Pinnacle-rad hos Oddset | – | – | – |
| topptipsetstryk | 979 | 2. Brighton – Leeds | premier_league | korrekt par fälls av tröskeln | Brighton - Leeds United (odds hos Oddset från 2026-08-24) | 1.0/0.588 | 0.794 |
| topptipsetstryk | 979 | 5. Nottingham – Tottenham | premier_league | korrekt par fälls av tröskeln | Nottingham Forest - Tottenham Hotspur (odds hos Oddset från 2026-08-24) | 0.741/0.692 | 0.716 |
| topptipsetstryk | 979 | 8. Millwall – Bolton | championship | listad före spelstopp, Pinnacles namnform ej sparad | Millwall - Bolton (odds hos Oddset från 2026-09-02) | – | – |

Poolmatcharens trösklar: sida ≥ 0.6, kombinerat ≥ 0.72 (`app/pinnacle.py`). Matcharen ingår i pit-v4:s datagenererande process: en ändring (alias, suffixstrippning, sänkt tröskel) gäller bara framåt och kräver ny featureversion eller ett explicit beslut om att pit-v4:s presence får ändra mening. Ingen historik bakfylls.
