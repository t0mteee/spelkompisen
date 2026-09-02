// Formattering utan React: tid, pengar, procent. Bruten ur App.jsx 2026-09-02.

export const fmt = (o) => (o === null || o === undefined ? '–' : o.toFixed(2))
export function timeAgo(iso) {
  if (!iso) return 'aldrig'
  const s = (Date.now() - new Date(iso).getTime()) / 1000
  if (s < 90) return 'nyss'
  if (s < 3600) return `${Math.round(s / 60)} min sedan`
  if (s < 86400) return `${Math.round(s / 3600)} h sedan`
  return `${Math.round(s / 86400)} dygn sedan`
}
export function fmtTs(t) {
  const d = new Date(t); const p = (n) => String(n).padStart(2, '0')
  return `${p(d.getDate())}/${p(d.getMonth() + 1)} ${p(d.getHours())}:${p(d.getMinutes())}`
}
// behåll bara förändringspunkter (hoppa över upprepade identiska odds)
export function fmtClose(iso) {
  return iso ? iso.slice(5, 16).replace('T', ' ') : ''
}
export function fmtFetched(iso) {
  if (!iso) return '–'
  try {
    return new Date(iso).toLocaleString('sv-SE', { day: 'numeric', month: 'numeric', hour: '2-digit', minute: '2-digit' })
  } catch { return '–' }
}
export function fmtStart(iso) {
  if (!iso) return ''
  try {
    return new Date(iso).toLocaleString('sv-SE', {
      weekday: 'short', day: 'numeric', month: 'numeric', hour: '2-digit', minute: '2-digit',
    })
  } catch { return '' }
}
export const kr = (v) => (v == null ? '–' : Math.round(v).toLocaleString('sv-SE') + ' kr')

/* ---------- Svenska Spel "Egna rader"-export (filuppladdning) ----------
   Tjänsten finns på .../externa-systemspel (Stryktipset, Europatipset och
   Topptipset — alla varianter laddas upp via topptipset-sidan).
   Filformat: en rad per spelad rad, "E,<tecken>,<tecken>,..." i matchordning.
   Vi enumererar konkreta rader (E) – korrekt även för reducerade system där
   vi måste behålla exakt de raderna (ett M-system skulle spela hela produkten). */
export const pct = (v) => (v == null ? '–' : (v * 100 < 0.1 ? (v * 100).toFixed(3) : (v * 100).toFixed(v < 0.1 ? 2 : 1)) + ' %')

/* Räkna kupongens nyckeltal från analysens fair-sannolikheter.
   poly = ∏(pᵢ·x + (|Sᵢ|−pᵢ)) ger förväntat antal vinstrader per nivå.
   dp   = Poisson-binomial över pᵢ ger sannolikheten för bästa radens antal rätt. */
