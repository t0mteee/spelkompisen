import test from 'node:test'
import assert from 'node:assert/strict'
import { agentAppUrl, parseRoute, formatRoute, parentRoute, sameRoute } from './routes.js'

test('utan hash startar Idag, okänd hash likaså', () => {
  assert.deepEqual(parseRoute(''), { view: 'idag' })
  assert.deepEqual(parseRoute('#'), { view: 'idag' })
  assert.deepEqual(parseRoute('#/'), { view: 'idag' })
  assert.deepEqual(parseRoute('#/nagot-annat'), { view: 'idag' })
  assert.equal(formatRoute({ view: 'idag' }), '')
})

test('kuponger med och utan öppen kupong', () => {
  assert.deepEqual(parseRoute('#/kuponger'), { view: 'historik', tab: 'kuponger', coupon: null })
  assert.deepEqual(parseRoute('#/kuponger/12'), { view: 'historik', tab: 'kuponger', coupon: 12 })
  assert.deepEqual(parseRoute('#/kuponger/abc'), { view: 'historik', tab: 'kuponger', coupon: null })
  assert.equal(formatRoute({ view: 'historik', tab: 'kuponger', coupon: 12 }), '#/kuponger/12')
  assert.equal(formatRoute({ view: 'historik' }), '#/kuponger')
})

test('tester: katalog, ett test och exakt testkupong', () => {
  assert.deepEqual(parseRoute('#/tester'), { view: 'historik', tab: 'tester', test: null, open: null })
  assert.deepEqual(parseRoute('#/tester/ph5'), { view: 'historik', tab: 'tester', test: 'ph5', open: null })
  const deep = '#/tester/ph5/stryktipset/4969/h3/ph5-v4-dr1-b5000-medel'
  assert.deepEqual(parseRoute(deep), { view: 'historik', tab: 'tester', test: 'ph5',
    open: { product: 'stryktipset', draw_number: 4969, horizon: 'h3', config_key: 'ph5-v4-dr1-b5000-medel' } })
  assert.equal(formatRoute(parseRoute(deep)), deep)
  // ofullständig detalj faller tillbaka till testet
  assert.deepEqual(parseRoute('#/tester/ph5/stryktipset/4969'), { view: 'historik', tab: 'tester', test: 'ph5', open: null })
})

test('facit, oddset-fokus och tur och retur', () => {
  assert.deepEqual(parseRoute('#/facit/topptipset'), { view: 'historik', tab: 'facit', product: 'topptipset' })
  assert.deepEqual(parseRoute('#/oddset/varde'), { view: 'oddset', focus: 'varde' })
  for (const hash of ['#/kuponger', '#/kuponger/3', '#/tester', '#/tester/mathmax', '#/facit', '#/facit/stryktipset', '#/pool', '#/oddset', '#/oddset/radar', '#/labb']) {
    assert.equal(formatRoute(parseRoute(hash)), hash)
  }
  assert.ok(sameRoute(parseRoute('#/historik'), { view: 'historik', tab: 'kuponger' }))
})

test('föräldern till en detalj', () => {
  assert.deepEqual(parentRoute(parseRoute('#/kuponger/3')), { view: 'historik', tab: 'kuponger' })
  assert.deepEqual(parentRoute(parseRoute('#/tester/ph5/stryktipset/4969/h3/k')), { view: 'historik', tab: 'tester', test: 'ph5' })
  assert.deepEqual(parentRoute(parseRoute('#/tester/ph5')), { view: 'historik', tab: 'tester' })
  assert.deepEqual(parentRoute(parseRoute('#/pool')), { view: 'idag' })
})

test('beslut: lista och direktlänk till ett beslut går tur och retur', () => {
  assert.deepEqual(parseRoute('#/beslut'), { view: 'beslut', item: null })
  assert.deepEqual(parseRoute('#/beslut/12'), { view: 'beslut', item: 12 })
  assert.equal(formatRoute({ view: 'beslut', item: null }), '#/beslut')
  assert.equal(formatRoute({ view: 'beslut', item: 12 }), '#/beslut/12')
  assert.deepEqual(parseRoute(formatRoute({ view: 'beslut', item: 7 })), { view: 'beslut', item: 7 })
})

test('agentens app på samma värd, port 5176', () => {
  const loc = { protocol: 'http:', hostname: 'macbook-pro-server.tail71ffdc.ts.net' }
  assert.equal(agentAppUrl(loc), 'http://macbook-pro-server.tail71ffdc.ts.net:5176/')
  assert.equal(agentAppUrl(loc, 'pool'), 'http://macbook-pro-server.tail71ffdc.ts.net:5176/#/pool')
  assert.equal(agentAppUrl(null), 'http://127.0.0.1:5176/')
})
