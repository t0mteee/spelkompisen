# Överlämning 2026-10-13: sex besvarade agentbeslut

Underlag: `~/spel-ai-data/utkorg/inlasta/<id>.json`. Svar: `spelai_inbox_answer`.
Alla sex är val 0 från Samans iPhone (Safari, ej misstänkta), besvarade
2026-10-08 till 2026-10-13.
granskaren-2026-10-08-v8-utanfor-1x2 (val 1, vänta) lämnas orörd.

| Beslut | Vad som gjordes | Commit |
|---|---|---|
| koordinatorn-2026-10-13-pool-namnmatchning | pool-name-v8 (nivå D, dammarkören som skiljeregel för landslag) + vaktlarmet `pool_pinnacle_saknas` | 07368fe, f6c0261 |
| drift-2026-10-12-pool-agf-alias | aliaset `arhus`/`agf aarhus` → `agf` i v8 (inte täckt av nivå D: Århus/AGF har ingen textlikhet) | 07368fe |
| koordinatorn-2026-10-08-larm-rollfel | `roll_fel_i_rad` i vakten (fel/timeout två gånger i rad, orsaken i texten) | f6c0261 |
| drift-2026-10-12-live-orattade | `livekassa.RESULTAT_ALIAS` + `livespel_orattat` i vakten | 0b4d478 |
| granskaren-2026-10-11-kambi-suspended | suspended i `kambi.league_events` + `oddset_odds.cache_age_s` | d957e1a |
| koordinatorn-2026-10-13-driftsattning-via-beslut | `app/spelai/driftsattning.py`, `bygg.sb`, beslutskortet, `docs/spelai-facit.md` § 17 | 588652b |

## Fynd värda att veta

- **USA–Spanien (Topptipset 4383) var inget namnfel.** Pinnacles enda rad var
  "International - Friendlies Women", och Svenska Spel skrev inte "Dam". v7:s
  veto för landslag byggde på att Svenska Spel alltid skriver Dam, och det stämmer
  alltså inte. I v8 är dammarkören därför en skiljeregel: herrraden vinner alltid.
- **Tester som kodade den gamla försiktigheten ändrades medvetet:** Inter–Lazio
  mot Inter Miami–Lazio, Deportivo Cali–Aguilas, Corinthians–Estudiantes, Santa
  Fe/Rosario mot exakt motståndare och Kina–Japan utan Dam. De säger nu vad v8
  gör. Barcelona ≠ Barcelona SC, trupper, kända falska par och landsnamn är
  oförändrade. Där ett kontextalias finns (Banfield–Rosario) styr det fortfarande
  ensamt.
- **Uppspelning:** v8 mot alla avvisade kandidater i `pool_match_diagnostic` gav
  ett trettiotal nya D-länkar, alla till rätt klubb (Feyenoord Rotterdam,
  Henan Songshan Longmen, America → America Mineiro mot brasiliansk motståndare,
  Fortaleza → Fortaleza CEIF mot colombiansk osv.).
- **Matcharen gick i drift före commit**, eftersom poolticken kör arbetskatalogen.
  Den var testad då. Resten byggdes i worktreen `../spelkompisen-wt`.
- **Livespel 9** rättades av sig själv 2026-10-13T09:03Z (vinst 16 kr) när
  football-data-raden kom. Spel 13 (Alavés–Atlético 1–2, under 2,5) och 26
  (Crystal Palace–Nottingham 3–1, under 3,5) blir förluster på 50 kr vid första
  spelai-ticken efter driftsättningen.
- **Push vid driftsättning går via spegeln, inte `git push` i agentrepot.**
  CLAUDE.md förbjuder git med agentrepot som arbetskatalog. Spegeln pushar
  samma `main` till samma GitHub-repo, så beslutets "push ingår" uppfylls.
- **Bygget kör agentens kod**, men bara i `bygg.sb`. Gränsprovet 2026-10-13
  nekade skrivning i agentrepot och Spelkompisen, läsning av databasen och
  `.env`, nät och git. Bara byggkatalogen var skrivbar.
- **API:t kan inte återställas automatiskt.** Facitsidan rör aldrig agentrepot
  med git. Därför kräver `omstart_api` att arbetskopians `backend/` är identisk
  med commiten, och en röd API-hälsa efter återställning rapporteras som `rod`.
