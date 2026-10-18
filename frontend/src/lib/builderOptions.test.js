import test from 'node:test'
import assert from 'node:assert/strict'
import { BUILDER_VALUE_WEIGHT, visibleSystemTypes, restoredSysType } from './builderOptions.js'

const TYPES = [
  { id: 'ev' }, { id: 'farg', hidden: true }, { id: 'math' }, { id: 'red' },
  { id: 'g', hidden: true }, { id: 'svs_r409', hidden: true },
]

test('bara synliga systemtyper erbjuds, i ordning med Värderader först', () => {
  assert.deepEqual(visibleSystemTypes(TYPES).map((type) => type.id), ['ev', 'math', 'red'])
})

test('ett sparat dolt eller okänt val börjar om på Värderader', () => {
  assert.equal(restoredSysType('farg', TYPES), 'ev')
  assert.equal(restoredSysType('svs_r409', TYPES), 'ev')
  assert.equal(restoredSysType(undefined, TYPES), 'ev')
  assert.equal(restoredSysType('red', TYPES), 'red')
  assert.equal(restoredSysType('math', TYPES), 'math')
})

test('värdevikten är låst på 50 %', () => {
  assert.equal(BUILDER_VALUE_WEIGHT, 50)
})
