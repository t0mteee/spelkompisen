import test from 'node:test'
import assert from 'node:assert/strict'
import { topAliveForecast, forecastBasisText, minPayoutNote, perRowText, guaranteeLines } from './forecast.js'
import { kr } from './format.js'

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

test('under minimiutdelningen visas 0 kr med förklaring', () => {
  const forecast = { min_payout_kr: 15, min_payout_basis: 'belagd',
    levels: { 11: { per_row_kr: 0, below_min_payout: true, raw_per_row_kr: 12.4 },
      12: { per_row_kr: 180 } } }
  assert.equal(perRowText(forecast.levels[11]), kr(0))
  assert.equal(perRowText(forecast.levels[12]), `≈ ${kr(180)}`)
  assert.equal(perRowText(undefined), '–')
  const note = minPayoutNote(forecast, forecast.levels[11])
  assert.match(note, /under Svenska Spels minimiutdelning/)
  assert.ok(note.includes(kr(15)))
  assert.ok(!note.includes('antagen'))
  assert.equal(minPayoutNote(forecast, forecast.levels[12]), '')
  const topp = { ...forecast, min_payout_basis: 'antagen' }
  assert.match(minPayoutNote(topp, forecast.levels[11]), /antagen för Topptipset/)
})

test('garanti är en egen rad, aldrig i prognosen', () => {
  const forecast = { levels: { 13: { per_row_kr: 2660000 } },
    guarantees: [{ level: 13, type: 'SingelWinner', amount_kr: 10000000, sole_winner: true },
      { level: 13, type: 'Annan', description: 'extrapott', amount_kr: 500000, sole_winner: false },
      { level: 13, type: 'Tom', amount_kr: 0 }] }
  assert.deepEqual(guaranteeLines(forecast), [
    `om du är ensam vinnare på 13 rätt: minst ${kr(10000000)}`,
    `garanti extrapott: ${kr(500000)}`])
  assert.deepEqual(guaranteeLines({ levels: {} }), [])
  assert.deepEqual(guaranteeLines(null), [])
  // prognosen per rad är orörd av garantin
  assert.equal(perRowText(forecast.levels[13]), `≈ ${kr(2660000)}`)
})
