import test from 'node:test'
import assert from 'node:assert/strict'
import { couponStatus, filterCoupons, summarizeCoupons, recentlySettled } from './coupons.js'

const now = new Date('2026-09-13T12:00:00Z')
const c = (over) => ({ id: 1, product: 'stryktipset', draw_number: 4969, cost_kr: 256,
  draw_close: '2026-09-05T13:59:00Z', settled_at: null, payout_complete: null, payout_kr: null, ...over })

test('status: ej startad, live, avgjord, rättad, ofullständig, datafel', () => {
  assert.equal(couponStatus(c({ draw_close: '2026-09-20T13:59:00Z' }), now), 'ej_startad')
  assert.equal(couponStatus(c({ live: { n_decided: 0, current_known: 0 } }), now), 'ej_startad')
  assert.equal(couponStatus(c({ live: { n_decided: 3, current_known: 5 } }), now), 'live')
  assert.equal(couponStatus(c({ live: { all_decided: true, n_decided: 13 } }), now), 'avgjord')
  assert.equal(couponStatus(c({ settled_at: '2026-09-06', payout_complete: 1 }), now), 'rattad')
  assert.equal(couponStatus(c({ settled_at: '2026-09-06', payout_complete: 0 }), now), 'rattad_ofullstandig')
  assert.equal(couponStatus(c({ live_error: 'FetchError' }), now), 'datafel')
  assert.equal(couponStatus(c({}), now), 'vantar')
})

test('filter på period, spelfamilj och status', () => {
  const list = [
    c({ id: 1, product: 'topptipsetstryk', draw_close: '2026-09-12T18:00:00Z' }),
    c({ id: 2, product: 'topptipset', draw_close: '2026-07-01T18:00:00Z', settled_at: '2026-07-02', payout_complete: 1, payout_kr: 10 }),
    c({ id: 3, product: 'stryktipset', draw_close: '2025-12-24T18:00:00Z', settled_at: '2025-12-25', payout_complete: 1 }),
  ]
  assert.deepEqual(filterCoupons(list, { product: 'topptipset' }, now).map((x) => x.id), [1, 2])
  assert.deepEqual(filterCoupons(list, { period: '30d' }, now).map((x) => x.id), [1])
  assert.deepEqual(filterCoupons(list, { period: 'ar' }, now).map((x) => x.id), [1, 2])
  assert.deepEqual(filterCoupons(list, { status: 'oppna' }, now).map((x) => x.id), [1])
  assert.deepEqual(filterCoupons(list, { status: 'rattade', product: 'stryktipset' }, now).map((x) => x.id), [3])
})

test('summeringen räknar pengar bara på komplett utdelning', () => {
  const sum = summarizeCoupons([
    c({ id: 1 }),
    c({ id: 2, settled_at: '2026-09-06', payout_complete: 1, cost_kr: 100, payout_kr: 250 }),
    c({ id: 3, settled_at: '2026-09-06', payout_complete: 0, cost_kr: 100, payout_kr: 9999 }),
  ])
  assert.equal(sum.n, 3); assert.equal(sum.n_open, 1); assert.equal(sum.n_settled, 2)
  assert.equal(sum.n_complete, 1); assert.equal(sum.n_incomplete, 1)
  assert.equal(sum.spent_kr, 100); assert.equal(sum.won_kr, 250); assert.equal(sum.balance_kr, 150)
  assert.equal(sum.roi, 1.5)
  assert.equal(summarizeCoupons([]).roi, null)
})

test('nyligen rättade inom sju dygn', () => {
  const list = [c({ id: 1, settled_at: '2026-09-10T08:00:00Z' }), c({ id: 2, settled_at: '2026-08-10T08:00:00Z' }), c({ id: 3 })]
  assert.deepEqual(recentlySettled(list, 7, now).map((x) => x.id), [1])
})
