# Pooloptimerare v1 — teknisk pilot och överlämning

Datum: 2026-08-30

## Kort besked

Den lokala, read-only Topptipsoptimeraren är implementerad och tekniskt
verifierad. Den kan prova upp till 10 000 deterministiska sätt att välja exakt
256 rader utan att ändra sannolikhetsmodellen, produktionsbyggaren, UI:t eller
någon kupong. Körningen sker lokalt i Python och använder inga AI-token.

Ingen ny modell är vald. En liten pilot med 500 konfigurationer bevisar att
motorn, gallringen, checkpointen och multiprocessing fungerar, men dess 12
slutauditomgångar är alldeles för få för modellslutsatser.

Förregistreringen som frystes före piloten finns i
`docs/pooloptimerare-v1-forregistrering.md`.

## Det som byggts

- `backend/scripts/optimera_topptips256.py` öppnar en explicit SQLite-snapshot
  i `mode=ro` och skriver endast JSON-resultat/checkpoint.
- Kontrollkonfigurationen motsvarar dagens Standard exakt. Regressionstestet
  kräver samma 256 rader i samma ordning som `build_ev_system`.
- Historiken sorteras globalt efter spelstopp och delas 60/20/20 i utveckling,
  validering och historisk slutaudit.
- Successiv gallring gör att alla 10 000 kandidater inte behöver köras genom
  alla omgångar. Champion följer alltid med.
- Kandidaterna kan ändra värdevikt, global kappa, X-gruppvärdering, minsta
  X-spridning och maximalt teckenberoende. Utvärderingen använder alltid samma
  frysta referensmodell.
- Resume vägras om kod, spec, dataset eller kandidatlista har ändrats.
- Slutauditen sparar parade träff- och winsoriserade ROI-skillnader samt
  deterministiska ojusterade 90-procentsintervall. De är diagnostik, aldrig
  promotionsbevis efter en stor modellsökning.
- Om en begränsad miljö nekar process-semaforer faller CLI:n säkert tillbaka
  till sekventiell körning. Vanlig lokal körning med två processer är testad.

Lokala resultat ignoreras via `backend/data/optimizer/`; råresultat och
databassnapshots ska inte committas.

## Verifiering

Den slutliga koden klarade:

- 9 fokuserade optimerartester, inklusive exakt championidentitet, hårt
  exponeringstak, X-kvot, kostnad/facit, determinism och parad slutaudit;
- hela backendens 823 tester;
- Python-kompilering och `git diff --check`;
- en tvåkärnig pilot utan DB-skrivning.

Pilotens fasta fakta:

- källa: den lokala databaskopian från 11 augusti, endast för teknikprov;
- 1 950 kvalificerade Topptipsfamiljeomgångar hittades;
- 60 jämnt tidsutspridda omgångar användes: 36/12/12;
- 500 konfigurationer, två worker-processer, cirka 25 sekunders faktisk
  beräkning;
- gallring: 500 → 37 → 35 → 20 → 5;
- champion hade noll ogiltiga omgångar i samtliga steg;
- de fem finalisterna fick fyra toppträffar var på de tolv slutauditomgångarna
  och valde där samma rader, därför blev alla parade skillnader noll.

Det sista utfallet betyder inte att parametrarna alltid är likvärdiga. Det
visar att den lilla piloten saknade upplösning för att skilja dem och uppfyllde
sin avsedda roll som teknikprov. Pilotens JSON ligger bara i `/tmp` och är
inte forskningsunderlag.

## Så körs verktyget

Från `backend/`, med projektets venv:

```bash
PYTHONPATH=. .venv/bin/python -u -B scripts/optimera_topptips256.py \
  --pilot --configs 500 --pilot-draws 60 --workers 2 \
  --db /absolut/sökväg/till/fixerad-snapshot.db
```

Full körning, först efter att snapshotsteget nedan är klart:

```bash
PYTHONPATH=. .venv/bin/python -u -B scripts/optimera_topptips256.py \
  --full --configs 10000 --workers 2 \
  --db /absolut/sökväg/till/fixerad-snapshot.db
```

Standardresultatet hamnar under `backend/data/optimizer/`. Använd `--resume`
med samma argument och resultatfil efter ett avbrott. Verktyget skriver aldrig
i DB:n och får inte riktas mot en pågående serverdatabas via nätverksdelning.

## Nästa steg

1. Skapa en konsistent SQLite-snapshot på servern med SQLite backup-API eller
   en kontrollerad WAL-checkpoint/backup-rutin. Kopiera sedan snapshoten till
   beräkningsdatorn. Kopiera aldrig bara den levande `.db`-filen medan WAL
   används.
2. Notera snapshotens tid, filstorlek och SHA-256 i körloggen. Kör först
   pilotläget igen mot den färska snapshoten.
3. Om kontrolltalen fortfarande är rena, kör den förregistrerade fullsökningen
   med 10 000 konfigurationer. En rimlig lokal uppskattning från piloten är
   tiotals minuter, men mät i stället för att lova en fast tid.
4. Granska historisk slutaudit utan att trimma parametrar mot den. Nominera
   högst tre tydligt olika armar: träff, referensvärde/ROI och balans.
5. Förregistrera armarna i ett nytt point-in-time-forwardtest. Dagens Standard
   förblir champion tills forwardgrinden och projektets vanliga
   multipeltestskydd faktiskt är uppfyllda.

Efter Topptipset 256 görs en ny separat version för 512 rader och därefter för
Stryktipset/Europatipset. Att blanda budgetar och produkter i v1 skulle göra
resultatet svårare att tolka och öka sökfriheten i onödan.
