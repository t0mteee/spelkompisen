import test from 'node:test'
import assert from 'node:assert/strict'
import { fmt, kr, pct, timeAgo, fmtClose } from './format.js'

test('fmt visar två decimaler och streck för saknat', () => {
  assert.equal(fmt(2.5), '2.50')
  assert.equal(fmt(null), '–')
  assert.equal(fmt(undefined), '–')
})

test('kr och pct är stabila för typiska värden', () => {
  assert.equal(typeof kr(1234.5), 'string')
  assert.match(kr(1234.5), /^1.235 kr$/)
  assert.equal(kr(null), '–')
  assert.equal(pct(0.5), '50.0 %')
  assert.equal(pct(0.05), '5.00 %')
  assert.equal(pct(null), '–')
})

test('timeAgo ger relativ text utan att kasta', () => {
  const nyss = new Date(Date.now() - 30 * 1000).toISOString()
  assert.equal(typeof timeAgo(nyss), 'string')
  assert.equal(typeof timeAgo(null), 'string')
  assert.equal(typeof fmtClose('2026-09-05T13:59:00Z'), 'string')
})
