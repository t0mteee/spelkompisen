import test from 'node:test'
import assert from 'node:assert/strict'
import { systemComposition } from './systemComposition.js'

test('visar faktisk radandel även för saknat tecken och ensidigt system', () => {
  const sys = { picks: [{event_number: 5, signs: ['1','X']}], rows: [['1'],['1'],['X']] }
  const [row] = systemComposition(sys)
  assert.deepEqual(row.signs.map(s => s.count), [2,1,0])
  assert.equal(row.signs[0].share, 2/3)
  assert.equal(row.signs[2].selected, false)
})

test('matematiskt system får tecken, inte fabricerad procent', () => {
  const [row] = systemComposition({ picks: [{event_number: 1, signs: ['1','2']}], rows: [] })
  assert.deepEqual(row.signs.map(s => s.share), [null,null,null])
  assert.deepEqual(row.signs.map(s => s.selected), [true,false,true])
})
