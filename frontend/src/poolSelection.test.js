import assert from 'node:assert/strict'
import test from 'node:test'

import {
  beginRequest, payoutMatchesSelection, requestIsCurrent,
} from './poolSelection.js'

test('ett sent svar blir ogiltigt så fort en ny laddning börjar', () => {
  const sequence = { current: 0 }
  const oldRequest = beginRequest(sequence)
  const newRequest = beginRequest(sequence)

  assert.equal(requestIsCurrent(sequence, oldRequest), false)
  assert.equal(requestIsCurrent(sequence, newRequest), true)
})

test('pottdata måste matcha både produkt och omgång', () => {
  const payout = { product: 'topptipset', draw_number: 4259 }

  assert.equal(payoutMatchesSelection(payout, 'topptipset', 4259), true)
  assert.equal(payoutMatchesSelection(payout, 'topptipset', 4258), false)
  assert.equal(payoutMatchesSelection(payout, 'europatipset', 4259), false)
})
