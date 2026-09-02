import test from 'node:test'
import assert from 'node:assert/strict'
import { PRODUCT_LABEL, HIST_FAMILIES, IS_FAMILY, horizonLabel, pctSigned, roiCls, forwardTestFilterKey, ROI_MIN_N } from './labels.js'
import { FAMILY } from './families.js'

test('Topptipset-familjen är EN post i väljaren men tre produkter', () => {
  assert.equal(HIST_FAMILIES.filter((f) => f.id === 'topptipset').length, 1)
  assert.equal(IS_FAMILY('topptipset'), true)
  assert.equal(IS_FAMILY('stryktipset'), false)
  assert.equal(PRODUCT_LABEL.topptipsetextra, 'Topptipset Extra')
  assert.equal(FAMILY('topptipsetstryk'), 'topptipset')
  assert.equal(FAMILY('europatipset'), 'europatipset')
})

test('horisonter visas i minuter, aldrig som h3/m20', () => {
  assert.equal(horizonLabel({ horizon_minutes: 180, horizon: 'h3' }), '180 min')
  assert.equal(horizonLabel({ horizon: 'h3' }), 'h3')   // bara som sista utväg
  assert.equal(horizonLabel(null), '–')
})

test('pctSigned, roiCls och filternyckeln', () => {
  assert.equal(pctSigned(0.05), '+5 %')
  assert.equal(pctSigned(-0.05), '-5 %')
  assert.equal(pctSigned(null), '–')
  assert.equal(roiCls(0.1), 'v3pos'); assert.equal(roiCls(-0.1), 'v3neg'); assert.equal(roiCls(null), '')
  assert.equal(forwardTestFilterKey({ label: 'EV medel', method: 'x' }), 'EV medel')
  assert.equal(forwardTestFilterKey({ method: 'x' }), 'x')
  assert.ok(ROI_MIN_N >= 10)
})
