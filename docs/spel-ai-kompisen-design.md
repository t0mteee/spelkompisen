# spel-ai-kompisen — design och byggplan (v3)

**Status:** godkänd av Saman 2026-10-01 ("Kör", efter sammanfattningen v2 och UI-skissen).
**Skriven av:** Claude. **Ersätter som styrande dokument:**
`docs/spel-ai-kompisen-plan-2026-10-01.md` (bakgrund, Codex ändringar i 3e288d6) och
`docs/spel-ai-kompisen-sammanfattning-2026-10-01.md` (beslutslistan v2). De ligger kvar som
historik. **UI-skiss:** https://claude.ai/artifact/SNZHbsGKMkDruBtm2TcuhS (privat för Saman,
exempeldata).

Det här dokumentet är kontraktet för Claude, Codex och agenten själv. Den som ändrar något
av det som står här ändrar det här först.

## 0. Samans beslut 2026-10-01

Alla rekommendationer i beslutslistan v2 är godkända, plus två tillägg från kvällen:

| # | Beslut |
|---|---|
| 1 | Tre villkor: fast facitmotor, ingen dubbel insamling, de fasta gränserna gäller |
| 2 | Agentens mandat i sidoprojektet är brett och utan rutingodkännanden |
| 3 | Agenten delar Samans Max-prenumeration; tak vecka 1: 8 AI-körningar per dygn, korta motiveringar inräknade |
| 4 | Privat repo `t0mteee/spel-ai-kompisen` |
| 5 | En idé flyttas till Spelkompisen bara av Saman, som ⚖, efter facit |
| 6 | Codex arbetar i Spelkompisen; agenten ensam i sidoprojektet |
| 7 | Gränserna i facitmotorn ärvs från Spelkompisen (avsnitt 5.6) |
| 8 | Resurser: låg prioritet (`nice`), högst 20 GB disk för sidoprojektet |
| 9 | Poolförslag per nivå: 256 kr alla poolspel; 512, 5 000, 20 000 och 39 366 kr för Stryktipset och Europatipset |
| 10 | 30-minutersförslaget är officiellt; 6 h-versionen är förhandsversion; båda får facit |
| 11 | Strategibyten är fria men loggas; facit skrivs aldrig om |
| 12 | 39 366 kr levereras som M-system att markera |
| 13 | Livekassan enligt avsnitt 7, med Svenska Spels liveodds som pris |
| 14 | Livekassan under 7 500 kr ⇒ inga nya spel och ett beslut till Saman |
| 15 | Beslutsinkorgen samlar även Spelkompisens ⚖, och Idag visar "N beslut väntar" |
| 16 | Nytt UI enligt avsnitt 10; Spelkompisens vyer nås via "Verktyg" |
| 17 | "Jag spelade detta" för pool och live; riktiga resultat följs separat |
| 18 | Notiser enligt avsnitt 9 |
| 19 | Notiskanal: ntfy med slumpat ämne; Claude-appens notiser provas |
| 20 | Sofascore: Flashscore som resultatkälla i Spelkompisen; V2.2-frågan blir eget ⚖ |
| 21 | Agenten kan lämna egna förslag (avsnitt 8) |
| 22 | Fyra roller, varav en tänker som en människa som använder verktyget (avsnitt 6) |

## 1. Syfte och mål

Saman ska slippa vara den som upptäcker fel, och agenten ska självständigt arbeta mot:

1. **Pool:** maximera vinstchanserna på Stryktipset, Europatipset och Topptipset, med olika
   strategier för små och stora system mot olika utdelningsspann.
2. **Odds:** en modell som förutser oddsrörelser eller på annat sätt pekar ut spelvärden.
3. **Live:** en modell som hittar spelvärda ögonblick (över/under, sida) ur liveodds,
   livestatistik och förväntad matchbild.
4. **Felsökning:** endpoints som slutar svara, siffror som saknas.
5. **Mer data:** fler källor eller annat som hjälper det dagliga arbetet.
6. **Spelbeslut:** veckobudget, insats per omgång och ett tydligt "avstå".
7. **Samans egna kuponger:** vad som kostat och vad som fungerat.
8. **Agentens kostnad mot nytta.**

