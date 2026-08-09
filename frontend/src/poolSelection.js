// Små rena grindar för omgångsbundet UI-state. De ligger utanför React så
// sena-svar-regeln kan regressionsprovas utan ett tungt browser-testramverk.
export function beginRequest(sequenceRef) {
  sequenceRef.current += 1
  return sequenceRef.current
}

export function requestIsCurrent(sequenceRef, token) {
  return sequenceRef.current === token
}

export function payoutMatchesSelection(payouts, product, draw) {
  return payouts?.product === product
    && Number(payouts?.draw_number) === Number(draw)
}
