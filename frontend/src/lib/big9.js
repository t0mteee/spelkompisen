// Big 9 (ATG) i Poolspel — ren logik utan React (beslut 2026-11-04-big9-i-byggaren).
// En rad är nio tokens i matchordning; en token är 1X2 + Ö/U 2,5 (`1O` = hemma
// och över). ATG tar bara fulla system ("Spela enskilda utfall", beslut
// 2026-11-04-big9-fullt-system): byggaren lämnar en cellmängd per match, och
// kupongen visar vilka av de sex rutorna som ska markeras hos ATG.

export const BIG9_CELLS = ['1O', '1U', 'XO', 'XU', '2O', '2U']
export const BIG9_VALUE_GREEN = 1.08
export const BIG9_VALUE_RED = 0.92

const SIGN = { 1: '1', X: 'X', 2: '2', W: 'Wild Card' }
const GOALS = { O: 'Över', U: 'Under' }

export function cellLabel(cell) {
  if (cell === 'W') return 'Wild Card'
  if (cell === '*') return 'struken'
  const sign = SIGN[cell?.[0]]
  const goals = GOALS[cell?.[1]]
  return sign && goals ? `${sign} ${goals}` : String(cell ?? '–')
}

// Kort visning i tabellhuvud och kupongbild: "1 Ö", "X U".
export function cellShort(cell) {
  if (cell === 'W') return 'W'
  if (cell === '*') return '*'
  const goals = cell?.[1] === 'O' ? 'Ö' : cell?.[1] === 'U' ? 'U' : ''
  return goals ? `${cell[0]} ${goals}` : String(cell ?? '–')
}

export function valueClass(value) {
  if (value == null) return ''
  if (value >= BIG9_VALUE_GREEN) return 'pos'
  if (value < BIG9_VALUE_RED) return 'neg'
  return ''
}

export function pctText(share, digits = 1) {
  return share == null ? '–' : `${(share * 100).toFixed(digits).replace('.', ',')} %`
}

export const rowTokens = (row) => String(row || '').trim().split(/\s+/).filter(Boolean)

// Raderna som text: en rad per kupongrad, tokens med mellanslag.
export function rowsText(rows) {
  return (rows || []).map((row) => rowTokens(row).join(' ')).join('\n') + ((rows || []).length ? '\n' : '')
}

export function fileName(product, serial) {
  return `big9-${product}-omg${serial}.txt`
}

// Täckningen per match som kupongbild: celler som finns på någon rad, med antal.
export function coverageCells(coverage, cells = BIG9_CELLS) {
  return (coverage || []).map((counts) => cells.map((cell) => ({
    cell, count: counts?.[cell] || 0, marked: (counts?.[cell] || 0) > 0,
  })))
}

// Omgångar i väljaren: öppna först (närmast spelstopp), annars de senaste stängda.
export function roundOptions(data) {
  const open = data?.open || []
  return open.length ? open : (data?.recent || [])
}

export const roundKey = (r) => (r ? `${r.product}|${r.serial}` : '')

// ATG:s tider är UTC (`Z`); visa dem i svensk tid.
export function fmtSwedish(iso) {
  if (!iso) return '–'
  const t = new Date(iso)
  if (Number.isNaN(t.getTime())) return '–'
  return t.toLocaleString('sv-SE', {
    timeZone: 'Europe/Stockholm', weekday: 'short', day: 'numeric', month: 'numeric',
    hour: '2-digit', minute: '2-digit',
  })
}

// Fullt system: cellmängd per match (`system.cells`), annars ur täckningen.
export function systemCells(system, cells = BIG9_CELLS) {
  if (Array.isArray(system?.cells)) return system.cells
  return (system?.coverage || []).map((counts) => cells.filter((c) => (counts?.[c] || 0) > 0))
}

// "3 × 1 × 3 … = 486 rader": antalet rader är produkten av mängdernas storlek.
export function systemFormula(cells) {
  const sizes = (cells || []).map((c) => c.length)
  const rows = sizes.reduce((acc, n) => acc * n, sizes.length ? 1 : 0)
  return { sizes, rows, text: `${sizes.join(' × ')} = ${rows} rader` }
}

