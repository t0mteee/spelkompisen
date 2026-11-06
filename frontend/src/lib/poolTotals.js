// Ö/U-raden under poolmatchen. pool-draw-risk-v2: X-skyddets total är
// Pinnacle först, annars Svenska Spels/Kambis lina. Smarkets Ö/U
// (pool_reference.read_ou_for_draw) visas bredvid och används aldrig i bygget.
const TOTAL_SOURCE = { pinnacle: 'P', svenskaspel_kambi: 'SvS' }
const fmtLine = (v) => String(v).replace('.', ',')
const fmtOdds = (v) => (typeof v === 'number' ? v.toFixed(2) : '–')

export function poolTotalParts(m) {
  const parts = []
  if (m?.total_line != null) {
    const src = TOTAL_SOURCE[m.total_source] || ''
    parts.push(`Ö/U ${fmtLine(m.total_line)}${src ? ` ${src}` : ''}`)
  }
  const sm = m?.reference_ou
  if (sm?.line != null) parts.push(`${sm.short || 'Sm'} ${fmtLine(sm.line)}: Ö ${fmtOdds(sm.O)} / U ${fmtOdds(sm.U)}`)
  return parts
}

export function poolTotalTitle(m) {
  const lines = []
  if (m?.total_line != null) {
    lines.push(m.total_source === 'svenskaspel_kambi'
      ? `X-skyddets total: Svenska Spels/Kambis Ö/U-lina ${fmtLine(m.total_line)} (Pinnacle saknas).`
      : `X-skyddets total: Pinnacles Ö/U-lina ${fmtLine(m.total_line)}.`)
  }
  const sm = m?.reference_ou
  if (sm?.line != null) {
    const pct = sm.fair?.O != null ? ` (${Math.round(sm.fair.O * 100)} % över)` : ''
    lines.push(`Smarkets Ö/U ${fmtLine(sm.line)}${pct}, senast bekräftat ${new Date(sm.last_seen_at).toLocaleString('sv-SE')}. Bara visning.`)
  }
  return lines.join('\n')
}
