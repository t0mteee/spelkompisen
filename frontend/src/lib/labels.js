// Etiketter, produkt-/familjetabeller och små formatterare som Idag, Historik
// och Labb delar. Ren logik utan React. Bruten ur AppV3.jsx 2026-09-02.
import { FAMILY } from './families.js'
import { fmtClose } from './format.js'

export const POOL_GAMES = [
  { id: 'topptipset', label: 'Topptipset' },
  { id: 'stryktipset', label: 'Stryktipset' },
  { id: 'europatipset', label: 'Europatipset' },
  { id: 'bomben', label: 'Bomben' },
]
export const HIST_PRODUCTS = [
  { id: 'stryktipset', label: 'Stryktipset' },
  { id: 'europatipset', label: 'Europatipset' },
  { id: 'topptipset', label: 'Topptipset' },
  { id: 'topptipsetstryk', label: 'Topptipset Stryk' },
  { id: 'topptipsetextra', label: 'Topptipset Extra' },
]
export const PRODUCT_LABEL = Object.fromEntries(
  [...POOL_GAMES, ...HIST_PRODUCTS].map((p) => [p.id, p.label]))
/* Topptipset Dagens/Stryk/Extra är SAMMA spel hos Svenska Spel: åtta matcher,
   samma vinstplan (70 %), bara olika omgångar under olika namn (pid 25/23/24).
   På facit-korten räknas de därför som EN produkt.
   Detta är enbart en VISNINGSgruppering. Produktslug, settlementidentitet,
   PH3:s config_key och `benchmarks_for(product)` är oförändrade — en nyckel
   får aldrig byta betydelse i efterhand, och de tre har egna omgångsserier. */
export const FAMILY_LABEL = { ...PRODUCT_LABEL, topptipset: 'Topptipset' }
export const RESEARCH_FAMILY_LABEL = {
  ph5: '🧪 5 000-test',
  mathmax: '🧮 Matematiskt max',
  reducedmax: '✂️ Reducerat max',
  max40: '🗃 40 000-pilot',
}
// Väljarens poster: en per familj, i HIST_PRODUCTS ordning. Backend expanderar
// familjenyckeln via svenskaspel.GAME_GROUPS när `family=1` skickas med.
export const HIST_FAMILIES = HIST_PRODUCTS
  .filter((p, i, all) => all.findIndex((q) => FAMILY(q.id) === FAMILY(p.id)) === i)
  .map((p) => ({ id: FAMILY(p.id), label: FAMILY_LABEL[FAMILY(p.id)] || p.label }))
export const IS_FAMILY = (id) => HIST_PRODUCTS.filter((p) => FAMILY(p.id) === id).length > 1
// Under så här många utvärderingsbara observationer visas ingen ROI någonstans
// i appen — ett par rättade omgångar ger tresiffriga procenttal som är brus.
export const ROI_MIN_N = 10
export function hoursTo(iso) {
  if (!iso) return null
  const h = (new Date(iso).getTime() - Date.now()) / 3600000
  return Number.isFinite(h) ? h : null
}
export function closesIn(iso) {
  const h = hoursTo(iso)
  if (h == null) return ''
  if (h < 0) return 'stängd'
  if (h < 1) return `stänger om ${Math.max(1, Math.round(h * 60))} min`
  if (h < 48) return `stänger om ${Math.round(h)} h`
  return `stänger ${fmtClose(iso)}`
}
export function fmtDay(iso) {
  if (!iso) return '–'
  try {
    return new Date(iso).toLocaleDateString('sv-SE', { day: 'numeric', month: 'short', year: 'numeric' })
  } catch { return '–' }
}
// Avspark på Idag-korten: "idag 20:00" säger mer än ett datum, och nästan allt
// som ligger i värde-/rörelselistan spelas inom ett dygn.
export function fmtKickoff(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  const tid = d.toLocaleTimeString('sv-SE', { hour: '2-digit', minute: '2-digit' })
  const dygn = Math.round(
    (new Date(d).setHours(0, 0, 0, 0) - new Date().setHours(0, 0, 0, 0)) / 86400000)
  if (dygn === 0) return `idag ${tid}`
  if (dygn === 1) return `imorgon ${tid}`
  return `${d.toLocaleDateString('sv-SE', { weekday: 'short', day: 'numeric', month: 'numeric' })} ${tid}`
}