Realistiska förväntningar: poolspelen behåller 30–40 % av insatserna, facit kräver cirka 40
omgångar per system, och de första månaderna visar troligen mest vad som inte fungerar.

## 2. Principer

1. **Agenten får ändra allt utom facit.** Den som väljer modell får inte också avgöra vad som
   räknas som bra. Allt som frysa, validera, rätta eller räkna hör till facitsidan.
2. **Klockan är vanliga schemalagda jobb.** AI:n förklarar och bygger men håller aldrig en
   tidsgräns ensam. Hinner den inte, går förslaget ut ändå med standardtext.
3. **Ingen dubbel insamling.** Spelkompisen samlar; sidoprojektet läser. Ny insamling som
   avgör facit (till exempel livepriser) ligger på facitsidan.
4. **Teknisk isolering, inte regler i en prompt.** Gränserna upprätthålls av sandbox och
   filrättigheter och provas innan agenten körs obevakad.
5. **De fasta gränserna gäller alla:** inga automatiska spel, källgränsen, inget i `svs` eller
   `vm`, inga hemligheter i repon, aldrig en databas i ett publikt repo.
6. **Missat är missat.** En frysning som inte sker i tid markeras missad och bakfylls aldrig.

## 3. Arkitektur

```
                 Saman (mobil: notiser, Claude-appen, webbläsare)
                    │                │                     │
             ntfy-notiser     chatt (Remote Control)   UI 5176 (+ Verktyg → 5175)
                    │                │                     │
┌───────────────── FACITSIDAN (betrodd) ─────────────────┐ │
│ Spelkompisen-repot, backend 8002, launchd-jobb          │◄┘ inkorg, facit, förslag, kassa
│ · insamling (oförändrad) + vakten                       │
│ · backend/app/spelai/: schemaläggare, frysning,         │
│   validering, rättning, livepriser, inkorg, notiser     │
│ · tabeller spelai_* i stryktips.db (backas upp nattligen)│
└──────────────▲───────────────────────────┬──────────────┘
               │ läser (mode=ro)           │ anropar agentens kod i sandbox,
               │                           │ läser bara stdout (JSON)
┌──────────────┴───── SIDOPROJEKTET (agentens) ─────────────────┐
│ ~/spel-ai-kompisen (privat repo, gaffel av Spelkompisen)       │
│ · backend 8003: agentens API (journal, kö, roller, förslag)    │
│ · frontend 5176: Hem, Beslut, Pool, Live, Agent                │
│ · agent/: strategier (pool, live, odds), minnesfiler           │
│ · ~/spel-ai-data/agent.db: agentens egna data                  │
│ · Claude-körningar: chattsession + schemalagda rollkörningar   │
└────────────────────────────────────────────────────────────────┘
```

**Facitsidan** är betrodd kod som Claude och Codex underhåller i Spelkompisen-repot med
samma tester, pushkrok och driftsättningsregler som resten av Spelkompisen. Agenten kan läsa
den men inte ändra den.

**Sidoprojektet** är agentens. Där får den ändra kod, modeller och UI, committa, driftsätta
och återställa. Det läser Spelkompisens databas skrivskyddat och skriver bara till sin egen
databas.

## 4. Repon, kataloger, portar och processer

| Vad | Plats | Skrivbar för agenten |
|---|---|---|
| Spelkompisen inkl. facitsidan | `~/spelkompisen` (publikt repo) | nej |
| Spelkompisens databas inkl. `spelai_*` | `~/spelkompisen/backend/data/stryktips.db` | nej, läs `mode=ro` (`-shm` får skrivas) |
| Sidoprojektet | `~/spel-ai-kompisen` (privat repo `t0mteee/spel-ai-kompisen`, `upstream` = Spelkompisen) | ja |
| Agentens data | `~/spel-ai-data/` (`agent.db`, uppgifter, skärmbilder, forskning) | ja |
| Hemligheter (ntfy-ämne) | `~/spelkompisen/backend/.env` (gitignorerad) | nej |

