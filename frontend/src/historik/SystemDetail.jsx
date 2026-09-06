// Ett fryst system mot facit: liverättning, detalj och gruppertabell.
// Bruten ur AppV3.jsx 2026-09-02.
import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { CouponOverview } from './CouponOverview.jsx'
import { coverageResult, visibleResearch } from '../lib/couponView.js'
import { get } from '../lib/api.js'
import { PRODUCT_LABEL, RESEARCH_FAMILY_LABEL, fmtDay, STRATEGY_LABEL, horizonLabel, pctSigned, roiCls, marketTimeLabel, PH5_METHOD_LABEL } from '../lib/labels.js'
import { LoadingState, EmptyState, ErrorState, kr, SortableTable } from '../App.jsx'

export function SystemLiveCorrection({ live, error, observedAt, compact = false }) {
  if (!live) return (
    <div className={`v3syslive ${error ? 'error' : ''}`}>
      <b>{error ? 'Liverättningen är tillfälligt otillgänglig' : 'Hämtar liverättning…'}</b>
      <span className="v3hint">{error
        ? 'Försöker igen automatiskt. Det frysta systemet och slutliga facitet påverkas inte.'
        : 'Aktuell ställning hämtas utan att något nytt system skapas.'}</span>
    </div>
  )
  const levels = Object.keys(live.alive_per_level || {})
    .map(Number).sort((a, b) => b - a)
  const aliveText = (level) => {
    const lo = live.alive_min_per_level?.[level]
    const hi = live.alive_max_per_level?.[level]
    if (lo != null && hi != null && lo !== hi) {
      return `${lo.toLocaleString('sv-SE')}–${hi.toLocaleString('sv-SE')}`
    }
    return Number(live.alive_per_level?.[level] || 0).toLocaleString('sv-SE')
  }
  const status = (match) => match.cancelled ? 'struken · tecken väntar'
    : match.extra_time ? `ordinarie tid klar · ${match.status_text || 'förlängning'}`
      : match.final ? 'slut'
        : match.in_progress ? match.status_text || 'pågår'
          : 'ej startad'
  return (
    <section className="v3syslive" aria-label="Liverättning av testkupongen">
      <div className="v3syslivehead">
        <div>
          <span className="v3eyebrow">LIVERÄTTNING · PRELIMINÄRT</span>
          <h4>{live.all_decided ? 'Alla matcher avgjorda' : 'Så ligger testkupongen till nu'}</h4>
        </div>
        <span className="v3hint">uppdaterad {observedAt ? marketTimeLabel(observedAt) : 'nyss'}</span>
      </div>
      <div className="v3syslivekpis">
        <span><b>{live.n_decided}</b>/{live.n_events} fastställda</span>
        <span>fastställt bäst <b>{live.best_secure}</b> rätt</span>
        {live.current_known > 0 && live.current_best != null && (
          <span title="Bästa radens rätt om alla aktuella ställningar står sig.">
            läget nu <b>{live.current_best}/{live.current_known}</b></span>
        )}
        <span className={live.out_of_contention ? 'v3neg' : ''}>
          max <b>{live.max_possible}</b> möjligt</span>
      </div>
      <div className="v3syslivelevels">
        {levels.map((level) => (
          <span key={level} className={live.alive_per_level[level] ? '' : 'dead'}>
            <b>{aliveText(level)}</b>
            <small>rader kan nå {level} rätt</small>
          </span>
        ))}
      </div>
      {live.alive_unproven?.length > 0 && (
        <div className="v3note">Radantalet visas som ett spann eftersom ordinarie tids
          resultat ännu inte är belagt för {live.alive_unproven.join(', ')}.</div>
      )}
      {!compact && <div className="v3syslivematches">
        {(live.matches || []).map((match) => (
          <div key={match.col} className={`v3syslivematch${match.final ? ' final' : ''}`}>
            <span className="v3hint">{match.col}</span>
            <b>{match.description || [match.home, match.away].filter(Boolean).join(' – ')
              || `Match ${match.col}`}</b>
            <span className="v3syslivescore">{match.score || '–'}
              {match.sign && <i>{match.sign}</i>}</span>
            <span className="v3hint">{status(match)}</span>
          </div>
        ))}
      </div>}
      <p className="v3hint">”Fastställt” räknar bara matcher vars tecken står fast.
        ”Läget nu” använder även pågående ställningar. Slutligt facit och
        simulerad utdelning sätts fortfarande först från Svenska Spels officiella resultat.</p>
    </section>
  )
}
/* Ett fryst system match för match: täckte vi tecknet som gick in, och hur
   stod folkets streck vid frysningen mot vid spelstopp? */
