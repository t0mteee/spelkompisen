# PH5 v3 — täthetssvep 4 096/5 000 rader

Datum: 2026-08-14. **Förregistrerad före körning.**

**Status:** körkontrakt låst; körning ännu inte startad.

## Frågan

PH5 v2 visade att värderadernas underskott mot slump på Stryktipset krympte
med budgeten: **−8,2 → −5,0 → −2,3 procentenheter** vid 100, 256 och 512
rader. Europatipset låg nära neutralt. Vi testar nu den praktiska budget Saman
faktiskt överväger:

> Slår den befintliga medelbyggarens radval naiva kontroller vid 4 096 eller
> exakt 5 000 rader på Stryktipset respektive Europatipset?

Detta lokaliserar inte en matematisk korsningspunkt. Eftersom 1 024 och 2 048
inte testas kan utfallet bara motivera **lägsta testade budget**, aldrig
"lägsta möjliga budget".

## Varför historisk ablation först

Det frysta forward-facitet är fortfarande det enda beviset för framtida
prestanda, men underlaget kommer långsamt. Vid mätningen 2026-08-14 fanns bara
sex settlade forward-system och promotionsgrinden kräver minst 40 parade
omgångar. Noll toppvinster på några veckor vore det sannolika utfallet och
säger nästan ingenting.

Den historiska analysen kan däremot använda hundratals kompletta omgångar och
samtliga vinstnivåer, inte bara 13 rätt. Den väljer en kandidat snabbt; den
validerar den inte framåt.

## Fyra låsta körningar

| Produkt | Budget/rader |
|---|---:|
| Stryktipset | 4 096 |
| Stryktipset | 5 000 |
| Europatipset | 4 096 |
| Europatipset | 5 000 |

Endast 13-matchsspelen ingår. En 8 192-körning har tagits bort: de gamla
kontrollerna bygger ett binärt `2^13 = 8 192`-universum och skulle då spela
varenda kandidat. Armarna blev identiska och kontrollen kunde omöjligen
underkänna metoden. Dessutom är 5 000 den riktiga produktfrågan.

Topptipsetfamiljen ingår inte. Där motsvarar 4 096 rader 62 % av hela
utfallsrummet `3^8 = 6 561`, alltså mattbombning snarare än radval.

## Fast kohort före armbygget

Kohorten är `final_only-radval-v3-fixed-payout` och skapas **innan** någon arm
byggs. En omgång får vara med endast om:

- den har exakt 13 ej inställda matcher med facit, slutstreck och öppningsodds;
- omsättning och radpris är positiva;
- samtliga planerade vinstnivåer har både belopp och fler än noll officiella
  vinnare.

Sista kravet gör att utdelningen kan räknas för vilken arm som helst. I v2
föll en omgång bort först när en viss arm träffade en nivå med noll vinnare;
därför kunde budget och arm i smyg ändra kohorten. V3 kräver samma omgångs-ID:n
och `n_incomplete_payout = 0` i båda budgetarna.

Audit före körning gav 8 335 settlementrader över alla fem produkter, men bara
**216 Stryktips- och 477 Europatipsomgångar (693 totalt)** i den relevanta,
fasta kohorten. Talet 8 324 i den första planen var därför missvisande och får
inte användas som analysens n.

## Armar

Alla armar spelar samma antal rader och utvärderas mot samma omgång.

1. `varderader` — oförändrad `build_ev_system`, medel, värdevikt 0,5.
2. `folkrad` — de mest strecksannolika raderna i den gamla binära
   kandidatpoolen.
3. `favoritrad` — marknadens mest sannolika rader i samma binära pool.
4. `byggarslump` — slump ur **exakt produktionsbyggarens kandidatuniversum**,
   inklusive dess helgarderingar på öppna matcher. Kandidattecknen hämtas från
   samma hjälpfunktion som byggaren använder.
5. `slump` — den gamla binära slumpen behålls som historisk diagnostik men är
   inte ensam promotionskontroll.

