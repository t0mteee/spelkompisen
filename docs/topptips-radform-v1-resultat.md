# Topptips radform v1 — historiskt resultat

Körd 2026-08-24/25 efter förregistreringen i
`docs/topptips-radform-v1-forregistrering.md`. Ingen produktionsmodell,
standardinställning eller historisk frysning ändrades.

## Data och delning

- Fixerad read-only-snapshot: 403 742 720 byte, SHA-256
  `c969748888b80d1f295b30903f5a57076fbe4a25263e7484d7fff7d36b7faa4d`.
- Period: 2024-01-01–2026-08-23.
- 1 985 kompletta Topptipsomgångar: Dagens 1 586, Stryk 134 och Extra 265.
- Äldsta 1 388 omgångarna (70 procent per produkt) tränade radformen. Senaste
  597 var holdout och rördes inte när modellen specificerades eller tränades.
- Alla system kostar 384 kronor/rader. Armarna ser samma öppningsodds och
  slutstreck. Resultatet är därför en relativ `final_only`-screening, inte ett
  point-in-time-bevis eller en spelbar absolut ROI-prognos.

Råresultat och varje omgång finns i
`docs/topptips-radform-v1-resultat.json`.

## Vad modellen lärde sig

Multiplikatorn läggs på respektive produkts befintliga kappa. Högre värde
betyder fler väntade medvinnare och därmed lägre beräknad utdelning för raden.

| Radens antal X | Multiplikator | Tolkning mot dagens modell |
|---:|---:|---|
| 0 | 1,0566 | cirka 5,7 % fler medvinnare |
| 1 | 0,9759 | cirka 2,4 % färre |
| 2 | 0,9874 | cirka 1,3 % färre |
| 3 | 1,0482 | cirka 4,8 % fler |
| 4+ | 1,0798 | cirka 8,0 % fler |

Historiken säger alltså inte att alla kryssrika rader är underspelade. Rader
med 3–4+ X hade tvärtom fler medvinnare än dagens enhetliga prognos väntade.
Det är orsaken till att huvudkandidaten inte är en manuell X-bonus.

## Resultat på orörd holdout

| Modell | 8 rätt | Rå medel-ROI* | Beräknad träffchans | X/rad | Facit-X omöjligt |
|---|---:|---:|---:|---:|---:|
| Dagens modell | 204/597 (34,17 %) | −5,50 % | 35,78 % | 1,406 | 50 |
| **Radform v1** | **208/597 (34,84 %)** | **+0,19 %** | 35,76 % | 1,390 | 55 |
| Full X-balans | 203/597 (34,00 %) | −5,71 % | 34,42 % | 2,005 | 0 |
| Träffsäkert läge, värdevikt 0 | 225/597 (37,69 %) | −12,51 % | 37,56 % | 1,446 | 48 |

\* Rå ROI är känslig för enstaka stora utdelningar och är inte
point-in-time. Projektets primära jämförelse är därför parad och winsoriserad.

Radform v1 mot dagens modell:

- fyra kandidatunika 8-rättsträffar och noll current-unika;
- +0,67 procentenheters parad träffskillnad, 90 % KI
  `[+0,17..+1,17]`;
- +1,34 procentenheters parad winsoriserad ROI-skillnad, 90 % KI
  `[+0,34..+2,35]`;
- bara −0,02 procentenheters beräknad marknadsträff;
- i genomsnitt 9,8 av 384 rader byttes ut.

Begränsningen är viktig: på utvecklingsperioden hade radformen 379 mot 383
träffar och −0,67 procentenheters parad winsoriserad ROI-skillnad med KI över
noll. Holdout är positiv men bärs av endast fyra skiljande toppträffar. Det är
ett tillräckligt fynd för en forward-challenger, inte för att ersätta
standardbyggaren.

Full X-balans eliminerade alla 50 fall där facit hade fler X än någon rad,
men bytte i genomsnitt 84 rader, sänkte den marknadsberäknade träffchansen med
1,35 procentenheter och gav 18 egna respektive 19 förlorade toppträffar.
Träff- och ROI-KI korsar noll. Den underkänns som ensam standardmodell.

Värdevikt 0 gav fler toppträffar i både utveckling och holdout och högre
beräknad träffchans. Den råa medel-ROI:n var samtidigt sämre eftersom armen
oftare fångar folkligare, lägre betalda utfall och missar vissa sällsynta stora
vinster. Det är ett rimligt val för högre träfffrekvens, men inte en lösning på
fyrkryssproblemet.

## Topptipset 4289 — enbart illustrativ efterhandskontroll

Omgången var utesluten ur både träning och holdout. Med öppningsodds och
slutstreck gav rekonstruktionen:

| Modell | 8 rätt på `21XX21XX` | Bäst | Snitt X | 4+ X-rader |
|---|---:|---:|---:|---:|
| Dagens modell | nej | 7 | 1,104 | 0 |
| Radform v1 | nej | 7 | 1,094 | 0 |
| Full X-balans | **ja** | **8** | 2,023 | 45 |
| Värdevikt 0 | nej | 7 | 1,182 | 0 |

Det visar varför Samans invändning är relevant, men får inte användas som
bevis för full X-balans: samma arm var marginellt sämre på den stora holdouten.
Kontrollen använder dessutom slutstreck, inte exakt streckbild när den riktiga
kupongen spelades.

## Beslut och nästa steg

1. Standardbyggaren ändras inte på `final_only`-evidens.
2. `topptips-radform-v1` är godkänd för en separat 384-raders
   point-in-time-forwardarm. Den får aldrig blandas med PH5-v3 eller verkligt
   spelade kuponger.
3. Full X-balans underkänns som ensam modell men är nyttig som diagnostisk
   svansarm.
4. Nästa X-specifika kandidat bör vara en liten, förregistrerad
   **svansportfölj**: behåll huvuddelen av current och använd en begränsad del
   av budgeten för X-rader som current lämnar utanför. Andelen får inte väljas
   på den redan granskade holdouten; den måste låsas i en ny version och sedan
   utvärderas framåt.
5. Värdevikt 0 ska presenteras som “högre historisk träfffrekvens, lägre
   utdelningsprofil”, inte som ett sätt att försäkra sig mot många X.
