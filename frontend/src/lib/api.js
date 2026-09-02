// Hämtning mot backend: cache-buster, no-store, JSON-kontroll och backendens
// detail-text. Bruten ur AppV3.jsx 2026-09-02.

// Ett svar som inte är JSON betyder nästan alltid att backend är nere eller
// startar om: vite-proxyn svarar då med något annat än vårt API. Rått blir
// det "SyntaxError: The string did not match the expected pattern" i Safari
// — ett meddelande som inte säger användaren någonting alls (observerat i
// drift 2026-08-06 mitt under en omstart av :8002). Säg vad som hänt i
// stället; felet i sig är övergående och ett omladdat anrop löser det.
export const OFFLINE = 'Backend svarade inte med data — servern kan vara nere eller '
  + 'starta om. Prova att ladda om om en liten stund.'
export const asJson = async (r) => {
  try {
    return await r.json()
  } catch {
    throw new Error(OFFLINE)
  }
}
export const get = (url, options = {}) => fetch(
  `${url}${url.includes('?') ? '&' : '?'}_t=${Date.now()}`,
  { cache: 'no-store', ...options }).then((r) => {
    if (!r.ok) throw new Error(`${r.status}`)
    return asJson(r)
  })
// Som get(), men lyfter fram backendens detail-text. Bor på modulnivå:
// cache-busterns Date.now() får inte ligga i en komponentkropp.
export const getDetail = (url, label) => fetch(`${url}${url.includes('?') ? '&' : '?'}_t=${Date.now()}`,
  { cache: 'no-store' }).then(async (r) => {
    if (!r.ok) {
      // Felkroppen kan själv vara icke-JSON (proxyfel, gateway-sida).
      let detail = null
      try { detail = (await r.json()).detail } catch { /* ingen detail */ }
      throw new Error(detail || `${label} ${r.status}`)
    }
    return asJson(r)
  })
export const readState = () => {
  try { return JSON.parse(localStorage.getItem('svs_state') || '{}') || {} } catch { return {} }
}