| Port | Tjänst |
|---|---|
| 8002 / 5175 | Spelkompisen backend / frontend (oförändrat) |
| 8003 / 5176 | sidoprojektets backend / frontend |

Launchd-jobb (alla i `tools/spelkompisen_tjanster.py`, alla syns för vakten):

| Etikett | Sida | Vad |
|---|---|---|
| `com.saman.spelai.schema` | facit | var 5:e min: frysningar vid 6 h och från 35 min, rättning, missade tillfällen, kassaspärr, startar rollkörningar inom taket |
| `com.saman.spelai.live` | facit | under pågående matcher varannan minut: livepriser, agentens livemodell i sandbox, validering och bokföring |
| `com.saman.spelai.backend` / `.frontend` | sidoprojekt | 8003 / 5176 |
| `com.saman.spelai.chatt` | sidoprojekt | den långlivade chattsessionen i tmux med Remote Control |

## 5. Facitmotorn (facitsidan)

Kod: `backend/app/spelai/` i Spelkompisen-repot. Tabeller i `stryktips.db`, skapade med
migreringsskript, backup och rapport (`docs/db-atgarder.md`). Allt är append-only; en rad
ändras eller tas aldrig bort.

### 5.1 Tabeller (utkast)

| Tabell | Innehåll |
|---|---|
| `spelai_pool_proposal` | produkt, omgång, nivå (kr), horisont (`6h`/`30m`), roll (`agent`/`standard`), strategiversion, radformat (`rows`/`msystem`), rader eller M-systemets tecken, radantal, hash, fryst tid, underlagets observationstider (odds, streck, omsättning) |
| `spelai_pool_result` | förslag-id, rätt per rad (bästa), utdelning utspädd med egna vinnande rader, ROI, facittid |
| `spelai_live_price` | match, marknad, lina, tecken, odds, marknad öppen/stängd, observationstid (HTTP `Age` avdragen), källa |
| `spelai_live_bet` | match, minut, ställning, marknad, lina, tecken, odds, prisets observationstid, insats, modellversion, motiveringsfält, lagt tid |
| `spelai_live_result` | spel-id, utfall (vinst/förlust/push/halv), netto, facittid, pris vid nästa observation (realism) |
| `spelai_run` | rollkörningar: roll, uppgift, start, slut, status, modell, kostnad/användning ur `--output-format json` |
| `spelai_inbox` | beslut och förslag: typ, källa (roll eller Spelkompisen), rubrik, varför, alternativ, rekommendation, sista tid, status |
| `spelai_inbox_answer` | svar: id, val, kommentar, tid, vem |
| `spelai_played` | "jag spelade detta" för pool och live |
| `spelai_event` | journal för facitsidans händelser: frysning, missat, spärr, notis skickad |

### 5.2 Poolfrysning

- Schemaläggaren frågar agentens byggare i sandbox:
  `python -m agent.forslag --produkt P --omgang N --niva K --horisont H` → JSON på stdout.
  Indata är det som finns i Spelkompisens databas vid den tidpunkten. Ingen nätåtkomst.
- Validering: rätt produkt och omgång, nivån inom budget (radpris 1 kr), giltiga tecken per
  match, inga dubblettrader. 39 366 som M-system: exakt 3 spikar, 1 halvgardering och 9
  helgarderingar. Ogiltigt svar ⇒ förslaget markeras `ogiltigt` och standarden visas i stället
  med tydlig etikett.
- **Standarden** byggs samtidigt med Spelkompisens byggare på samma budget, strategi medel,
  samma underlag, och fryses i samma minut.
- Tidpunkter: 6 h före spelstopp; officiellt bygge börjar 35 min före och ska vara fryst
  senast 30 min före. Utanför fönstret ⇒ `missat`.

### 5.3 Livebokföring

- Livepriser hämtas av facitsidan från Svenska Spels öppna Kambi-flöde, bara för matcher som
  är live och har livestatistik, högst ett anrop per match och varv, varannan minut.
- Agentens livemodell anropas i sandbox med matchläget (minut, ställning, statistik,
  förväntad matchbild före avspark, aktuella priser) och svarar med spelavsikter.
