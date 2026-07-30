# Oddset-sidan: tabbar + sorterbara listor (2026-07-29, Samans beställning)

**ARBETSPLAN MED LÄGESMARKÖRER — uppdatera ☐→✅ per commit.** Om sessionen
dör: läs detta + `git log --oneline -15`, fortsätt på första ☐. Varje etapp
är separat committbar och lämnar UI:t funktionellt.

## Mål och beslut (fattade med Saman 29/7)

Oddset-sidan görs om från staplade sektioner till **sub-tabbar** med
**sorterbara listor** i stället för kortrutnät — enklare att jämföra och
sortera (alla rubriker klickbara: datum/tid, xG, stora chanser, edge osv).

Låsta designbeslut:
1. **Räknarrad alltid synlig** på tabbraden ("⚡ 8 live · 2 signaler ·
   💰 4 värdespel") — tabbar får inte dölja brådskande info.
2. **Mobilen behåller kortformat** (media query ≤760px, mönstret finns) —
   sorteringen ska fungera i båda lägena (sortvalet styr även kortordning).
3. **EN delad komponent** (`SortableTable` i App.jsx-biblioteket) för alla
   tabeller — rubrikklick asc/desc, pil, null sist, sortval persisterat i
   `svs_state` per tabell-id. Aldrig per-vy-kopior.
4. Signal-facit/loggen FLYTTAS till Labb (bevisytan) — Oddset renodlas
   till beslutsyta (v3-arkitekturens princip).

## Etapper

- ☐ **E1: SortableTable-komponenten** + CSS (App.jsx-biblioteket).
  Props: id, columns [{key, label, sort(a,b)|numeric, title}], rows,
  renderRow, defaultSort. Persistens via befintliga svs_state-mönstret.
- ☐ **E2: Tabbstruktur** i Oddset-vyn (AppV3): sub-pills 📋 Matcher ·
  ⚡ Live · 💰 Värdespel · 📈 Rörelser, räknarrad, persisterat tabbval,
  befintliga ankar-id:n (#oddset-live-radar m.fl.) behålls för fokusläge.
- ☐ **E3: Live-radarn som sorterbar tabell** (desktop): min, ställning,
  liga, match, xG h–b, chansgap/proxyindex, stora chanser, skott på mål,
  källa, signalnivå. Default: signal-score fallande. Mobil: kortvyn kvar.
- ☐ **E4: Värdespel som sorterbar tabell**: tid, liga, match, tecken,
  odds, edge, ¼-Kelly, tier/OMTVISTAD, ankare. Default: edge fallande.
- ☐ **E5: Sorterbara rubriker på Marknadsradarn + huvudtabellen**
  (datum/tid, liga, edge, rörelse — befintliga tabeller, bara rubriker).
- ☐ **E6: Flytta Signal-facit/Signal-loggen till Labb**; Oddset-sidan
  slutar rendera clvbox/ledger (Labb har redan clv-datat).
- ☐ **E7: Mobilverifiering** (resize_window 390px, sortering i kortläge),
  dokumentation: CLAUDE.md UI-konventioner + plan.md STATUS + denna fil.

## Verifiering per etapp

Browser mot :5175 (desktop + mobile preset), inga konsolfel, sortklick
ändrar ordning och överlever sidladdning (svs_state). Befintliga
funktioner (fokusläge, "Bara signaler", Rek-kolumnen) får inte regrediera.

## Läge

Påbörjad 2026-07-29. Inga etapper klara ännu vid skrivning — markörerna
ovan är sanningen.
