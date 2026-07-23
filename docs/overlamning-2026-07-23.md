# Överlämning/changelog för Codex — 2026-07-23

Ersätter `docs/overlamning-2026-07-16.md` som aktuell ingång (den gamla ligger
kvar som historik — dess "Fallgropar"-avsnitt gäller fortfarande ordagrant).
Sanningskällor i ordning: `docs/plan.md` (STATUS överst) → `docs/db-atgarder.md`
→ git-loggen (svenska, per arbetspaket).

## Changelog sedan 2026-07-16-överlämningen

**Codex egna 19 commits (16–17/7)** — hela P0/P1-backloggen: WP1 settlement-
ankring, WP2 full prisnärvaro/källhälsa, WP4 CLV per lina, WP5 prediction
ledger + grönt v3, WP6 jackpot/κ/portfolio-MC, WP7, WP8 frånvaro-/Elo-historik,
WP3-fuzzy-audit (hittade äkta felkoppling Egersund→Haugesund, gräns 0,75),
backtest v4, UI v3 + PWA, WP9c team-events, modell v2 förregistrerad och
**STOPPAD på egna kriterier** (ingen live-påverkan). Claude spot-verifierade
17/7: 107/107 tester, ankringsmatematiken korrekt, DB-integritet ok, v2
isolerad — inga metodfel funna. Granskningsnoter i konversation/plan.md.

**Alt-linjelagret (Claude, 20/7, `b917125`)** — Samans "steppa upp"-beställning:
samma-linje-regeln dödade 67 % av AH- och ~40 % av Ö/U-jämförelserna (AH samma
huvudlinje bara 33 %). Ny tabell `oddset_sharp_alt` sparar sharpens ALLA linjer
(samma två API-anrop, noll ny trafik); värdemotorn devigar alt-paret på BOKENS
exakta lina (fresh ≤45 min, `alt_line: true` i posten); `closing_snapshot`
läser alt-lagret när huvudlinan flyttat. Ny sharp-version `s-776ca0e0`
(`alt_lines` i SHARP_PARAMS). Första varvet: 1 238 alt-rader/38 matcher;
Ö/U-jämförelser 66 (28 via alt), AH 38 (12), hörnor 6 (2). 5 nya tester
(112/112). Detaljer: `docs/db-atgarder.md` 2026-07-20.

**Facit-läge 20/7:** sharp 1X2 close-EV **+3,8 %** på 50 stängda (Allsvenskan
+3,7 %/16 matcher, MLS +6,8 %/12) — riktning rätt, långt till candidate
(30 matcher/liga). Modell-tiern fortsatt negativ (amber gör sitt jobb).

**Drift/miljö:**
- **svs PAUSAD 20/7** (fryst arkiv, total paritet verifierad): launchd urlastat,
  plist-kopian borta ur ~/Library/LaunchAgents (original i svs/backend/scripts/),
  servrar 8000/5173 stoppade, DB kvar. Borttagen ur menybars-appen 23/7.
- **VM-koll på is** (Samans beslut, se ~/vm/LÄRDOMAR.md): borttagen ur menybars-
  appen 23/7; vm-launchd-insamlingarna redan urlastade. Menybars-appen
  (`~/vm/tools/menubar.py`) hanterar nu ENBART Spelkompisen (8002/5175) och är
  vägen att starta servrarna efter omstart ("Starta allt").
- Spelkompisen är därmed **enda driften** — och enda Pinnacle-konsumenten på IP:t.

## Att göra (utöver NTFY_TOPIC, som förblir Samans steg)

1. **UI-grupptabell för grönt-status** (runda 2 punkt 2, S): tier-✓ lever kvar
   (`App.jsx:1465/1469` läser `clv.sharp/model.green_ready`). Ersätt med
   grupptabell (API:ts `groups` finns redan) + tier-rad som ren översikt utan ✓.
2. **Candidate-ETA i facitpanelen** (S): visa "insamling pågår — tidigast
   candidate ~<datum>" per primär grupp så unga siffror inte överläses.
3. **Spot-checka alt-linje-flödet efter några dagar** (S): flaggor/ledger under
   `s-776ca0e0` — rimliga volymer per marknad, stängningar via alt-lagret
   fungerar i produktion (första riktiga exakt-line-closen på flyttad lina).
4. **Hörn-grön väg (gamla B8)**: nu UPPLÅST av alt-linjerna — vänta tills
   hörn-facitet samlat n, sedan egen facit-grupp (utforskande, BH-FDR).
5. **Märk v2-modulerna "vilande"** (S): stoppad-statusen står i plan.md men inte
   i modulhuvudena (`oddset_v2*.py`) — en rad per docstring: återupptas endast
   med nytt fryst outer-manifest.
6. **Mät värde-pill-flimmer** (hypotes): 45-min-vakten kan få AH/ÖU-pillar att
   blinka mellan fulla varv — mät växlingar/dygn innan ev. åtgärd.
7. **Låt facitet mogna**: inga tröskeländringar, ingen modellutveckling förrän
   ledgern dömt (tidigast ~2–3 veckor för första candidate).
8. **Öppna produktbeslut hos Saman**: 🎯 Bara signaler som mobil-default;
   spel-journal i appen; Europa-expansion (gate uppfylld, kräver produktbeslut);
   ASA-certfelet; servermigrering (E14). **pytest-beslutet kan stängas** —
   unittest-sviten (112 fall) täcker behovet utan ny dependency.

## Regler som aldrig viker (påminnelse)

Sharp-ankrat = enda gröna; modell = amber, aldrig i CLV. Grönt per signalgrupp,
aldrig per tier. Notiser kräver närvarobekräftat pris. DB-ändringar = skript +
backup + rapport. Versionspolicy: signal_version grupperar facit, git_hash
reproducerar. Inga automatiska spel, enbart gratiskällor, rör aldrig ~/svs
eller ~/vm (svs är dessutom fryst arkiv).
