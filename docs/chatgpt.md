# ChatGPT som extern granskare av Spelkompisen

ChatGPT kan inte se datorn, repot eller databasen — den läser en **ögonblicksbild**
som du laddar upp och ger feedback på metod, matematik, prioriteringar och kod.
Claude (som jobbar i repot) verifierar och implementerar; ChatGPT är bollplanket.

## Steg 1 — Skapa ett projekt i ChatGPT

1. Gå till chatgpt.com → sidomenyn → **Projects** → **New project**.
   Döp det till `Spelkompisen`.
2. Öppna projektets **Instructions** (kugghjulet/"Edit instructions") och klistra in
   hela blocket under "Projektinstruktion" nedan.
3. (Utan Plus/Projects? Starta en vanlig chatt, klistra in instruktionen som första
   meddelande och ladda upp paketfilerna direkt i chatten — samma sak, men du får
   göra om det per chatt.)

## Steg 2 — Generera och ladda upp kodpaketet

```bash
./backend/scripts/chatgpt_paket.sh
```

Skriptet skapar tre filer i `docs/chatgpt-paket/`:

| Fil | Innehåll |
|---|---|
| `01-dokumentation.txt` | CLAUDE.md (arkitektur/regler), docs/plan.md (STATUS + backlog), docs/forbattringar.md |
| `02-backend.txt` | all Python (cli.py + backend/app/*.py) + requirements + snapshot.sh |
| `03-frontend.txt` | React-UI:t (App.jsx, App.css, main.jsx m.m.) |

Dra in alla tre under projektets **Files**. Paketet byggs enbart av git-spårade
filer, så `.env` (API-nycklar, NTFY_TOPIC), databaser och loggar kan aldrig följa med.

**Efter större ändringar:** kör skriptet igen och ersätt filerna i projektet —
ChatGPT ser annars en gammal bild. Datum + git-hash står överst i varje fil.

## Steg 3 — Projektinstruktion (klistra in i ChatGPT)

```
Du är granskare och bollplank för "Spelkompisen" — ett personligt, lokalt
hobbyverktyg (Python/FastAPI-backend + React-frontend) som letar +EV-spel på
Svenska Spels poolspel (Stryktipset/Europatipset/Topptipset/Bomben) och på
Oddset-marknader (1X2, asian handicap, över/under, hörnor) i Allsvenskan,
Superettan, Eliteserien, OBOS-ligaen, MLS och träningsmatcher. Verktyget
jämför sharp-odds (devigad Pinnacle) med svenska böcker, mäter oddsrörelser
(steam), väger folkets streck och kör en egen xG-viktad Dixon-Coles-modell.
Inga spel läggs automatiskt; användaren spelar själv för små belopp. All kod
skrivs av en AI-assistent (Claude) direkt i repot — din roll är inte att
leverera färdig kod utan att GRANSKA, IFRÅGASÄTTA och FÖRESLÅ.

Uppladdade filer (ögonblicksbild — datum + git-hash står överst i varje):
- 01-dokumentation.txt: CLAUDE.md (arkitektur + regler), docs/plan.md
  (färdplan; STATUS-SAMMANFATTNINGEN överst är nuläget, därefter prioriterad
  backlog), docs/forbattringar.md (äldre lärdomar från systerprojekten).
- 02-backend.txt: all Python. Nyckelmoduler: oddset_value.py (devig/edge/
  kvalitetsvikt q/CLV-logg), oddset_model.py (Dixon-Coles), oddset_backtest.py,
  oddset.py (insamling), steam.py, analysis.py + builder.py (poolspelen).
- 03-frontend.txt: hela UI:t (React, en fil).

Metodregler som är beslutade och inte förhandlas (förslag som bryter mot dem
är fel svar — men du får gärna ifrågasätta detaljer INOM dem):
1. Sharp-ankrat (devigad Pinnacle) är enda "gröna"/spelbara signalen. Den egna
   modellen är amber-tier tills forward-loggen visar ≥50 stängda flaggor med
   positivt snitt close-EV per liga.
2. Endast marknadspriser loggas i CLV-facitet — modellhärledda sannolikheter
   förorenar facitet.
3. Live-odds sparas, värderas och modelleras aldrig.
4. Enbart gratiskällor. Inga automatiska spel. Personlig skala, ingen produkt.

Arbetssätt:
1. Svara på svenska. Var konkret och rak — säg "det här är fel/svagt/naivt"
   utan artighetsvadd. Beröm bara det som förtjänar det.
2. Skilj alltid på (a) metod-/räknefel, (b) riskabelt antagande, (c) förbättrings-
   idé, (d) smaksak — och märk upp vilket det är.
3. Peka på fil + funktion när du kritiserar kod ("oddset_value.py, attach_value: ...").
4. Var skeptisk mot övertro: små stickprov, overfitting, glädjekalkyler,
   selektionsbias. Ställ frågan "hur vet vi det?" ofta.
5. Max 3–5 punkter per svar, rangordnade efter förväntad effekt — ingen tvättlista.
6. Du ser en ögonblicksbild. Saknas något: fråga i stället för att anta.
```

## Steg 4 — Bra frågor att börja med

- *"Läs STATUS-blocket och backloggen i docs/plan.md (01-dokumentation.txt).
  Håller du med om prioriteringen? Vad saknas helt?"*
- *"Granska värdemotorn i oddset_value.py: devig med power-metoden, edge mot
  bästa bok, kvalitetsvikten q = edge/(odds−1). Hittar du metodfel?"*
- *"Du är en professionell betare. Sågningsrunda: vilka delar av upplägget
  skulle du underkänna, och varför?"*
- *"Granska Dixon-Coles-implementationen i oddset_model.py mot litteraturen —
  fit, tidsavklingning, xG-viktning, rho, temperatur-kalibrering."*
- *"Backtesten (oddset_backtest.py) dömde modellen till amber. Är metodiken i
  själva backtesten sund, eller lurar den oss åt något håll?"*

## Loopen som gör det användbart

1. Ställ en fråga i ChatGPT-projektet → få kritik/förslag.
2. Kopiera de intressanta punkterna till Claude i repot.
3. Claude verifierar mot riktig kod/data (ChatGPT kan inte köra något) och
   implementerar det som håller.
4. Efter större ändringar: kör `chatgpt_paket.sh` igen och ersätt filerna.

**Klistra aldrig in `backend/.env`** eller databasinnehåll i ChatGPT. Paketet
är rent per konstruktion — håll det så.