/* Rörelsen i ODDS i stället för bara procentenheter: "1.92 → 1.68".
   `steam` och `value.fair` mäter SAMMA storhet — Pinnacles devigade
   1X2-sannolikhet (attach_steam respektive attach_value) — så skiftet kan
   uttryckas i odds utan någon ny insamling: sannolikheten då är den nu minus
   pp, och odds är inversen. Det är alltså den DEVIGADE kvoten, inte Pinnacles
   noterade pris (som ligger under sin marginal). Saknas fair för tecknet visas
   inget par alls hellre än ett påhittat. */
export const oddsSkift = (m, sg, pp) => {
  const nu = m.value?.['1x2']?.[sg]?.fair
  if (nu == null || pp == null) return null
  const da = nu - pp / 100
  if (!(nu > 0 && nu < 1) || !(da > 0 && da < 1)) return null
  return `${(1 / da).toFixed(2)} → ${(1 / nu).toFixed(2)}`
}
export const selLabel3 = (m, mk, sg, line) => {
  if (mk === '1x2') return sg === '1' ? `1 · ${m.home}` : sg === '2' ? `2 · ${m.away}` : 'X · Kryss'
  if (mk === 'ah') return `${sg === 'H' ? m.home : m.away} ${line > 0 && sg === 'H' ? '+' : ''}${sg === 'H' ? line : -line} AH`
  if (mk === 'ou') return `${sg === 'O' ? 'Över' : 'Under'} ${line} mål`
  return `${sg === 'O' ? 'Över' : 'Under'} ${line} hörnor`
}
export const STRATEGY_LABEL = {
  säker: 'Säker', medel: 'Medel', tuff: 'Tuff',
  byggarslump: 'Slump · samma urval', favoritrad: 'Favoritrader',
  folkrad: 'Folkrader',
  // `maxev` är samma byggare som medel med balansknappen i botten
  // (värdevikt 1,0 ⇒ k = 0, ren EV utan träffchansdämpning). Etiketten
  // säger vad knappen GÖR, eftersom "maxev" annars läses som en egen metod.
  maxev: 'Ren EV · utan dämpning',
}
// Horisonten är minuter före spelstopp. Nyckeln (`h3`/`m20`) är ett internt
// id som aldrig ska nå användaren — brödtexten sa T−3 h medan tabellen sa h3.
export const horizonLabel = (row) => (row?.horizon_minutes != null
  ? `${row.horizon_minutes} min` : row?.horizon || '–')
export const pctSigned = (v) => (v == null ? '–'
  : `${v >= 0 ? '+' : ''}${Math.round(v * 100)} %`)