- Validering: insats 50–200 kr i steg om 50, högst 3 spel och 600 kr per match, priset högst
  60 s gammalt och marknaden öppen, kassan minst 7 500 kr. Ett godkänt spel bokförs till det
  observerade priset. Inga villkor i efterhand.
- Rättning på ordinarie tid; handikapp med push och halvvinst. Priset vid nästa observation
  sparas som realismmått och används aldrig för att sortera bort spel.

### 5.4 Rättning och facit

- Pool: verkligt utfall ur `pool_draw_settlement` och publicerad utdelning, utspädd med egna
  vinnande rader (PH3-metoden). Agentens förslag och standarden rättas på samma sätt.
- Live: avräkning mot resultat i ordinarie tid.
- Odds: agentens oddsmodell fryser prognoser vid horisonter; facit mot Pinnacles stängning
  (CLV) och logloss mot utfall.

### 5.5 Inkorgen

- Agenten skapar beslut och förslag som JSON-filer i `~/spel-ai-data/utkorg/`. Schemaläggaren
  läser in och validerar dem. Agenten läser svaren ur databasen men kan inte skriva dem.
- Saman svarar på Spelkompisens beslutssida (betrodd kod, 5175); sidoprojektets Beslut-flik
  visar listan och öppnar den sidan för svaret. Svaret sparas i `spelai_inbox_answer` med
  klientens adress och webbläsare. Ett svar som kommer från servern själv larmar.
- Tak och budgetar (till exempel antal körningar per dygn) läses av schemaläggaren ur
  besvarade beslut. Ett absolut tak står i facitsidans kod och ändras bara av Claude eller
  Codex, så att agenten aldrig kan höja sitt eget tak.
- Spelkompisens ⚖-punkter flyttas in från `docs/backlog.md` som beslut med källa
  "Spelkompisen". Idag i Spelkompisen visar "N beslut väntar".

### 5.6 Gränser (ärvda från Spelkompisen)

| Område | Gräns innan något kallas en förbättring |
|---|---|
| Pool | minst 40 parade omgångar mot standarden och BH-FDR 10 % över nivåerna |
| Odds | CLV-grönt v2: minst 50 stängda och undre bootstrap-KI-gräns > 0 |
| Live | minst 200 avgjorda spel, minst 60 dagar och undre KI90 > 0 |

Gränserna sätts i facitmotorn. Agenten får visa siffror innan dess men aldrig kalla dem en
förbättring.

### 5.7 API (Spelkompisens backend, 8002)

`GET /api/spelai/pool` (förslag, standard, facit per nivå) · `GET /api/spelai/live` (kassa,
öppna, avgjorda, per marknad) · `GET /api/spelai/inbox` · `POST /api/spelai/inbox/<id>/svar`
(från Spelkompisens beslutssida) · `POST /api/spelai/spelat` · `POST /api/spelai/paus` ·
`GET /api/spelai/korningar`. Alla GET är rena läsningar.

## 6. Agenten och rollerna

| Roll | Ansvar | När | Modell |
|---|---|---|---|
| **Koordinatorn** | Chattar med Saman, fördelar arbete, skriver journal och morgonrapport | alltid nåbar i Claude-appen | Opus |
| **Forskaren** | Pool, odds och live: provar idéer i bakgrunden och sköter de officiella strategierna | forskningspass 10:00 (och 15:00 från vecka 2), motiveringar till förslagen | Opus |
| **Granskaren** | Prövar varje påstådd förbättring och varje strategibyte mot facit; letar efter tur, överanpassning och data som inte fanns i tid. Kan stoppa ett påstående, inte en driftsättning | före varje byte och varje "förbättring" | Opus |
| **Användaren** | Använder appen som Saman: öppnar den i headless Chrome i mobilformat (390×844) när Saman skulle göra det, läser skärmbilderna och lämnar förslag på det som är otydligt | vid förslagen 6 h och 30 min före stopp (kort), söndagar en hel genomgång | Sonnet |
| **Driften** | Vaktens larm, felsökning, rättningar, nya datakällor | morgonrunda 07:00 och vid nytt rött larm (högst 3 per dygn) | Sonnet |

