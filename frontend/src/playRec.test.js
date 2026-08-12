import assert from 'node:assert/strict'
import test from 'node:test'

import { kompaktKr, playRecommendation, projectionBasisText } from './playRec.js'

// Uppmätta återbetalningar, se _payout_ratio i backend/app/main.py.
const STRYK = 0.598
const TOPP = 0.700

const omgang = (over) => ({
  payout_ratio: STRYK, spelvarde: STRYK, spelvarde_proj: STRYK,
  turnover: 838_499, projected_turnover: 12_138_765, ...over,
})

test('utan jackpot är avstå aritmetiskt tvunget för alla tre produkterna', () => {
  for (const ratio of [STRYK, 0.637, TOPP]) {
    const r = playRecommendation(omgang({
      payout_ratio: ratio, spelvarde: ratio, spelvarde_proj: ratio,
    }))
    assert.equal(r.level, 'skip')
  }
})

test('avståndet är jackpoten som saknas till tunt läge, mot samma bas som spelvärdet', () => {
  const r = playRecommendation(omgang())

  assert.equal(r.proj, true)
  assert.equal(r.bas, 12_138_765)
  // (0,80 − 0,598) × 12 138 765 ≈ 2,45 Mkr
  assert.ok(Math.abs(r.gap - 0.202 * 12_138_765) < 1)
  assert.equal(kompaktKr(r.gap), '2,5 Mkr')
})

test('live-omsättning används när prognosen inte är högre', () => {
  const r = playRecommendation(omgang({ turnover: 20_000_000, projected_turnover: 12_138_765 }))

  assert.equal(r.proj, false)
  assert.equal(r.bas, 20_000_000)
  assert.ok(Math.abs(r.gap - 0.202 * 20_000_000) < 1)
})

test('tillräcklig jackpot lyfter omgången till tunt och sedan till spelläge', () => {
  const tunt = playRecommendation(omgang({ spelvarde_proj: 0.85 }))
  assert.equal(tunt.level, 'thin')
  // Nästa tröskel är nu 100 %, inte 80 %.
  assert.ok(Math.abs(tunt.gap - 0.15 * 12_138_765) < 1)

  const spela = playRecommendation(omgang({ spelvarde_proj: 1.04 }))
  assert.equal(spela.level, 'go')
  assert.equal(spela.gap, null, 'i spelläge finns inget avstånd kvar att visa')
})

test('en omgång utan omsättning ger inget avstånd i stället för delning med noll', () => {
  const r = playRecommendation(omgang({ turnover: 0, projected_turnover: 0 }))

  assert.equal(r.bas, 0)
  assert.equal(r.gap, null)
  assert.ok(Number.isFinite(r.sv))
})

test('kompaktKr håller sig kort i chipet', () => {
  assert.equal(kompaktKr(4_958_434), '5,0 Mkr')
  assert.equal(kompaktKr(869_533), '870 tkr')
  assert.equal(kompaktKr(139_287), '139 tkr')
  assert.equal(kompaktKr(900), '900 kr')
  assert.equal(kompaktKr(null), '0 kr')
})

test('prognosgrunden blir läsbar text och aldrig object Object', () => {
  assert.equal(projectionBasisText({ mode: 'weekday', n: 8, weekday: 5 }),
    'median av 8 senaste omgångarna med samma spelstoppsveckodag (lör)')
  assert.equal(projectionBasisText({ mode: 'all', n: 6 }),
    'median av senaste 6 omgångarna oavsett veckodag')
  assert.equal(projectionBasisText(null), 'median av tidigare omgångar')
})