Hamming-armen körs inte. Dess giriga sökning är `O(rader × kandidatpool)` och
skulle dominera körtiden vid dessa budgetar, medan den inte ingår i frågan.

## Primärt mått och osäkerhet

För varje omgång räknas `varderader − kontroll` i ROI. Differensen winsoriseras
till ±200 procentenheter och medelvärdet av de winsoriserade parade
differenserna är huvudmåttet. Omgången är bootstrap-block.

JSON sparar:

- punktskattning, median, vinstandel, 90- och 95-procentigt KI;
- rå ROI och faktiskt radantal per arm och omgång;
- byggarens kandidatuniversum per omgång;
- commit, databassnapshot, seed och antal bootstrapdrag.

Körningen använder 2 000 bootstrapdrag. **95 %-KI är beslutskriteriet.** Två
budgetar granskas per produkt; ett tvåsidigt 95 %-intervall motsvarar en
2,5-procentig ensidig gräns per budget och håller den ensidiga
familjefelnivån högst 5 % med Bonferroni över budgetsökningen. Kravet att slå
alla tre primära kontroller är ett intersection-union-test och kräver ingen
ytterligare lättnad.

## Beslutsregel, låst före körning

Beslut fattas separat för Stryktipset och Europatipset.

1. Körningen är giltig bara om båda budgetarna har exakt samma fasta kohort,
   noll ofullständiga utdelningar, noll byggfel och fullt radantal i alla
   primära armar.
2. En budget passerar bara om den undre 95 %-KI-gränsen är över noll mot
   `folkrad`, `favoritrad` **och** `byggarslump`.
3. Om 4 096 passerar väljs 4 096. Annars väljs 5 000 endast om 5 000 passerar.
   Det kallas alltid "lägsta testade budget".
4. Om ingen budget passerar registreras ingen ny forward-nyckel. Nästa
   experiment ska då ändra själva rankningen, inte köpa fler rader.
5. Om 4 096 passerar men 5 000 inte gör det, eller kurvan annars blir tydligt
   icke-monoton, sker ingen automatisk registrering; orsaken granskas först.

Punktskattning, toppnivåträffar eller den gamla binära slumpen får inte ensamma
promovera en budget.

## Om en budget passerar

Den får inte läggas till i globala `BUDGETS`, eftersom det automatiskt skulle
skapa säker/medel/tuff-varianter som aldrig testats. I stället registreras
exakt en produktstyrd medelnyckel för varje 13-matchsprodukt som själv
passerar. En ny nyckel ger två nya forward-jämförelser per produkt (h3 och
m20), alltså högst fyra tillägg om båda produkterna passerar. Befintlig
BH-FDR-grind och kravet på minst 40 parade omgångar gäller oförändrat.

Nyckeln ska märkas som historiskt vald. Ablationen får aldrig senare citeras
som forward-validering.

## Tolkning och begränsningar

Alla armar ser slutstrecket, vilket inte fanns vid verkligt spelbeslut. Absolut
ROI är därför ett **optimistiskt, icke-PIT estimat**, inte en prognos och inte
en bevisad övre gräns. Den parade jämförelsen är ändå relevant för radvalet
eftersom armarna får samma information.

Analysen svarar inte på om poolspelet är lönsamt efter uttag, jackpotvariation
eller framtida marknadsförändring. Den svarar bara på om vår nuvarande
radrankning slår tre specificerade alternativ vid två praktiska tätheter.

## Reproducerbar körning

Körningen ska ske sekventiellt och lågprioriterat från en fixerad commit mot en
SQLite-snapshot, aldrig mot den växande produktionsdatabasen:

```bash
PH5_PYTHON=/Users/saman/spelkompisen/backend/.venv/bin/python \
  nice -n 10 backend/scripts/run_ph5_tathetssvep_v3.sh \
  /tmp/ph5-v3-snapshot.db /tmp/ph5-v3-resultat
```

JSON-filer och logg kopieras in i `docs/` först när samtliga körningar är
klara och kontrollerade. Startcommit, snapshot-hash, process-id och sökvägar
läggs då under statusraden ovan.