- Rollerna definieras som Claude Code-agenter i sidoprojektets `.claude/agents/`.
- Schemalagda rollkörningar startas av facitsidans schemaläggare som separata
  `claude -p`-körningar med rollens instruktioner, inom taket. Varje körning bokförs i
  `spelai_run` med användning ur `--output-format json`.
- Chattsessionen lever i tmux, bevakas av launchd och har Remote Control. Den läser
  journalen och kan starta en roll på Samans begäran, men den är inte klockan.
- Minnet ligger i filer i sidoprojektet: `agent/mal.md`, `agent/journal.md`,
  `agent/beslut.md`, `agent/ko.md`, `agent/strategier.md`.

## 7. Poolförslagen och livekassan (sammanfattning)

**Pool:** ett officiellt förslag per spel och nivå enligt beslut 9–12. Topptipset får bara
256 kr, eftersom 8 matcher ger 6 561 möjliga rader. Radfil (Egna rader) upp till 20 000 rader;
39 366 som M-system. Strategibyten loggas med skäl. Notis per spel och tidpunkt, samlad för
alla nivåer.

**Live:** fiktiv kassa 10 000 kr; 50–200 kr per spel; 1–3 spel per match; över/under och sida;
Svenska Spels liveodds; spärr vid 7 500 kr. Koden lägger spelen i livevarvet; agenten går
igenom dem varje morgon. Ingen notis per spel; gårdagens resultat i morgonrapporten.

## 8. Beslut och förslag

| Typ | Vem skapar | Vad händer |
|---|---|---|
| **Beslut** | koordinatorn eller Spelkompisen | Görs inte förrän Saman svarat. Gäller allt utanför mandatet: facitregler, Spelkompisen, budget, kassaspärren |
| **Förslag: förbättring** | vilken roll som helst | Genomförs i sidoprojektet efter 24 h om Saman inte säger nej. Gäller sådant som ändrar hur Saman använder appen: UI, notiser, förslagens format |
| **Förslag: spelråd** | Forskaren | Bara ett råd, till exempel "avstå Europatipset 2613"; inget ändras |

Övrigt inom mandatet görs direkt och syns i journalen.

## 9. Notiser

- Kanal: ntfy med ett långt slumpat ämne i `backend/.env`. Claude-appens egna notiser provas
  för agentens del.
- Notis vid: nytt beslut, poolförslag (en per spel och tidpunkt), morgonrapport, klart eller
  misslyckat arbete, driftsättning eller återställning, missat förslag, agentsessionen nere mer
  än 30 min, kassaspärr.
- Startnotis bara vid driftsättning. Tysta timmar 23–07 utom beslut med sista tid.
- En notis innehåller aldrig kuponger, insatser eller loggar — bara vad som hänt och en länk.
- Detta återaktiverar inte Spelkompisens odds- och signalnotiser (pausade sedan 2026-07-16).

## 10. UI (sidoprojektet, port 5176)

Fem flikar, mobil först, mörkt tema som Spelkompisen (se skissen):

| Flik | Innehåll |
|---|---|
| Hem | beslut och förslag som väntar, dagens poolförslag med nedräkning, livekassan, vad agenten gör, driftlarm, Verktyg |
| Beslut | Beslut / Förslag / Besvarade. Svarsknapparna (Godkänn rekommendationen, Välj annat, Kommentera; för förslag Kör nu, Nej, Kommentera) ligger på Spelkompisens beslutssida, som fliken öppnar (5.5) |
| Pool | spel × nivå med status, öppnat förslag med rader, spikar, ändringar 6 h → 30 min, motivering, jämförelse mot standarden, radfil och "Jag spelade detta"; facit per nivå; strategibyten |
| Live | kassa och graf, öppna spel, dagens avgjorda, per marknad |
| Agent | arbetar nu, roller, kvot, journal, forskningskö, notislogg, Pausa/Återuppta |

"Verktyg" länkar till Spelkompisens vyer på 5175. Pausknappen stoppar rollkörningar,
poolförslag och livespel via en flagga som facitsidan läser.

## 11. Säkerhet och isolering

- Samma macOS-konto. Claude Code-sandboxen är påtvingad för agenten: ingen möjlighet att köra
  kommandon utanför sandboxen.
