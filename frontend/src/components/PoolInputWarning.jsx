import { useRef, useState } from 'react'
import { poolInputTitle, poolReviewText, sourceLabel } from '../lib/poolInputHealth.js'

export function PoolInputWarning({ health, scope = 'Aktuell analys', compact = false }) {
  const [copyState, setCopyState] = useState('')
  const reportRef = useRef(null)
  const title = poolInputTitle(health)
  if (!title) return null
  const review = poolReviewText(health, scope)
  async function copy() {
    try {
      await navigator.clipboard.writeText(review)
      setCopyState('copied')
    } catch {
      // LAN på http saknar ofta Clipboard API, särskilt på telefon.
      // Behåll ett manuellt kopierbart underlag, inga falska ”kopierat”.
      setCopyState('manual')
      reportRef.current?.focus({ preventScroll: true })
      reportRef.current?.select()
    }
  }
  return <aside className={`pool-input-warning ${health.level}`} role="status" aria-label={`Oddsvarning · ${scope}`}>
    <strong>⚠ {compact ? 'Underlag vid systembygget: ' : ''}{title}</strong>
    {!compact && <p>{health.missing_all > 0
      ? 'Kontrollera underlaget innan du använder förslaget. Utan kompletta odds kan bygget använda folkets streck eller reservvärden.'
      : health.missing_sharp > 0
        ? 'SvS-odds finns som grund, men Pinnacles oberoende referens saknas för delar av kupongen.'
        : health.missing_svs > 0
          ? 'Pinnacle finns som reserv för 1X2. SvS-priserna är ofullständiga.'
          : 'Teckenvalet saknar Ö/U-stöd i delar av kupongen. Övriga regler används fortfarande.'}</p>}
    <details>
      <summary>Visa matcher och granskningsunderlag</summary>
      <ul>{health.issues.map(m => <li key={m.event_number}>
        <b>{m.event_number}. {m.description}</b>
        <span>Saknar: {m.missing.join(' · ')}</span>
        {m.reason && <span>Orsak: {m.reason}</span>}
        <span>Sannolikhetsbas: {sourceLabel(m.prob_source)}</span>
        {m.reserve_total && <span>{m.reserve_total.available
          ? `${m.reserve_total.label}: Ö/U ${m.reserve_total.line} · Över ${m.reserve_total.over_odds} / Under ${m.reserve_total.under_odds}. Observerat ${new Date(m.reserve_total.observed_at).toLocaleString('sv-SE')}. Visas som reservunderlag, används ännu inte av byggaren.`
          : `Ö/U-reserv: ${m.reserve_total.status === 'source_error' ? 'källan kunde inte läsas' : 'inget färskt verifierat pris'}.`}</span>}
      </li>)}</ul>
      <p>Visar underlaget för {scope.toLowerCase()}. Ett cachat Pinnacle-pris används bara om det
        är högst 90 min gammalt och länken inte tappats efter priset — annars står orsaken vid
        matchen. SvS-oddsen är ingen färskhetsgaranti. Utan angiven orsak finns inget Pinnacle-pris
        alls; tidigt i veckan kan det vara normalt.</p>
      <button type="button" onClick={copy}>Kopiera för granskning</button>
      <span role="status">{copyState === 'copied' ? ' Kopierat — klistra in till Codex eller Claude.'
        : copyState === 'manual' ? ' Automatisk kopiering saknas här. Markera och kopiera texten nedan.' : ''}</span>
      <textarea ref={reportRef} readOnly value={review} rows={5}
        aria-label={`Granskningsunderlag · ${scope}`} />
    </details>
  </aside>
}