// Kupongen som text: en rad per match med cellerna att markera hos ATG.
export function couponText(system, cells = systemCells(system)) {
  const lines = (system?.matches || []).map((m, i) => {
    const marked = (cells[i] || []).map(cellShort).join(', ')
    return `${m.event_number}. ${m.home} – ${m.away}: ${marked}`
  })
  const { text } = systemFormula(cells)
  return lines.join('\n') + (lines.length ? `\n${text}\n` : '')
}

// ── Egen kupong (beslut 2026-11-04-big9-lagg-till-i-kupong-omforsok) ─────────
// Saman väljer själv rutor per match; varje vald ruta visar folkets streck,
// modellens sannolikhet (ATG:s odds utan marginal) och kvoten modell/streck.
// Kupongen är ett fullt system som byggarens: rader = produkten av rutorna.

// Kvoten modell/streck: grön över 1, röd under 1 (beslutets gränser, inte
// värdefärgens 1,08/0,92).
export function ratioClass(ratio) {
  if (ratio == null) return ''
  if (ratio > 1) return 'pos'
  if (ratio < 1) return 'neg'
  return ''
}

export const emptyCoupon = (n) => Array.from({ length: n }, () => [])

// Lägg till eller ta bort en ruta; mängden hålls i cellordningen 1O … 2U.
export function toggleCell(coupon, index, cell) {
  return coupon.map((set, i) => {
    if (i !== index) return set
    const next = set.includes(cell) ? set.filter((c) => c !== cell) : [...set, cell]
    return BIG9_CELLS.filter((c) => next.includes(c))
  })
}

// Byggarens system som start: mängden per match, parad på matchnumret.
export function couponFromSystem(system, matches) {
  const cells = systemCells(system)
  const byEvent = new Map((system?.matches || []).map((m, i) => [m.event_number, cells[i] || []]))
  return (matches || []).map((m) => BIG9_CELLS.filter((c) => (byEvent.get(m.event_number) || []).includes(c)))
}

// En sparad kupong godtas bara om den passar omgångens matcher och celler.
export function restoreCoupon(saved, n) {
  if (!Array.isArray(saved) || saved.length !== n) return emptyCoupon(n)
  return saved.map((set) => (Array.isArray(set) ? BIG9_CELLS.filter((c) => set.includes(c)) : []))
}

// Kupongens nyckeltal. Chansen för 9 rätt är produkten av modellens
// sannolikhet för de valda rutorna, folkets andel produkten av strecken
// (matcherna som oberoende) — samma rader. Struken match är rätt för alla.
// Saknas modell eller streck i en vald match blir talet null, aldrig en gissning.
export function couponStats(matches, coupon, rowPrice) {
  const list = matches || []
  const sizes = list.map((_, i) => (coupon?.[i] || []).length)
  const missing = list.filter((_, i) => !sizes[i]).map((m) => m.event_number)
  const rows = list.length && !missing.length ? sizes.reduce((a, n) => a * n, 1) : 0
  let chance = rows ? 1 : null
  let folk = rows ? 1 : null
  const unpriced = []
  const unstreck = []
  list.forEach((m, i) => {
    if (!rows || m.cancelled) return
    const chosen = (m.cells || []).filter((c) => coupon[i].includes(c.cell))
    if (chosen.some((c) => c.p == null)) unpriced.push(m.event_number)
    else if (chance != null) chance *= chosen.reduce((a, c) => a + c.p, 0)
    if (chosen.some((c) => c.q == null)) unstreck.push(m.event_number)
    else if (folk != null) folk *= chosen.reduce((a, c) => a + c.q, 0)
  })
  if (unpriced.length) chance = null
  if (unstreck.length) folk = null
  return {
    sizes, form: sizes.join('·'), rows, missing, unpriced, unstreck,
    cost: rows * (rowPrice || 0), chance, folk,
    ratio: chance != null && folk ? chance / folk : null,
  }
}

// Små sannolikheter med två värdesiffror: "0,042 %", "12,3 %".
export function smallPct(share) {
  if (share == null) return '–'
  const pct = share * 100
  const text = pct >= 1 ? pct.toFixed(1) : pct.toPrecision(2)
  return `${text.replace('.', ',')} %`
}

// "1 på 240" för chanser under 50 %.
export function oneIn(share) {
  if (!share || share >= 0.5) return ''
  return `1 på ${Math.round(1 / share).toLocaleString('sv-SE')}`
}
