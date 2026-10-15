// Livesidan (#/live, 2026-10-15): alla pågående poolomgångar sida vid sida.
// Backend räknar livebilden i bakgrunden (backend/app/pool_live_view.py) och
// sidan hämtar bara det färdiga svaret var 20:e s medan den syns. LIVEBILD,
// aldrig facit: facit och utdelning kommer ur settlementlagret i Historik.
import { useCallback, useEffect, useRef, useState } from 'react'
import { get } from '../lib/api.js'
import { kr } from '../lib/format.js'
import {
  POLL_MS, couponHeadline, decisiveRequirements, drawPhase, forecastLevels,
  freshnessText, levelChips, matchClock, requirementText, shareText, signClass, sortDraws,
} from '../lib/liveView.js'
import { ErrorState, LoadingState } from '../components/ui.jsx'

const SIGNS = ['1', 'X', '2']

function usePoolLive() {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [, setTick] = useState(0)
  const inFlight = useRef(null)
  const load = useCallback(() => {
    if (inFlight.current) return
    const controller = new AbortController()
    inFlight.current = controller
    get('/api/pool/live', { signal: controller.signal })
      .then((value) => { setData(value); setError(null) })
      .catch((e) => { if (e?.name !== 'AbortError') setError(e.message) })
      .finally(() => { if (inFlight.current === controller) inFlight.current = null })
  }, [])
  useEffect(() => {
    load()
    const poll = window.setInterval(() => { if (!document.hidden) load() }, POLL_MS)
    // Sekundvisaren i "uppdaterad för X s sedan" utan nytt anrop.
    const clock = window.setInterval(() => setTick((t) => t + 1), 5000)
    const onVisible = () => { if (!document.hidden) load() }
    document.addEventListener('visibilitychange', onVisible)
    return () => {
      window.clearInterval(poll)
      window.clearInterval(clock)
      document.removeEventListener('visibilitychange', onVisible)
      inFlight.current?.abort()
      inFlight.current = null
    }
  }, [load])
  return { data, error, reload: load }
}

function SignChips({ match, counts }) {
  const signs = SIGNS.filter((s) => counts?.[s])
  if (!signs.length) return <span className="v3hint">–</span>
  return (
    <span className="lv-signs">
      {signs.map((s) => (
        <span key={s} className={`lv-sign ${signClass(match, s)}`}
          title={`${counts[s]} ${counts[s] === 1 ? 'rad' : 'rader'} med ${s}`}>{s}</span>
      ))}
    </span>
  )
}