export function SystemDetail({ product, draw, horizon, config, onClose }) {
  const dialogRef = useRef(null)
  useEffect(() => {
    const previous = document.activeElement
    const dialog = dialogRef.current
    const overflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    dialog.showModal()
    return () => {
      dialog.close()
      document.body.style.overflow = overflow
      previous?.focus?.({ preventScroll: true })
    }
  }, [])
  const [d, setD] = useState(null)
  const [err, setErr] = useState(null)
  const [live, setLive] = useState(null)
  const [liveErr, setLiveErr] = useState(null)
  const [liveObservedAt, setLiveObservedAt] = useState(null)
  const [rowPage, setRowPage] = useState(0)
  const [rowNumber, setRowNumber] = useState('')
  useEffect(() => {
    let current = true
    get(`/api/pool/systems/detail?product=${product}&draw=${draw}`
      + `&horizon=${horizon}&config=${encodeURIComponent(config)}`)
      .then((value) => { if (current) setD(value) })
      .catch((e) => { if (current) setErr(String(e)) })
    return () => { current = false }
  }, [product, draw, horizon, config])
  useEffect(() => {
    if (!d?.available || d.facit_complete) return undefined
    let current = true
    let pending = false
    let controller = null
    const liveUrl = `/api/pool/systems/live?product=${product}&draw=${draw}`
      + `&horizon=${horizon}&config=${encodeURIComponent(config)}`
    const detailUrl = `/api/pool/systems/detail?product=${product}&draw=${draw}`
      + `&horizon=${horizon}&config=${encodeURIComponent(config)}`
    const refresh = () => {
      if (!current || pending || document.visibilityState === 'hidden') return
      pending = true
      controller = new AbortController()
      get(liveUrl, { signal: controller.signal })
        .then((value) => {
          if (!current) return undefined
          if (value.settled) {
            // Settlementjobbet är klart. Hämta den tunga exakta detaljen EN
            // gång till och byt livebilden mot officiellt facit.
            return get(detailUrl, { signal: controller.signal }).then((detail) => {
              if (current) setD(detail)
            })
          }
          setLive(value.live || null)
          setLiveObservedAt(value.observed_at || null)
          setLiveErr(null)
          return undefined
        })
        .catch((reason) => {
          if (current && reason?.name !== 'AbortError') setLiveErr(String(reason))
        })
        .finally(() => { pending = false })
    }
    refresh()
    const timer = window.setInterval(refresh, 30000)
    document.addEventListener('visibilitychange', refresh)
    return () => {
      current = false
      controller?.abort()
      window.clearInterval(timer)
      document.removeEventListener('visibilitychange', refresh)
    }
  }, [d?.available, d?.facit_complete, product, draw, horizon, config])
  const pageSize = 20
  const rows = d?.rows || []
  const searchedRow = rowNumber === '' ? null
    : rows.find((row) => row.index === Number(rowNumber))
  const shownRows = rowNumber === ''
    ? rows.slice(rowPage * pageSize, (rowPage + 1) * pageSize)
    : searchedRow ? [searchedRow] : []
  const pageCount = Math.max(1, Math.ceil(rows.length / pageSize))
  const distribution = Object.entries(d?.correct_dist || {})
    .map(([correct, count]) => [Number(correct), Number(count)])
    .sort((a, b) => b[0] - a[0])
  const liveByEvent = Object.fromEntries(
    (live?.matches || []).map((match) => [match.event, match]))
  const liveByColumn = Object.fromEntries(
    (live?.matches || []).map((match) => [match.col, match]))
  const liveRowScore = (signs) => {
    if (!live?.matches?.length) return null
    let secure = 0
    let possible = 0
    for (let index = 0; index < signs.length; index += 1) {
      const match = liveByColumn[index + 1]
      const decided = match?.final && !match.cancelled && !match.sign_provisional
      if (!decided) possible += 1
      else if (match.sign === signs[index]) { secure += 1; possible += 1 }
    }
    return { secure, possible }
  }
  const coverage = coverageResult(d?.events || [], d?.correct_max, d?.facit_complete)
  return createPortal(
    <dialog ref={dialogRef} className="coupon-dialog" aria-label="Fryst kupong och facit"
      onCancel={(event) => { event.preventDefault(); onClose() }}>
    <div className="v3sysdetail" id="hist-system-detail">
      <div className="v3sysdetailhead">
        <b>{PRODUCT_LABEL[product] || product} · omgång {draw} · {d
          ? `${d.research ? `${RESEARCH_FAMILY_LABEL[d.research_family]
            || '🧪 Researchtest'} · ` : ''}${d.research
            ? (d.method === 'byggarslump' ? PH5_METHOD_LABEL[d.method] : d.label || PH5_METHOD_LABEL[d.method] || d.method)
            : STRATEGY_LABEL[d.strategy] || d.strategy || 'testsystem'}`
          : 'testsystem'}</b>
        <button className="v3more" onClick={onClose}>stäng ✕</button>
      </div>
      {err && <ErrorState message={err} />}
      {!d && !err && <LoadingState label="Hämtar systemet…" />}
      {d && !d.available && <EmptyState title="Systemet finns inte i ledgern" />}
      {d?.available && (
        <>
          <div className="v3sysdetailmeta">
            <span>{d.n_rows.toLocaleString('sv-SE')} rader · {kr(d.cost_kr)}</span>
            <span>fryst {horizonLabel(d)} före stopp{d.timely ? '' : ' (sen)'}</span>
            <span>{d.correct_max == null && live ? 'fastställt bäst ' : 'bäst '}
              <b>{d.correct_max ?? live?.best_secure ?? '–'}</b> rätt</span>
            {d.n_missed > 0 && (
              <span className="v3neg" title="Matcher där inget av systemets tecken
                gick in. Varje sådan match sänker takresultatet med ett rätt.">
                missade {d.n_missed} {d.n_missed === 1 ? 'match' : 'matcher'}</span>
            )}
            <span className={roiCls(d.roi)}>{d.correct_max == null
              ? 'väntar facit'
              : d.payout_complete === false ? 'utdelning okänd'
                : `${kr(d.payout_kr)} · ${pctSigned(d.roi)}`}</span>
          </div>
          {!d.facit_complete && <SystemLiveCorrection live={live}
            error={liveErr} observedAt={liveObservedAt} compact />}
          {coverage && <p className="v3note">
            {coverage.missing ? `${coverage.missing} ${coverage.missing === 1 ? 'rätt tecken saknades' : 'rätta tecken saknades'} helt. ` : 'Alla rätta tecken fanns med. '}
            {coverage.reductionLoss > 0
              ? `Tecknen kunde ge ${coverage.ceiling} rätt, men bästa sparade raden fick ${d.correct_max}. Rätt kombination reducerades bort.`
              : 'Systemet nådde det bästa resultat som de valda tecknen tillät.'}
          </p>}
          <CouponOverview events={d.events} nRows={d.n_rows} liveByEvent={liveByEvent} />
          {rows.length > 0 && (
            <details className="v3systemrows">
              <summary>Se enskilda rader och vinstfördelning ({rows.length.toLocaleString('sv-SE')} rader)</summary>
              <div className="v3systemrowshead">
                <div>
                  <h4>Exakta rader mot facit</h4>
                  <span className="v3hint">Det här testet består av {rows.length.toLocaleString('sv-SE')}
                    {' '}separata rader, inte en enda rad. {d.facit_complete
                      ? 'De är sorterade med bäst resultat först.'
                      : 'Facit saknas ännu, så den frysta originalordningen visas.'}
                    {' '}# är platsen i den sparade testfilen.</span>
                </div>
                <label className="v3rowfind">
                  <span>Hitta radnummer</span>
                  <input type="number" min="1" max={rows.length}
                    value={rowNumber} placeholder={`1–${rows.length}`}
                    onChange={(event) => setRowNumber(event.target.value)} />
                </label>
              </div>
              {d.facit_complete
                ? <div className="v3systemfacitline">
                    <b>Facit</b>
                    {(d.facit || '').split('').map((sign, index) => (
                      <span key={index}>{sign}</span>
                    ))}
                  </div>
                : <div className="v3note"><b>Facit väntar.</b> Kupongen är ändå
                    redan fryst och kan granskas exakt som den såg ut före
                    spelstopp.</div>}
              <div className="v3systemdist">
                {distribution.map(([correct, count]) => (
                  <span key={correct}>{count.toLocaleString('sv-SE')} {count === 1 ? 'rad' : 'rader'}
                    {' '}med <b>{correct} rätt</b></span>
                ))}
              </div>
              {d.audit_matches_stored === false && (
                <div className="v3note v3neg"><b>Kontrollvarning:</b> de omräknade
                  raderna stämmer inte med den sparade summeringen.</div>
              )}
              <div className="v3systemrowlist">
                {shownRows.map((row) => {
                  const rowLive = row.correct == null ? liveRowScore(row.signs) : null
                  return <div className="v3systemrow" key={row.index}>
                    <span className="v3systemrowindex">#{row.index}</span>
                    <div className="v3systemsigns" aria-label={`Rad ${row.index}: ${row.signs}`}
                      style={{ gridTemplateColumns: `repeat(${d.events.length}, minmax(0, 1fr))` }}>
                      {row.signs.split('').map((sign, index) => {
                        const match = liveByColumn[index + 1]
                        const liveClass = !match?.sign ? ''
                          : match.final ? (match.sign === sign ? 'hit' : 'miss')
                            : match.sign === sign ? 'liveleading' : ''
                        return <span key={index}
                          className={!d.facit_complete ? liveClass
                            : d.facit?.[index] === sign ? 'hit' : 'miss'}>{sign}</span>
                      })}
                    </div>
                    <b>{row.correct != null ? `${row.correct}/${d.events.length}`
                      : rowLive ? `${rowLive.secure} fast · max ${rowLive.possible}` : 'väntar'}</b>
                    {row.payout_kr == null ? null : row.payout_kr > 0
                      ? <span className="v3pos">+{kr(row.payout_kr)}</span>
                      : <span className="v3hint">0 kr</span>}
                  </div>
                })}
                {rowNumber !== '' && !searchedRow && (
                  <EmptyState title={`Rad #${rowNumber} finns inte`}
                    detail={`Ange ett nummer mellan 1 och ${rows.length}.`} />
                )}
              </div>
              {rowNumber === '' && pageCount > 1 && (
                <div className="v3rowpager">
                  <button disabled={rowPage === 0}
                    onClick={() => setRowPage((page) => Math.max(0, page - 1))}>← Föregående</button>
                  <span>Rader {rowPage * pageSize + 1}–{Math.min((rowPage + 1) * pageSize, rows.length)}
                    {' '}av {rows.length.toLocaleString('sv-SE')}</span>
                  <button disabled={rowPage >= pageCount - 1}
                    onClick={() => setRowPage((page) => Math.min(pageCount - 1, page + 1))}>Nästa →</button>
                </div>
              )}
            </details>
          )}
        </>
      )}
    </div>
    </dialog>, document.body
  )
}
/* En grupp är en simulerad konfiguration över flera omgångar, inte en spelad
   kupong. Håll därför kostnad/utdelning explicit kontrafaktiska i både rubrik
   och tooltip; annars läser den ackumulerade ROI-nämnaren som verkliga pengar. */
