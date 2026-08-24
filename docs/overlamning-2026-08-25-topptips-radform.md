# Överlämning 2026-08-25 — Topptipsets radform och X-backtest

## Kort status

Samans faktiskt spelade Topptipset 4289 (`21XX21XX`) hade fyra X medan hans
384 rader saknade alla 4X-rader. Den exakta kupongen, inte PH5-frysningen, var
utgångspunkten. Ingen spelad kupong eller produktionskonfiguration har ändrats.

Två isolerade researchbyggare finns nu i `backend/app/builder.py`:

- `build_topptips_row_shape_system` / `topptips-radform-v1`: samma
  matchsannolikheter och radscore som current men separat medvinnarkappa för
  0, 1, 2, 3 och 4+ X;
- `build_topptips_x_balanced_system` / `topptips-xbalans-v1`: diagnostiskt
  stresstest som fördelar 384 rader enligt marknadens sannolikhet för antal X.

Ingen av dem anropas av ordinarie API eller autoinsamling. Den exakta
Topptips-snabbvägen i `_rank_ev_rows` är testad matematiskt likvärdig med den
gamla Poisson-binomialvägen och gör full ranking av 6 561 rader snabb nog.

## Resultat

Förregistreringar:

- `docs/topptips-radform-v1-forregistrering.md`
- `docs/topptips-xbalans-v1-forregistrering.md`

Full rapport: `docs/topptips-radform-v1-resultat.md`; rådata per omgång:
`docs/topptips-radform-v1-resultat.json`.

Modern era gav 1 388 utvecklings- och 597 senare holdoutomgångar. Radform v1
gav 208 mot currents 204 toppträffar, fyra egna/noll förlorade, och +1,34 pp
parad winsoriserad ROI med 90 % KI `[+0,34..+2,35]`. Den bytte bara 9,8 av
384 rader i snitt. Utvecklingsperioden var dock svagt negativ och de fyra
skiljande utfallen är få: starta forward-challenger, byt inte standard.

Full X-balans gav 203 mot 204 träffar och lägre marknadsberäknad träffchans.
Den hade fångat 4289 i final_only-rekonstruktionen men underkänns som generell
standard. Värdevikt 0 gav 225 träffar och högre träffchans men sämre rå ROI;
även den saknade 4X-rad på 4289.

## Rekommenderad fortsättning

1. Lägg `topptips-radform-v1` som en separat 384-raders researchnyckel vid h3
   och m20 från första ännu ofrysta Topptipsomgång. Ingen retrofrysning.
2. Visa den under 5 000-test/research med eget namn trots 384-radersbudget;
   blanda den inte i PH5-v3:s Stryk/Europa-facit.
3. Förregistrera därefter en liten X-svansportfölj som behåller majoriteten av
   current och ersätter en låst andel med X-balansens unika rader. Välj inte
   andelen på den redan öppnade 2024+-holdouten.
4. Efter minst 40 point-in-time-omgångar: jämför parat current, radform och
   svansportfölj på toppträff, winsoriserad ROI, portföljträff och antal
   X-omöjliga facit. Standard får ändras först då.

## Verifiering och drift

- 18 riktade buildertester gröna före fullkörningen.
- Backtestet öppnar snapshoten read-only och sparar hash, kodversion,
  träningskoefficienter, summeringar samt varje omgång.
- Produktionsservern har inte driftsatts med kandidaterna och databasen har
  inte migrerats eller skrivits.