function MatchTable({ draw, coupons }) {
  const shown = coupons.slice(0, 3)
  return (
    <table className="lv-matches">
      <colgroup>
        <col className="c-n" /><col /><col className="c-tid" /><col className="c-sc" />
        <col className="c-nu" />
        {shown.map((c) => <col key={c.id} className="c-k" />)}
      </colgroup>
      <thead>
        <tr>
          <th>#</th><th>Match</th><th>Tid</th><th>Ställn.</th><th>Nu</th>
          {shown.map((c, i) => (
            <th key={c.id} title={`Kupong #${c.id}${c.label ? ` · ${c.label}` : ''}`}>
              {shown.length > 1 ? `K${i + 1}` : 'Din'}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {draw.matches.map((m, i) => (
          <tr key={m.event ?? i} className={m.in_progress ? 'live' : m.final ? 'done' : ''}>
            <td>{m.event ?? i + 1}</td>
            <td className="lv-name">
              <span>{m.home || m.description}</span>
              {m.away && <span className="v3hint"> – {m.away}</span>}
              {m.live_probs && (
                <span className="lv-probs" title="Livepris, devigat (procent per tecken)">
                  {SIGNS.map((s) => `${s} ${Math.round((m.live_probs[s] || 0) * 100)}`).join(' · ')}
                </span>
              )}
            </td>
            <td className={m.in_progress ? 'lv-clock live' : 'lv-clock'}>{matchClock(m)}</td>
            <td className="lv-score">{m.score ? m.score.replace('-', '–') : ''}</td>
            <td>
              {m.sign && (
                <span className={`lv-now${m.final ? ' final' : ''}${m.sign_provisional ? ' prov' : ''}`}
                  title={m.sign_provisional ? 'Förlängning: tecknet efter ordinarie tid är inte belagt än' : undefined}>
                  {m.sign}</span>
              )}
            </td>
            {shown.map((c) => (
              <td key={c.id}><SignChips match={m} counts={c.row_signs?.[String(m.event)]} /></td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function CouponBlock({ coupon, index, many }) {
  if (coupon.error) {
    return <div className="lv-coupon"><span className="v3hint">Kupong #{coupon.id}: livebilden kunde inte räknas.</span></div>
  }
  const krav = decisiveRequirements(coupon)
  const chips = levelChips(coupon)
  const anyChance = chips.some((c) => c.chance != null)
  return (
    <div className="lv-coupon">
      <div className="lv-couponhead">
        <b>{many ? `K${index + 1} · ` : ''}{couponHeadline(coupon)}</b>
        <a className="v3more" href={`#/kuponger/${coupon.id}`}>kupongen →</a>
      </div>
      <span className="v3hint">
        #{coupon.id}{coupon.label ? ` · ${coupon.label}` : ''} · {coupon.n_rows} rader · {kr(coupon.cost_kr)}
        {coupon.current_best != null && ` · om ställningarna står sig: ${coupon.current_best} rätt`
          + ` (${coupon.current_best_rows} ${coupon.current_best_rows === 1 ? 'rad' : 'rader'})`}
      </span>
      {chips.length > 0 && (
        <div className="lv-levels">
          {chips.map((c) => (
            <span key={c.level} className={`lv-level${c.alive ? '' : ' dead'}`}
              title={c.span ? `Förlängning utan belagt tecken: mellan ${c.span[0]} och ${c.span[1]} rader` : undefined}>
              <b>{c.level} rätt</b>
              <span>{c.span ? `${c.span[0]}–${c.span[1]}` : c.alive} {c.alive === 1 && !c.span ? 'rad' : 'rader'}</span>
              {anyChance && c.chance != null && <i>{shareText(c.chance)} chans</i>}
            </span>
          ))}
        </div>
      )}
      {!coupon.all_decided && coupon.top_alive > 0 && (
        <div className="lv-krav">
          <span className="lv-kravhead">För {coupon.top_level} rätt krävs</span>
          {krav.length
            ? krav.map((k) => (
              <span key={k.col} className="lv-kravrow">
                <b>{k.col}</b> {k.description || ''}: <em>{requirementText(k.signs)}</em>
              </span>
            ))
            : <span className="v3hint">Alla kvarvarande tecken är täckta — vilket resultat som helst håller {coupon.top_level} rätt vid liv.</span>}
        </div>
      )}
      {(coupon.alive_rows || []).length > 0 && !coupon.all_decided && (
        <details className="lv-rows">
          <summary>Levande rader ({coupon.alive_rows_total ?? coupon.alive_rows.length})</summary>
          <ul>
            {coupon.alive_rows.map((r) => (
              <li key={r.n}>
                <span>rad {r.n}</span>
                <span>{r.secure} säkra, max {r.possible}</span>
                <span className="lv-need">{r.open.map((o) => `${o.col}:${o.sign}`).join(' ')}</span>
              </li>
            ))}
          </ul>
        </details>
      )}
      {coupon.chance_note && <span className="v3hint">{coupon.chance_note}</span>}
    </div>
  )
}

function DrawCard({ draw }) {
  const phase = drawPhase(draw)
  const coupons = draw.coupons || []
  const forecast = forecastLevels(draw.forecast)
  return (
    <article className="v3card lv-card" id={`live-${draw.product}-${draw.draw_number}`}>
      <div className="lv-head">
        <h3>{draw.name} <span className="v3hint">#{draw.draw_number}</span></h3>
        <span className={`lv-phase ${phase.key}`}>{phase.text}</span>
      </div>
      {draw.error ? <span className="v3hint">Svenska Spels livebild svarade inte ({draw.error}). Nästa försök om 20 s.</span> : (
        <>
          {forecast.length > 0 && (
            <div className="lv-forecast" title={draw.forecast?.note}>
              <span className="v3hint">Prognos per rad om det slutar som nu:</span>
              {forecast.map((f) => (
                <span key={f.level}><b>{f.level}</b> {f.belowMin ? '0 kr*' : kr(f.kr)}</span>
              ))}
            </div>
          )}
          {draw.folk_alla_ratt != null && (
            <span className="v3hint">
              Folket: {shareText(draw.folk_alla_ratt)} av raderna har allt rätt hittills
              (ur strecken, givet ställningarna nu).
            </span>
          )}
          <MatchTable draw={draw} coupons={coupons} />
          {coupons.map((c, i) => (
            <CouponBlock key={c.id} coupon={c} index={i} many={coupons.length > 1} />
          ))}
          {!coupons.length && <span className="v3hint">Ingen egen kupong på den här omgången.</span>}
        </>
      )}
    </article>
  )
}

export function LiveView() {
  const { data, error, reload } = usePoolLive()
  if (error && !data) return <ErrorState message={`Livebilden kunde inte hämtas (${error})`} />
  if (!data) return <LoadingState label="Hämtar livebilden…" />
  const draws = sortDraws(data.draws)
  const fresh = freshnessText(data.as_of)
  return (
    <div className="lv">
      <div className="lv-top">
        <h2>Live</h2>
        <span className={fresh.stale ? 'lv-fresh stale' : 'lv-fresh'}>
          {fresh.text}{data.active ? ' · uppdateras var 20:e s' : ''}
        </span>
        <button type="button" onClick={reload}>Uppdatera</button>
      </div>
      {draws.length > 1 && (
        <nav className="lv-jump" aria-label="Omgångar">
          {draws.map((d) => (
            <a key={`${d.product}-${d.draw_number}`} href={`#/live`}
              onClick={(e) => {
                e.preventDefault()
                document.getElementById(`live-${d.product}-${d.draw_number}`)
                  ?.scrollIntoView({ behavior: 'smooth', block: 'start' })
              }}>
              {d.name} {d.draw_number} · {drawPhase(d).text}
            </a>
          ))}
        </nav>
      )}
      {!draws.length && (
        <div className="v3card">
          <span className="v3hint">Inget poolspel pågår just nu. Omgångar visas här från spelstopp
            tills facit är klart, och dina kupongers omgångar från 30 min före spelstopp.</span>
        </div>
      )}
      <div className="lv-grid">
        {draws.map((d) => <DrawCard key={`${d.product}-${d.draw_number}`} draw={d} />)}
      </div>
      <p className="v3hint">Livebild ur Svenska Spels egen payload, Flashscores ordinarie tid och
        livepriser — aldrig facit. Prognosen är vår skattning, inte Svenska Spels siffra.</p>
    </div>
  )
}
