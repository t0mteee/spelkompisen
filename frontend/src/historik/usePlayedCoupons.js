// Laddning av VERKLIGT spelade kuponger i tre steg (lokalt → snabb
// liverättning → fullt svar med chans), samma kontrakt som gamla PlayedPanel
// (2026-08-xx) men som hook så Mina kuponger och Idag delar den. Första
// stegets fel maskeras ALDRIG som "inga kuponger": `error` sätts och `data`
// förblir null tills ett anrop lyckats.
import { useCallback, useEffect, useRef, useState } from 'react'

export function usePlayedCoupons({ intervalMs = 60_000, live = true } = {}) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const requestRef = useRef(0)
  const abortRef = useRef(null)
  const load = useCallback(async () => {
    const requestId = ++requestRef.current
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller
    const stamp = Date.now()
    const current = () => requestRef.current === requestId && !controller.signal.aborted
    const read = async (url) => {
      const response = await fetch(url, { cache: 'no-store', signal: controller.signal })
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      return response.json()
    }
    try {
      const local = await read(`/api/pool/played?live=false&_t=${stamp}`)
      if (!current()) return
      setError(null)
      const hasOpen = (local.coupons || []).some((coupon) => !coupon.settled_at)
      // BEHÅLL föregående livestatus medan den nya hämtas — annars blinkar
      // korten tomma varje minut.
      setData((previousData) => {
        if (!current()) return previousData
        const previous = Object.fromEntries(
          (previousData?.coupons || []).filter((c) => c.live).map((c) => [c.id, c.live]))
        return {
          ...local,
          coupons: (local.coupons || []).map((coupon) => (
            !coupon.settled_at && hasOpen && live
              ? { ...coupon, live_pending: true, live: previous[coupon.id] }
              : coupon
          )),
        }
      })
      if (!hasOpen || !live) return
      try {
        const quick = await read(`/api/pool/played?chance=false&_t=${stamp}`)
        if (current()) setData({
          ...quick,
          coupons: (quick.coupons || []).map((coupon) => (
            coupon.settled_at ? coupon : { ...coupon, live_pending: true }
          )),
        })
      } catch (reason) {
        if (reason?.name === 'AbortError' || !current()) return
      }
      if (!current()) return
      try {
        const full = await read(`/api/pool/played?_t=${stamp}`)
        if (current()) setData(full)
      } catch (reason) {
        if (reason?.name === 'AbortError' || !current()) return
        setData((previousData) => previousData ? {
          ...previousData,
          coupons: (previousData.coupons || []).map((coupon) => (
            coupon.settled_at ? coupon : {
              ...coupon, live_pending: false, live_error: reason?.name || 'FetchError',
            }
          )),
        } : previousData)
      }
    } catch (reason) {
      if (reason?.name !== 'AbortError' && current()) setError(reason?.message || 'Okänt fel')
    }
  }, [live])
  useEffect(() => {
    load()
    const tick = () => { if (document.visibilityState === 'visible') load() }
    const timer = window.setInterval(tick, intervalMs)
    return () => {
      window.clearInterval(timer)
      abortRef.current?.abort()
    }
  }, [load, intervalMs])
  return { data, error, reload: load }
}