export const roiCls = (v) => (v == null ? '' : v >= 0 ? 'v3pos' : 'v3neg')
export const marketTimeLabel = (iso) => {
  const parsed = new Date(iso)
  return Number.isNaN(parsed.getTime()) ? 'nyss' : parsed.toLocaleTimeString('sv-SE', {
    hour: '2-digit', minute: '2-digit', second: '2-digit',
  })
}
export const PH5_METHOD_LABEL = {
  varderader: 'Värderader',
  byggarslump: 'Byggarslump',
  favoritrad: 'Favoritrad',
  maxev: 'Max-EV',
  folkrad: 'Folkrad (avslutad)',
}
export const FORWARD_TEST = {
  ph5: {
    endpoint: '/api/pool/ph5', rowLabel: '5 000', title: '5 000-kronorstestet',
    loading: 'Hämtar 5 000-kronorstestet…', filterLabel: 'Metod',
  },
  max40: {
    endpoint: '/api/pool/max40', rowLabel: '40 000',
    title: '40 000-piloten · avslutad',
    loading: 'Hämtar den historiska 40 000-piloten…', filterLabel: 'Arm',
    paired: false, archived: true,
  },
  mathmax: {
    endpoint: '/api/pool/mathmax', rowLabel: '39 366',
    title: 'Matematiskt max · 39 366 rader',
    loading: 'Hämtar matematiskt maxtest…', filterLabel: 'Arm',
    paired: true,
  },
  reducedmax: {
    endpoint: '/api/pool/reducedmax', rowLabel: '20 000',
    title: 'Reducerat max · 20 000 rader',
    loading: 'Hämtar reducerat maxtest…', filterLabel: 'Arm',
    paired: true,
  },
}
export const forwardTestLabel = (test) => test.label || PH5_METHOD_LABEL[test.method] || test.method
export const forwardTestFilterKey = (test) => test.label || test.method
export const LABB_STATUS = {
  samlar: ['SAMLAR', 'Serien växer och utvärderas bara på sin förregistrerade kadens — inga beslut i förtid.'],
  candidate: ['CANDIDATE', 'Mängdkravet är nått — beslut tas enligt den förregistrerade regeln, inte löpande.'],
  pass: ['GATE-PASS', 'Den förregistrerade grinden är passerad — se dokumentet för hela beslutet.'],
  fals: ['FALSIFIERAD', 'Hypotesen föll mot facit — spåret byggs inte vidare som tips.'],
}
// Primärgrupperna för sharp-CLV (speglar backend PRIMARY_LEAGUES × 1X2 × sharp)
export const LABB_PRIMARY = ['allsvenskan', 'superettan', 'eliteserien', 'obosligaen', 'mls']
export const LABB_LEAGUE = {
  allsvenskan: 'Allsvenskan', superettan: 'Superettan', eliteserien: 'Eliteserien',
  obosligaen: 'OBOS-ligaen', mls: 'MLS',
  // sekundära/utforskande grupper — bara läsbara etiketter, ingen statuseffekt
  bestadeild: 'Besta deild', friendlies: 'Träningsmatcher',
  champions_league: 'Champions League', europa_league: 'Europa League',
  conference_league: 'Conference League',
  premier_league: 'Premier League', serie_a: 'Serie A',
  la_liga: 'La Liga', bundesliga: 'Bundesliga',
  danish_superliga: 'Danska Superliga',
  belgian_pro_league: 'Belgiska Pro League',
  primeira_liga: 'Primeira Liga',
  bolivian_primera: 'Bolivianska Primera División',
}
export const LABB_MARKET = {
  '1x2': '1X2', ah: 'AH', ou: 'Ö/U', cor: 'Hörnor',
}
export const LABB_BOOK = {
  svenskaspel: 'SvS', expekt: 'Expekt', ninjacasino: 'Ninja/Altenar',
  pinnacle: 'Pinnacle', smarkets: 'Smarkets',
}
// Avslutade/pågående forskningsspår utan eget API — daterade kort med källdok.
// Ytgränsen (2026-08-05) gäller även dessa: odds-spåren bor här, pool-spåren
// (pit-v4, PH5, startOdds) renderas i Historik via HISTORIK_RESEARCH nedan.
export const LABB_RESEARCH = [
  { icon: '🧮', title: 'Devig-ablation', date: '2026-07-26', status: 'pass',
    text: 'Konsensusflaggor +4,40 % [+2,54..+6,14] mot bara-power −0,49 % — devig-tvetydighet är en äkta filtersignal.',
    doc: 'docs/devig-ablation-2026-07-26.md' },
  { icon: '🔮', title: 'Close-drift v1', date: '2026-07-26', status: 'fals',
    text: 'Momentum FALSIFIERAD; tidiga AH/Ö/U-skift reverserar.',
    doc: 'docs/close-drift-facit-2026-07-26.md' },
  { icon: '🔬', title: 'V2.2 flerliga-shadow', status: 'samlar',
    text: 'Ren shadow, manifest v4 från 2026-08-01 21:20Z — inga tips, notiser eller CLV.',
    doc: 'docs/model-v2.2-multileague-forward-manifest-v4.json' },
]
// Poolens forskningsspår — visas i Historik (Historik = pool, Labb = odds).
export const HISTORIK_RESEARCH = [
  { icon: '📐', title: 'pit-v4 (pool-streckmove-v3)', status: 'samlar',
    text: 'Forward samlar, gate ≥40 out-of-time-omgångar per produkt.',
    doc: 'docs/pool-ph4-forward-manifest-v3.json' },
  { icon: '🎟️', title: 'PH5 256/512 rader', date: '2026-07-26', status: 'fals',
    text: 'Värderader ger ingen påvisad fördel på 13-matchsspel ens vid 512 rader.',
    doc: 'docs/ph5-radvalsablation-512rader-2026-07-26.json' },
  { icon: '🔓', title: 'startOdds', date: '2026-07-26', status: 'pass',
    text: 'Upplåst som omgångs-kovariat (final_only) — aldrig som PIT-observation.',
    doc: 'docs/startodds-semantik-2026-07-26.md' },
]
