import assert from 'node:assert/strict'
import test from 'node:test'
import {
  couponHeadline, decisiveRequirements, drawPhase, forecastLevels, freshnessText,
  levelChips, liveSummary, matchClock, requirementText, shareText, signClass, sortDraws,
} from './liveView.js'

test('shareText klarar små andelar', () => {
  assert.equal(shareText(null), null)
  assert.equal(shareText(0), '0 %')
  assert.equal(shareText(0.125), '12,5 %')
  assert.equal(shareText(0.0042), '0,42 %')
  assert.equal(shareText(0.00001), '< 0,01 %')
})

test('matchClock visar minut, slut, förlängning och avspark', () => {
  assert.equal(matchClock({ in_progress: true, minute: 67 }), "67'")
  assert.equal(matchClock({ final: true }), 'Slut')
  assert.equal(matchClock({ extra_time: true }), 'Förlängning')
  assert.equal(matchClock({ postponed: true }), 'Uppskjuten')
  assert.equal(matchClock({ start: '2026-10-17T13:00:00Z' }), '15:00')
})

test('drawPhase och sortDraws', () => {
  const live = { started: true, n_decided: 4, n_live: 3, matches: new Array(13), close: '2026-10-17T14:00:00Z' }
  assert.equal(drawPhase(live).text, '4/13 klara · 3 pågår')
  assert.equal(drawPhase({ ...live, finished: true }).key, 'klar')
  assert.equal(drawPhase({ error: 'TimeoutError' }).key, 'fel')
  const later = { started: false, matches: [1], close: '2026-10-17T18:00:00Z' }
  const done = { finished: true, started: true, matches: [1], close: '2026-10-17T10:00:00Z' }
  assert.deepEqual(sortDraws([done, later, live]), [live, later, done])
})

test('signClass färgar kupongens tecken', () => {
  assert.equal(signClass({ sign: '1', final: true }, '1'), 'hit')
  assert.equal(signClass({ sign: '1', final: true }, 'X'), 'miss')
  assert.equal(signClass({ sign: '1', final: false }, '1'), 'leading')
  assert.equal(signClass({ sign: '1', final: false }, '2'), 'behind')
  assert.equal(signClass({ sign: null }, '1'), '')
})

test('krav för alla rätt i klartext', () => {
  assert.equal(requirementText([]), 'ingen rad kvar')
  assert.equal(requirementText(['1']), 'måste bli 1')
  assert.equal(requirementText(['1', 'X']), '1 eller X')
  assert.equal(requirementText(['1', 'X', '2']), 'alla tecken täckta')
  const coupon = { krav: [{ col: 3, signs: ['1'] }, { col: 8, signs: ['1', 'X', '2'] }] }
  assert.deepEqual(decisiveRequirements(coupon).map((k) => k.col), [3])
})

test('couponHeadline och levelChips', () => {
  assert.equal(couponHeadline({ top_level: 13, top_alive: 4 }), '13 rätt lever i 4 rader')
  assert.equal(couponHeadline({ top_level: 13, top_alive: 1 }), '13 rätt lever i 1 rad')
  assert.equal(couponHeadline({ out_of_contention: true, max_possible: 9 }),
    'Kan inte nå vinst längre (max 9 rätt)')
  assert.equal(couponHeadline({ all_decided: true, best_secure: 11 }), 'Klar: bäst 11 rätt')
  const chips = levelChips({ alive_per_level: { 12: 18, 13: 4 },
    alive_min_per_level: { 13: 2, 12: 18 }, alive_max_per_level: { 13: 4, 12: 18 },
    chance_per_level: { 13: 0.032 } })
  assert.deepEqual(chips, [
    { level: 13, alive: 4, span: [2, 4], chance: 0.032 },
    { level: 12, alive: 18, span: null, chance: null }])
})

test('forecastLevels och freshnessText', () => {
  assert.deepEqual(forecastLevels({ levels: { 12: { per_row_kr: 900 },
    13: { per_row_kr: 80000 }, 10: { per_row_kr: 0, below_min_payout: true } } }), [
    { level: 13, kr: 80000, belowMin: false }, { level: 12, kr: 900, belowMin: false },
    { level: 10, kr: 0, belowMin: true }])
  const now = new Date('2026-10-17T13:42:30Z')
  assert.deepEqual(freshnessText('2026-10-17T13:42:10Z', now),
    { text: 'uppdaterad 15:42:10', stale: false, age: 20 })
  assert.equal(freshnessText('2026-10-17T13:30:00Z', now).stale, true)
  assert.equal(freshnessText(null, now).stale, true)
})

test('liveSummary för Idag', () => {
  assert.equal(liveSummary({ draws: [] }), null)
  assert.equal(liveSummary({ draws: [{ started: false, coupons: [] }] }), null)
  const rows = liveSummary({ draws: [
    { product: 'stryktipset', name: 'Stryktipset', draw_number: 4975, started: true,
      n_decided: 2, n_live: 1, matches: new Array(13), folk_alla_ratt: 0.2,
      coupons: [{ top_level: 13, top_alive: 4 }] },
    { product: 'topptipset', name: 'Topptipset', draw_number: 4390, started: true,
      n_decided: 1, matches: new Array(8), folk_alla_ratt: 0.31, coupons: [] }] })
  assert.equal(rows.length, 2)
  assert.equal(rows[0].detail, '13 rätt lever i 4 rader')
  assert.equal(rows[1].detail, '31 % av folket har allt rätt')
})
