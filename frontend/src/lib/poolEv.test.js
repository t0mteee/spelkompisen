import test from 'node:test'
import assert from 'node:assert/strict'
import { KAPPA, FOLK_MIN, kappaFor, folkProb, poissonBinomial, evalRows } from './poolEv.js'

test('kappaFor läser tabellen och faller till 1,0', () => {
  assert.equal(kappaFor('stryktipset', 13), KAPPA.stryktipset[13])
  assert.equal(kappaFor('stryktipset', 9), 1.0)
  assert.equal(kappaFor('okänd', 13), 1.0)
  for (const p of Object.keys(KAPPA)) for (const v of Object.values(KAPPA[p])) assert.ok(v >= 1, `${p} κ<1`)
})

test('folkProb golvar folkets sannolikhet', () => {
  assert.equal(folkProb({ streck: 0 }), FOLK_MIN, 'streck 0 får aldrig ge sannolikhet 0')
  assert.equal(folkProb(null), FOLK_MIN)
  assert.equal(folkProb({ streck: 50 }), 0.5)
  assert.equal(folkProb({ fair_prob: 0.3 }), 0.3)
})

test('poissonBinomial är en fördelning över antal medvinnare', () => {
  const dist = poissonBinomial([0.5, 0.5, 0.5])
  const sum = dist.reduce((a, b) => a + b, 0)
  assert.ok(Math.abs(sum - 1) < 1e-9, `summa ${sum}`)
  assert.equal(dist.length, 4)
})

test('evalRows kan anropas utan att kasta på tom rad-lista', () => {
  assert.doesNotThrow(() => evalRows([], [], 0, 13, 0, 'stryktipset'))
})
