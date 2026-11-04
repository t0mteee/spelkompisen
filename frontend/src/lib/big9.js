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
