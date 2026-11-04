import test from 'node:test'
import assert from 'node:assert/strict'
import {
  BIG9_CELLS, cellLabel, cellShort, valueClass, pctText, rowTokens, rowsText, fileName,
  coverageCells, roundOptions, roundKey, fmtSwedish, systemCells, systemFormula, couponText,
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
