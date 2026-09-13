// Mina kuponger: status, filter och summering av VERKLIGT spelade kuponger.
// Ren logik utan React. Pengar räknas bara på kuponger med komplett
// publicerad utdelning — okänd utdelning är inte förlust.
import { FAMILY } from './families.js'

export const STATUS = {
  ej_startad: 'ej startad',
  live: 'live',
  avgjord: 'avgjord · väntar på utdelning',
  rattad: 'rättad',
  rattad_ofullstandig: 'rättad · utdelning ofullständig',
  datafel: 'livedata saknas',
  vantar: 'väntar på livebild',
}

export function couponStatus(coupon, now = new Date()) {
  if (coupon.settled_at) return coupon.payout_complete ? 'rattad' : 'rattad_ofullstandig'
  if (coupon.live_error) return 'datafel'
  const live = coupon.live
  if (!live) {
    const close = coupon.draw_close ? new Date(coupon.draw_close) : null
    return close && close > now ? 'ej_startad' : 'vantar'
  }
  if (live.all_decided) return 'avgjord'
  if ((live.n_decided || 0) > 0 || (live.current_known || 0) > 0) return 'live'
  return 'ej_startad'
}

export const isOpen = (coupon) => !coupon.settled_at

const couponDay = (coupon) => coupon.draw_close || coupon.played_at || null

export function inPeriod(coupon, period, now = new Date()) {
  if (!period || period === 'alla') return true
  const day = couponDay(coupon)
  if (!day) return false
  const when = new Date(day)
  if (Number.isNaN(when.getTime())) return false
  if (period === 'ar') return when.getFullYear() === now.getFullYear()
  const days = { '30d': 30, '90d': 90 }[period]
  if (!days) return true
  return (now.getTime() - when.getTime()) <= days * 86400000
}

export function filterCoupons(coupons, filters = {}, now = new Date()) {
  const { period = 'alla', product = 'alla', status = 'alla' } = filters
  return (coupons || []).filter((coupon) => (
    inPeriod(coupon, period, now)
    && (product === 'alla' || FAMILY(coupon.product) === product)
    && (status === 'alla'
      || (status === 'oppna' ? isOpen(coupon) : !isOpen(coupon)))
  ))
}

// Summeringen följer ALLTID urvalet som visas. Saldo och ROI bara på
// kuponger med komplett utdelning; öppna och ofullständiga räknas men
// summeras aldrig som pengar.
export function summarizeCoupons(coupons) {
  const list = coupons || []
  const complete = list.filter((c) => c.settled_at && c.payout_complete)
  const spent = complete.reduce((sum, c) => sum + (Number(c.cost_kr) || 0), 0)
  const won = complete.reduce((sum, c) => sum + (Number(c.payout_kr) || 0), 0)
  return {
    n: list.length,
    n_open: list.filter(isOpen).length,
    n_settled: list.filter((c) => c.settled_at).length,
    n_complete: complete.length,
    n_incomplete: list.filter((c) => c.settled_at && !c.payout_complete).length,
    spent_kr: spent,
    won_kr: won,
    balance_kr: won - spent,
    roi: spent > 0 ? won / spent - 1 : null,
  }
}

// Nyligen rättade: det som är NYTT sedan sist, för Idag.
export function recentlySettled(coupons, days = 7, now = new Date()) {
  return (coupons || []).filter((c) => c.settled_at
    && (now.getTime() - new Date(c.settled_at).getTime()) <= days * 86400000)
}