- Skrivbart för agenten: `~/spel-ai-kompisen`, `~/spel-ai-data`, temporära kataloger och
  `stryktips.db-shm`. Allt annat är skrivskyddat, och `~/svs`, `~/vm`, `.env`-filer och
  `~/.ssh` är spärrade även för läsning.
- Nätverk för agenten: GitHub, Anthropic och de källor som är tillåtna enligt källgränsen.
- När facitsidan kör agentens kod sker det i en egen sandbox (`sandbox-exec`) utan nätverk och
  utan skrivrätt utanför `~/spel-ai-data`. Bara stdout läses.
- Gränsprov innan agenten körs obevakad: skrivning i `~/spelkompisen`, i databasen, i
  facitsidans tabeller och i `~/svs` ska nekas; läsning av databasen ska fungera; ett
  kommando utanför sandboxen ska nekas.

## 12. Byggordning

| Fas | Innehåll | Klart när |
|---|---|---|
| A | Detta dokument | ✅ 2026-10-01 |
| B | Facitsidan: tabeller (skript + backup), validering, standard, rättning, inkorg, API, schemaläggare utan agent | tester gröna; en torrkörning fryser standarden vid 6 h och 30 min för nästa omgång |
| C | Sidoprojektet: privat repo, gaffel med `upstream`, egen venv och node_modules, portarna, `agent.db`, minnesfiler, sidoprojektets CLAUDE.md, rollerna, sandboxinställningar | gränsproven i avsnitt 11 godkända |
| D | Poolförslag hela vägen: agentens första strategi = Spelkompisens byggare per nivå, notiser, Pool-fliken | ett riktigt förslag 6 h och 30 min före ett spelstopp, rättat efter omgången |
| E | Livekassan: livepriser, bokföring, rättning, Live-fliken; agentens första livemodell | spel bokförs och rättas under en matchdag |
| F | Agentkörningar: chattsession med Remote Control, schemalagda roller, tak, journal, morgonrapport | en hel dag med morgonrunda, forskningspass och motiveringar |
| G | UI klart: Hem, Beslut, Agent; Spelkompisens Idag-banner; ⚖-punkterna flyttade till inkorgen | Saman kan svara på ett beslut i mobilen |
| H | Provvecka och utvärdering: kvot, kvalitet, notiser, UI | dag 8 |

## 13. Ändringar i Spelkompisen som följer

- Facitsidan (fas B), inkorgsbannern på Idag och flytten av ⚖-punkter (fas G).
- Sofascore: Flashscore som resultatkälla för ligor utan football-data och källprovet utan
  Sofascore (beslut 20); V2.2-frågan som eget ⚖ i inkorgen.
- Vakten bevakar de nya jobben.

## 14. Öppna tekniska frågor (Codex får gärna svara här)

1. Räcker `sandbox-exec` för att köra agentens kod från facitsidan, eller behövs något annat
   på macOS?
2. SQLite i WAL-läge: fungerar skrivskyddad läsning från agentens sandbox när bara `-shm` är
   skrivbar?
3. Tar Svenska Spels Egna rader verkligen högst cirka 20 000 rader per fil?
4. Vilken publik Kambi-endpoint ger liveodds per match med minst last, och vilken `max-age`
   har den?
5. Visas behörighetsfrågor och notiser från en Remote Control-session i Claude-appen?
6. Hur länge kan chattsessionen leva innan den bör startas om med ny kontext?
7. Kan Claude Code-sandboxen spärra agentens nätåtkomst till 8002 och 5175 men tillåta 8003
   och 5176? Om inte gäller loggning av svarens klient, larm och det absoluta taket (5.5).

## 15. Ordlista

- **Facitsidan:** betrodd kod och data i Spelkompisen som fryser, validerar och rättar.
- **Standarden:** Spelkompisens byggare på samma budget och tidpunkt, strategi medel.
- **Officiellt förslag:** 30-minutersversionen per spel och nivå.
- **Förhandsversion:** 6 h-versionen.
- **Rollkörning:** en schemalagd `claude -p`-körning med en rolls instruktioner.
