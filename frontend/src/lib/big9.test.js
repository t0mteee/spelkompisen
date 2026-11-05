import test from 'node:test'
import assert from 'node:assert/strict'
import {
  BIG9_CELLS, cellLabel, cellShort, valueClass, pctText, rowTokens, rowsText, fileName,
  coverageCells, roundOptions, roundKey, fmtSwedish, systemCells, systemFormula, couponText,
  ratioClass, emptyCoupon, toggleCell, couponFromSystem, restoreCoupon, couponStats, smallPct, oneIn,
} from './big9.js'
import { POOL_GAMES, POOL_TABS } from './labels.js'

test('sex celler och deras namn', () => {
  assert.deepEqual(BIG9_CELLS, ['1O', '1U', 'XO', 'XU', '2O', '2U'])
  assert.equal(cellLabel('1O'), '1 Över')
  assert.equal(cellLabel('XU'), 'X Under')
  assert.equal(cellLabel('W'), 'Wild Card')
  assert.equal(cellShort('2O'), '2 Ö')
  assert.equal(cellShort('1U'), '1 U')
})

test('värdefärg följer poolens gränser', () => {
  assert.equal(valueClass(1.08), 'pos')
  assert.equal(valueClass(0.91), 'neg')
  assert.equal(valueClass(1.0), '')
  assert.equal(valueClass(null), '')
  assert.equal(pctText(0.1234), '12,3 %')
  assert.equal(pctText(null), '–')
})

test('raderna som text och fil', () => {
  assert.deepEqual(rowTokens(' 1O  XU 2O '), ['1O', 'XU', '2O'])
  assert.equal(rowsText(['1O XU', '2O 1U']), '1O XU\n2O 1U\n')
  assert.equal(rowsText([]), '')
  assert.equal(fileName('sp96', 546), 'big9-sp96-omg546.txt')
})

test('kupongbildens täckning', () => {
  const out = coverageCells([{ '1O': 3, XU: 0 }])
  assert.equal(out[0].length, 6)
  assert.deepEqual(out[0][0], { cell: '1O', count: 3, marked: true })
  assert.equal(out[0][3].marked, false)
})

test('omgångsväljaren och flikarna', () => {
  const open = [{ product: 'sp96', serial: 546 }]
  assert.deepEqual(roundOptions({ open, recent: [{ product: 'sp96', serial: 536 }] }), open)
  assert.equal(roundOptions({ open: [], recent: [{ product: 'sp96', serial: 536 }] })[0].serial, 536)
  assert.equal(roundKey(open[0]), 'sp96|546')
  assert.ok(POOL_TABS.some((t) => t.id === 'big9'))
  // Idag och produktetiketterna läser POOL_GAMES mot Svenska Spel — Big 9 hör inte dit
  assert.ok(!POOL_GAMES.some((g) => g.id === 'big9'))
})

test('ATG:s UTC-tider visas i svensk tid', () => {
  assert.match(fmtSwedish('2026-11-04T19:45:00Z'), /20:45/)
  assert.equal(fmtSwedish(null), '–')
  assert.equal(fmtSwedish('nej'), '–')
})

test('fullt system: cellmängd per match och antalet rader', () => {
  const system = {
    cells: [['1O', 'XU', '2O'], ['1O']],
    matches: [{ event_number: 1, home: 'A', away: 'B' }, { event_number: 2, home: 'C', away: 'D' }],
  }
  assert.deepEqual(systemFormula(system.cells), { sizes: [3, 1], rows: 3, text: '3 × 1 = 3 rader' })
  assert.equal(couponText(system), '1. A – B: 1 Ö, X U, 2 Ö\n2. C – D: 1 Ö\n3 × 1 = 3 rader\n')
  // äldre svar utan `cells`: mängden ur täckningen
  assert.deepEqual(systemCells({ coverage: [{ '1O': 2, XU: 0, '2U': 1 }] }), [['1O', '2U']])
  assert.equal(couponText({ matches: [], cells: [] }), '')
})

const cellsOf = (p, q) => BIG9_CELLS.map((cell, i) => ({
  cell, p: p ? p[i] : null, q: q ? q[i] : null, value: p && q ? p[i] / q[i] : null,
}))

test('egen kupong: rutor läggs till och tas bort i cellordning', () => {
  let c = emptyCoupon(2)
  assert.deepEqual(c, [[], []])
  c = toggleCell(c, 0, '2U')
  c = toggleCell(c, 0, '1O')
  assert.deepEqual(c, [['1O', '2U'], []])
  c = toggleCell(c, 0, '1O')
  assert.deepEqual(c, [['2U'], []])
  assert.deepEqual(restoreCoupon([['XU', 'nej', '1O']], 1), [['1O', 'XU']])
  assert.deepEqual(restoreCoupon([['1O']], 2), [[], []])
  assert.deepEqual(restoreCoupon(null, 1), [[]])
})

test('kvoten modell/streck: grön över 1, röd under 1', () => {
  assert.equal(ratioClass(1.01), 'pos')
  assert.equal(ratioClass(0.99), 'neg')
  assert.equal(ratioClass(1), '')
  assert.equal(ratioClass(null), '')
})

test('byggarens system som start paras på matchnumret', () => {
  const system = { cells: [['XU'], ['1O', '2U']], matches: [{ event_number: 2 }, { event_number: 1 }] }
  assert.deepEqual(couponFromSystem(system, [{ event_number: 1 }, { event_number: 2 }, { event_number: 3 }]),
    [['1O', '2U'], ['XU'], []])
})

test('kupongens form, rader, kostnad, chans och folkets andel', () => {
  const p = [0.3, 0.2, 0.1, 0.1, 0.2, 0.1]
  const q = [0.4, 0.1, 0.1, 0.1, 0.2, 0.1]
  const matches = [
    { event_number: 1, cells: cellsOf(p, q) },
    { event_number: 2, cells: cellsOf(p, q) },
    { event_number: 3, cancelled: true, cells: cellsOf(null, null) },
  ]
  const s = couponStats(matches, [['1O', '1U'], ['XO'], ['2U']], 0.5)
  assert.equal(s.form, '2·1·1')
  assert.equal(s.rows, 2)
  assert.equal(s.cost, 1)
  assert.ok(Math.abs(s.chance - 0.5 * 0.1) < 1e-12)   // struken match räknas som rätt
  assert.ok(Math.abs(s.folk - 0.5 * 0.1) < 1e-12)
  assert.ok(Math.abs(s.ratio - 1) < 1e-9)
  // en match utan ruta: inga rader, inga tal
  const tom = couponStats(matches, [['1O'], [], ['2U']], 0.5)
  assert.deepEqual([tom.rows, tom.cost, tom.chance, tom.folk, tom.missing], [0, 0, null, null, [2]])
  // saknad modell i en vald match: chansen gissas inte
  const utan = couponStats([{ event_number: 1, cells: cellsOf(null, q) }], [['1O']], 0.5)
  assert.equal(utan.chance, null)
  assert.deepEqual(utan.unpriced, [1])
  assert.ok(Math.abs(utan.folk - 0.4) < 1e-12)
})

test('små sannolikheter och 1 på N', () => {
  assert.equal(smallPct(0.123), '12,3 %')
  assert.equal(smallPct(0.00042), '0,042 %')
  assert.equal(smallPct(null), '–')
  assert.equal(oneIn(0.004), '1 på 250')
  assert.equal(oneIn(0.6), '')
})
