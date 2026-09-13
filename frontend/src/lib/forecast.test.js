import test from 'node:test'
import assert from 'node:assert/strict'
import { topAliveForecast, forecastBasisText } from './forecast.js'

test('högsta levande nivå med prognos', () => {
  const live = { alive_per_level: { 13: 0, 12: 3, 11: 20 },
    forecast: { levels: { 13: { per_row_kr: 900000 }, 12: { per_row_kr: 8500, pot_kr: 1000000 }, 11: { per_row_kr: 300 } } } }
  assert.deepEqual(topAliveForecast(live), { level: 12, per_row_kr: 8500, pot_kr: 1000000 })
  assert.equal(topAliveForecast({ alive_per_level: { 13: 0, 12: 0 }, forecast: { levels: {} } }), null)
  assert.equal(topAliveForecast({ alive_per_level: { 12: 3 } }), null)
  assert.equal(topAliveForecast(null), null)
})

test('underlagstext', () => {
  assert.equal(forecastBasisText({ basis: { decided: 4, current: 6, open: 3 } }),
    '4 avgjorda · 6 pågående som de står · 3 ospelade viktade på odds')
  assert.equal(forecastBasisText(null), '')
})
