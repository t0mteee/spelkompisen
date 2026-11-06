import test from 'node:test'
import assert from 'node:assert/strict'
import { poolTotalParts, poolTotalTitle } from './poolTotals.js'

test('Ö/U-raden visar X-skyddets källa och Smarkets bredvid', () => {
  const m = { total_line: 2.25, total_source: 'svenskaspel_kambi',
    reference_ou: { line: 2.5, O: 1.619, U: 2.6082, short: 'Sm', fair: { O: 0.6 }, last_seen_at: '2026-11-06T08:00:00Z' } }
  assert.deepEqual(poolTotalParts(m), ['Ö/U 2,25 SvS', 'Sm 2,5: Ö 1.62 / U 2.61'])
  assert.match(poolTotalTitle(m), /Kambis Ö\/U-lina 2,25 \(Pinnacle saknas\)/)
  assert.match(poolTotalTitle(m), /Smarkets Ö\/U 2,5 \(60 % över\).*Bara visning\./)
})

test('Pinnacle märks P och tom match ger ingen rad', () => {
  assert.deepEqual(poolTotalParts({ total_line: 3, total_source: 'pinnacle' }), ['Ö/U 3 P'])
  assert.deepEqual(poolTotalParts({}), [])
  assert.equal(poolTotalTitle({}), '')
})
