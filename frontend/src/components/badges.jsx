// Små märken: gnistkurva, byggmärke, Labb-pill. Brutna ur AppV3.jsx 2026-09-02.
import { STRATEGY_LABEL, LABB_STATUS } from '../lib/labels.js'


export function MiniSpark({ values, width = 220, height = 44 }) {
  const vals = (values || []).filter((v) => v != null)
  if (vals.length < 2) return null
  const min = Math.min(...vals), max = Math.max(...vals)
  const span = max - min || 1
  const pts = vals.map((v, i) =>
    `${(i / (vals.length - 1)) * width},${height - 4 - ((v - min) / span) * (height - 8)}`).join(' ')
  return (
    <svg className="v3spark" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" aria-hidden="true">
      <polyline points={pts} fill="none" stroke="currentColor" strokeWidth="1.6" />
    </svg>
  )
}

/* ================================ Idag ==================================== */
/* Förslagstypen bakom en bokförd kupong. Kuponger före 2026-08-05 saknar den
   — de var aldrig observerade och bakfylls aldrig. */
export function BuildBadge({ row }) {
  if (!row?.strategy && row?.budget == null) {
    return <span className="v3hint" title="Bokförd innan förslagstyp började
      sparas (2026-08-05). Uppgiften fanns aldrig och bakfylls inte.">okänd</span>
  }
  const parts = [
    row.budget != null ? `${Math.round(row.budget)} kr` : null,
    STRATEGY_LABEL[row.strategy] || row.strategy,
    row.value_weight != null ? `värde ${Math.round(row.value_weight * 100)} %` : null,
  ].filter(Boolean)
  return <span className="v3buildbadge">{parts.join(' · ')}</span>
}
export function LabbPill({ s }) {
  const [label, tip] = LABB_STATUS[s] || LABB_STATUS.samlar
  return <span className={`v3labbpill ${s}`} title={tip}>{label}</span>
}
