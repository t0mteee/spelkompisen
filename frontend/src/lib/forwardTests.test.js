import test from 'node:test'
import assert from 'node:assert/strict'
import { forwardView, matchesForwardFilters } from './forwardTests.js'

const filters = { product: 'alla', horizon: 'alla', method: 'alla', version: 'aktuell' }
const coupon = (changes = {}) => ({ product: 'stryktipset', draw_number: 1,
  horizon: 'h3', config_key: 'current', method: 'varderader', retired: false,
  timely: true, correct_max: 12, payout_complete: true, ...changes })

test('samma population för kuponger, grupper och KPI; arkiv dolt som standard', () => {
  const tests = [coupon(), coupon({ horizon: 'm20' }),
    coupon({ product: 'europatipset' }), coupon({ retired: true, config_key: 'old' })]
  const data = { tests, groups: tests.map((row) => ({ ...row, n: 1 })) }
  const all = forwardView(data, filters)
  assert.equal(all.coupons, 3)
  assert.equal(all.groups.length, 3)
  assert.equal(all.draws, 2, 'två frystider ger inte två oberoende omgångar')
  const selected = forwardView(data, { ...filters, product: 'stryktipset', horizon: 'm20' })
  assert.equal(selected.coupons, 1)
  assert.equal(selected.groups.length, 1)
  assert.equal(selected.facit, 1)
  assert.equal(selected.evaluated, 1)
})

test('arkiv och metodval ger samma urval; aktuella och äldre blandas bara på begäran', () => {
  const data = { tests: [coupon(), coupon({ retired: true, config_key: 'old', method: 'maxev' })] }
  assert.equal(forwardView(data, { ...filters, version: 'aldre' }).tests[0].config_key, 'old')
  assert.equal(forwardView(data, { ...filters, version: 'alla' }).coupons, 2)
  assert.equal(forwardView(data, { ...filters, method: 'maxev' }).coupons, 0)
  assert.equal(forwardView(data, { ...filters, version: 'aldre', method: 'maxev' }).coupons, 1)
})

test('matchfacit, komplett belopp och tidsriktig frysning är skilda saker', () => {
  const view = forwardView({ tests: [coupon(), coupon({ correct_max: 0 }),
    coupon({ payout_complete: null }), coupon({ payout_complete: false }),
    coupon({ timely: false }), coupon({ correct_max: null })] }, filters)
  assert.equal(view.facit, 5, 'noll rätt är ett känt facit')
  assert.equal(view.evaluated, 2, 'okänt belopp och sen frysning får inte räknas')
})

test('saknad aktivmetadata faller inte öppet; tomt och okänt filter ger noll', () => {
  assert.equal(matchesForwardFilters(coupon({ retired: undefined }), filters), false)
  assert.equal(forwardView({}, filters).draws, 0)
  assert.equal(forwardView({ tests: [coupon()] }, { ...filters, product: 'saknas' }).coupons, 0)
})