export function SystemGroupsTable({ id, groups, limit = null, onOpenLatest = null }) {
  return (
    <SortableTable id={id} className="v3histtable"
      wrapperClassName="v3histtablewrap"
      defaultSort={{ key: 'latest_frozen', dir: 'desc' }}
      rows={groups.filter(visibleResearch)} limit={limit}
      columns={[
        { key: 'product', label: 'Spel', defaultDir: 'asc',
          value: (g) => PRODUCT_LABEL[g.product] || g.product },
        { key: 'budget', label: 'Kostnad/test',
          title: 'Systemets kostnad i en enskild testomgång. Radpriset är 1 kr, så beloppet är också antalet rader.' },
        { key: 'strategy', label: 'Strategi', defaultDir: 'asc',
          value: (g) => STRATEGY_LABEL[g.strategy] || g.strategy || '' },
        { key: 'value_weight', label: 'Värdevikt' },
        { key: 'horizon_minutes', label: 'Fryst',
          title: 'Minuter före spelstopp' },
        { key: 'latest_frozen', label: 'Senast testad', defaultDir: 'desc',
          title: 'Datum för senaste omgång där konfigurationen sparades automatiskt',
          // Sortera kalenderdag, inte klockslaget för h3/m20. Då hålls
          // samma dags produkter ihop i backendens produktordning.
          value: (g) => g.latest_frozen?.slice(0, 10) || null },
        { key: 'n_frozen', label: 'Sparade tester',
          title: 'Antal automatiskt frysta förslag för gruppen.' },
        { key: 'n_evaluable', label: 'ROI-underlag',
          title: 'Frysta i tid, med känt resultat OCH känd utdelning — de enda ROI räknas på.' },
        { key: 'cost_kr', label: 'Sammanlagt',
          title: 'Antal tester med facit × kostnad per test. Inga pengar har spelats.' },
        { key: 'payout_kr', label: 'Simulerad utdelning',
          title: 'Kontrafaktiskt uppskattad utdelning. Detta är inte mottagna pengar.' },
        { key: 'roi', label: 'Simulerad ROI' },
        { key: 'best_correct', label: 'Bäst' },
        { key: 'open_latest', label: 'Rader', value: () => '' },
      ]}
      renderRow={(g) => {
        const perTest = g.cost_per_draw_kr ?? g.budget
        return (
          <tr key={`${g.product}-${g.config_key}-${g.horizon}`}
            className={g.retired ? 'v3retired' : ''}>
            <td>{g.research
              ? <span title="Research-only: påverkar inte ordinarie system eller promotion">🧪 </span>
              : null}{PRODUCT_LABEL[g.product] || g.product}</td>
            <td>{g.primary ? '★ ' : ''}{perTest != null ? kr(perTest) : '–'}</td>
            <td>{STRATEGY_LABEL[g.strategy] || g.strategy || '–'}</td>
            <td>{g.value_weight != null ? `${Math.round(g.value_weight * 100)} %` : '–'}</td>
            <td>{horizonLabel(g)}</td>
            <td>{g.latest_frozen ? fmtDay(g.latest_frozen) : '–'}</td>
            <td>{g.n_frozen}{g.n_timely < g.n_frozen
              ? <span className="v3hint"> ({g.n_frozen - g.n_timely} sena)</span> : ''}
              {g.n_cancelled
                ? <span className="v3hint"> ({g.n_cancelled} inställda)</span> : ''}</td>
            <td>{g.n_evaluable
              ? `${g.n_evaluable} ${g.n_evaluable === 1 ? 'test' : 'tester'}` : '–'}
              {g.n_payout_incomplete
                ? <span className="v3hint"> ({g.n_payout_incomplete} okänd utd.)</span> : ''}</td>
            <td className="v3costformula">{g.n_evaluable
              ? <>{g.n_evaluable} × {kr(perTest)} = <b>{kr(g.cost_kr)}</b></>
              : '–'}</td>
            <td>{g.n_evaluable ? kr(g.payout_kr) : '–'}</td>
            <td className={roiCls(g.roi)}>{pctSigned(g.roi)}</td>
            <td>{g.best_correct ?? '–'}</td>
            <td>{g.latest_draw_number != null && onOpenLatest
              ? <button className="v3more" onClick={() => onOpenLatest(g)}>
                  Visa senaste testet</button>
              : '–'}</td>
          </tr>
        )
      }}
      renderCard={(g) => {
        const perTest = g.cost_per_draw_kr ?? g.budget
        return (
          <article key={`${g.product}-${g.config_key}-${g.horizon}`}
            className={`v3groupcard${g.retired ? ' v3retired' : ''}`}>
            <div className="v3groupcardhead">
              <b>{g.research
                ? <span title="Research-only: påverkar inte ordinarie system eller promotion">🧪 </span>
                : null}{PRODUCT_LABEL[g.product] || g.product}</b>
              <strong className={roiCls(g.roi)}>{pctSigned(g.roi)}</strong>
            </div>
            <div className="v3groupcardmeta">
              <span>{g.primary ? '★ ' : ''}{kr(perTest)}/test</span>
              <span>{STRATEGY_LABEL[g.strategy] || g.strategy || '–'}</span>
              <span>värde {g.value_weight != null
                ? `${Math.round(g.value_weight * 100)} %` : '–'}</span>
              <span>fryst {horizonLabel(g)}</span>
            </div>
            <div className="v3groupcardformula">
              {g.n_evaluable
                ? <>{g.n_evaluable} {g.n_evaluable === 1 ? 'test' : 'tester'} × {kr(perTest)} = <b>{kr(g.cost_kr)}</b></>
                : 'Inga tester med komplett facit ännu'}
            </div>
            <div className="v3groupcardfoot">
              <span>{g.n_frozen} {g.n_frozen === 1 ? 'sparat test' : 'sparade tester'}</span>
              {g.n_cancelled ? <span>{g.n_cancelled} inställda</span> : null}
              <span>sim. utdelning {g.n_evaluable ? kr(g.payout_kr) : '–'}</span>
              <span>senast {g.latest_frozen ? fmtDay(g.latest_frozen) : '–'}</span>
              <span>bäst {g.best_correct ?? '–'} rätt</span>
            </div>
            {g.latest_draw_number != null && onOpenLatest && (
              <button className="v3more v3groupopen" onClick={() => onOpenLatest(g)}>
                Visa senaste testets rader och facit</button>
            )}
          </article>
        )
      }} />
  )
}
