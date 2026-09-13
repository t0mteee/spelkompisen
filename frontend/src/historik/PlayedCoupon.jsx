/* eslint-disable react-refresh/only-export-components -- delar komponenter och små etiketthjälpare. */
// Dina VERKLIGT spelade kuponger: livekort, kupongdetalj och import.
// Flyttade ur App.jsx 2026-09-13 (Mina kuponger); listlogiken bor i
// historik/MinaKuponger.jsx och laddningen i usePlayedCoupons.js.
import { useEffect, useRef, useState } from 'react'
import { CouponOverview } from './CouponOverview.jsx'
import { PRODUCT_LABEL } from '../lib/labels.js'
import { topAliveForecast, forecastBasisText, FORECAST_NOTE } from '../lib/forecast.js'
import { LoadingState, ErrorState, kr } from '../App.jsx'

function couponLabel(c) {
  // Ingen variantetikett: Topptipset är Topptipset. Dagens/Stryk/Extra är
  // omgångsserier hos Svenska Spel, inte olika spel — omgångsnumret skiljer
  // dem åt där det behövs.
  return `${PRODUCT_LABEL[c.product] || c.product} · omgång ${c.draw_number}`
}
function couponDate(c) {
  if (!c?.draw_close) return 'datum saknas'
  const date = new Date(c.draw_close)
  if (Number.isNaN(date.getTime())) return 'datum saknas'
  return date.toLocaleDateString('sv-SE', {
    weekday: 'short', day: 'numeric', month: 'short', year: 'numeric',
  })
}
function couponKindLabel(c) {
  if (c?.build_kind === 'byggare-komplement-a') return 'Kupong A'
  if (c?.build_kind === 'byggare-komplement-b') return 'Kupong B'
  const suffix = String(c?.label || '').split('·').map((part) => part.trim()).at(-1)
  if (suffix && suffix !== c.label && !/^omgång\s/i.test(suffix)) return suffix
  if (c?.build_kind === 'byggare') return 'Förslag'
  return c?.build_kind || null
}
function couponTitle(c) {
  const kind = couponKindLabel(c)
  return `${couponLabel(c)}${kind ? ` · ${kind}` : ''}`
}

/* Liverättningen: matcherna i kupongordning med ställning, mitt tecken och —
   för de som är kvar — vilket resultat som håller flest rader vid liv.
   Aggregaten under (bäst X rätt, chans per nivå) säger VAD som hänt men aldrig
   VILKEN match det gäller, och utan den kopplingen gick kupongen inte att följa
   medan omgången pågick. */
function LiveScorecard({ live }) {
  const matches = live?.matches || []
  if (!matches.length) return null
  const cheerByCol = Object.fromEntries((live.cheer || []).map((c) => [c.col, c]))
  const topLevel = live.cheer?.[0]?.top_level ?? live.n_events

  return (
    <table className="grid compact liverattning">
      <thead>
        <tr>
          <th>#</th><th>Match</th><th>Ställning</th>
          <th title="Kupongens tecken i den här matchen och hur många rader som har vardera.">Mina rader</th>
          <th title={`Hur många rader som fortfarande kan nå ${topLevel} rätt om matchen slutar så.`}>Heja på</th>
        </tr>
      </thead>
      <tbody>
        {matches.map((m) => {
          const cheer = cheerByCol[m.col]
          const label = m.description || `${m.home || '?'} – ${m.away || '?'}`
          /* Struken match: SvS fastställer tecknet i settlementet, så den
             håller alla tecken öppna tills dess — aldrig "rätt för alla". */
          /* Poolen fastställs på ordinarie 90 min, så en match i förlängning
             är klar för kupongen men inte klar som match. Båda ska sägas. */
          const status = m.cancelled ? 'struken'
            : m.extra_time ? `ordinarie klar · ${m.status_text || 'förlängning'}`
              : m.final ? 'slut'
                : m.in_progress ? (m.status_text || 'spelas')
                  : 'ej start'
          return (
            <tr key={m.col} className={m.final ? 'decided' : ''}>
              <td className="hint">{m.col}</td>
              <td>
                <span className="lr-team">{label}</span>
                <span className={`lr-status${m.extra_time ? ' warn' : ''}`}>{status}</span>
              </td>
              <td>
                <b>{m.score || '–'}</b>
                {m.sign && (
                  <span className={`lr-sign${m.final ? ' final' : ''}`}>{m.sign}</span>
                )}
                {/* Matchen är avgjord för kupongen, men utan Fulltime eller
                    Overtime går ordinarie tid inte att skilja från Current. */}
                {m.sign_provisional && (
                  <span className="lr-prov" title="Matchen är i förlängning och räknas som klar — poolen fastställs på ordinarie 90 minuter. Svenska Spel har dock inte publicerat ordinarie tids resultat än, så ställningen här kan innehålla förlängningsmål. Tecknet rättas automatiskt när slutresultatet kommer.">*</span>
                )}
              </td>
              <td className="lr-mine">
                {['1', 'X', '2'].map((s) => {
                  const n = m.row_signs?.[s]
                  if (!n) return null
                  // Rätt så långt = grönt, fällt = utgråat. Under pågående
                  // match är det preliminärt och får inte se ut som facit.
                  const tone = !m.sign ? '' : s === m.sign
                    ? (m.final ? ' hit' : ' leading') : (m.final ? ' miss' : '')
                  return (
                    <span key={s} className={`lr-chip${tone}`}
                      title={`${n} rader har ${s}`}>{s}<i>{n}</i></span>
                  )
                })}
              </td>
              <td>
                {cheer?.best
                  ? <span className="lr-cheer" title={`1: ${cheer.signs['1'].top} · X: ${cheer.signs.X.top} · 2: ${cheer.signs['2'].top} rader kvar till ${topLevel} rätt`}>
                      <b>{cheer.best}</b><i>{cheer.signs[cheer.best].top}</i>
                    </span>
                  : cheer
                    ? <span className="hint" title="Alla tre utfallen lämnar lika många rader med chans — matchen avgör ingenting för den här kupongen.">spelar ingen roll</span>
                    : <span className="hint">–</span>}
              </td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}

/* VILKA rader som lever. Nivåtabellen säger "2 rader kvar till 8 rätt" men
   pekar inte ut någon av dem — på en kupong med hundratals rader är det inte
   handlingsbart. Här står radnumret, hur många rätt raden har säkrat och,
   det som faktiskt betyder något, vilket tecken den behöver i varje match som
   ÄR KVAR.

   Listan hänger på en VALD NIVÅ, inte på "kan nå något". Topptipset har åtta
   matcher men bara 8 rätt delar potten, så "lever mot golvnivån" var 184 av
   256 rader och sa ingenting. Nivåknapparna bär `alive_per_level`, som är
   räknad på hela kupongen och därför sann även när radlistan är kapad.

   En struken match och ett obelagt förlängningstecken räknas som kvarvarande,
   så raden visas med det tecken den BEHÖVER — aldrig med ett tecken vi gissat
   åt Svenska Spel. */
function AliveRowsTable({ live }) {
  const [open, setOpen] = useState(false)
  const [level, setLevel] = useState(null)
  const rows = live?.alive_rows || []
  const cols = live?.alive_rows_open_cols || []
  const perLevel = live?.alive_per_level || {}
  const levels = Object.keys(perLevel).map(Number)
    .filter((l) => perLevel[l] > 0).sort((a, b) => b - a)
  if (!rows.length || !cols.length || !levels.length) return null
  const shownLevel = level != null && perLevel[level] ? level : levels[0]
  const held = rows.filter((r) => r.possible >= shownLevel)
  const truth = perLevel[shownLevel]
  const byCol = Object.fromEntries((live.matches || []).map((m) => [m.col, m]))
  const label = (col) => {
    const m = byCol[col]
    if (!m) return `M${col}`
    return m.home || (m.description || '').split(/\s+[–-]\s+/)[0] || `M${col}`
  }
  const full = (col) => {
    const m = byCol[col]
    return m ? (m.description || [m.home, m.away].filter(Boolean).join(' – ')) : `Match ${col}`
  }
  return (
    <div className="aliverows">
      <button className="linkbtn" onClick={() => setOpen(!open)}
        title="Radnummer, säkrade rätt och vilket tecken varje överlevande rad behöver i matcherna som är kvar.">
        {open ? 'Dölj vilka rader' : 'Visa vilka rader'}
      </button>
      {open && (
        <>
          <div className="aliverows-levels">
            {levels.map((l) => (
              <button key={l} type="button"
                className={l === shownLevel ? 'on' : ''}
                onClick={() => setLevel(l)}
                title={`${perLevel[l]} rader kan fortfarande nå ${l} rätt`}>
                {l} rätt<i>{perLevel[l]}</i>
              </button>
            ))}
          </div>
          <div className="tablewrap">
            <table className="grid compact aliverows-table">
              <thead>
                <tr>
                  <th title="Radens nummer i kupongen, i samma ordning som filen du lämnade in.">rad</th>
                  <th title="Rätt som redan står fast.">rätt nu</th>
                  {/* `max` är `rätt nu` plus antalet kvarvarande matcher —
                      samma konstant för varje rad. Bekvämt på desktop, men
                      det är den kolumn som får stryka på foten när tre
                      matchkolumner ska rymmas på 375 px. */}
                  <th className="ar-max"
                    title="Bästa antal rätt raden fortfarande kan nå.">max</th>
                  {cols.map((col) => (
                    <th key={col} title={full(col)}>
                      {/* Matchnumret binder kolumnen till liverättningen
                          ovanför. Lagnamnet kortas på mobil, numret aldrig. */}
                      <i>{col}</i><span>{label(col)}</span>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {held.map((r) => (
                  <tr key={r.n}>
                    <td className="hint">{r.n}</td>
                    <td><b>{r.secure}</b></td>
                    <td className="ar-max">{r.possible}</td>
                    {r.open.map((o) => (
                      <td key={o.col} className="ar-sign">{o.sign}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {/* Radlistan är kapad; nivåräknaren är det inte. Säg vilket tal som
              är hela sanningen i stället för att låta tabellhöjden ljuga. */}
          {truth > held.length && (
            <p className="hint">Visar {held.length} av {truth} rader som kan nå
              {' '}{shownLevel} rätt — de med flest säkrade rätt.</p>
          )}
        </>
      )}
    </div>
  )
}

/* Ett pågående system i siffror: hur långt raderna kommit och vad oddsen på
   de kvarvarande matcherna säger om chansen per vinstnivå. Sannolikheterna
   räknas i backend över HELA utfallsrummet — raderna delar ju matcher, så en
   produkt av per-rad-chanser hade varit fel. */
function PlayedLiveCard({ c, onForget }) {
  const live = c.live
  /* Exakt noll är noll. "<0,1%" om ett utfall som är uteslutet läste som en
     liten men verklig chans, och gjorde intervallets underkant obegriplig. */
  const pct = (p) => p === 0 ? '0%'
    : p >= 0.1 ? `${(p * 100).toFixed(0)}%`
      : p >= 0.001 ? `${(p * 100).toFixed(1)}%` : '<0,1%'
  const levels = live ? Object.keys(live.alive_per_level)
    .map(Number).sort((a, b) => b - a) : []
  const liveSourceNames = { svenskaspel: 'SvS', ninja: 'Ninja', pinnacle: 'Pinnacle' }
  const liveSourceText = Object.entries(live?.chance_live_source_counts || {})
    .map(([source, count]) => `${liveSourceNames[source] || source} ${count}`)
    .join(', ')
  return (
    <div className="playedcard">
      <div className="playedcard-head">
        <b>{couponLabel(c)}</b>
        <span className="hint" title="Omgångens spelstopp">{couponDate(c)}</span>
        {/* "pågår" på en omgång där varje match är spelad är osant — den
            väntar bara på att SvS publicerar utdelningen. Gårdagens
            Topptipset låg kvar som aktiv av precis det skälet. */}
        {live?.all_decided
          ? <span className="epill" title="Alla matcher är avgjorda. Kupongen får facit när Svenska Spel publicerar utdelningen.">
              avgjord · väntar på utdelning</span>
          : <span className="epill live">pågår</span>}
        <span className="hint">{c.n_rows} rader · {kr(c.cost_kr)}</span>
        {onForget && <button className="linkbtn" onClick={onForget}
          title="Ta bort felaktigt bokförd kupong (går bara innan facit satts)">✕ glöm</button>}
      </div>
      {!live && (
        <p className="hint">{c.live_pending
          ? 'Hämtar livestatus…'
          : c.live_error
          ? <span title={c.live_error}>Livestatus tillfälligt otillgänglig — försöker igen automatiskt inom en minut.</span>
          : 'Väntar på omgångens första resultat.'}</p>
      )}
      {live && (
        <>
          <div className="playedcard-sum">
            <span><b>{live.n_decided}</b>/{live.n_events} avgjorda</span>
            <span title="Rätt i matcher vars resultat redan står fast.">
              fastställt bäst <b>{live.best_secure}</b> rätt
            </span>
            {live.current_known > 0 && live.current_best != null && (
              <span className={live.current_best === live.n_events ? 'pos' : ''}
                title="Bästa radens rätt om alla aktuella ställningar blir slutresultat. Pågående matcher kan fortfarande ändras.">
                om det slutar som nu <b>{live.current_best}</b>/{live.current_known}
                {live.current_best_rows > 0
                  ? ` · ${live.current_best_rows} rad${live.current_best_rows === 1 ? '' : 'er'}`
                  : ''}
              </span>
            )}
            {/* Max nåbart är ren aritmetik och finns även när en livemarknad
                är avstängd — det är ofta den enda siffra som betyder något. */}
            {live.max_possible != null && (
              <span className={live.out_of_contention ? 'neg' : ''}
                title="Bästa antal rätt någon rad fortfarande kan nå: säkrade rätt plus alla oavgjorda matcher.">
                max <b>{live.max_possible}</b> möjligt
              </span>
            )}
            {live.chance_open_matches != null && (
              <span className="hint">{live.chance_open_matches} matcher kvar</span>
            )}
            {(() => {
              const fc = topAliveForecast(live)
              return fc ? <span title={FORECAST_NOTE}>
                prognos {fc.level} rätt <b>≈ {kr(fc.per_row_kr)}</b>/rad
              </span> : null
            })()}
          </div>
          <LiveScorecard live={live} />
          {live.out_of_contention && (
            <p className="playedcard-dead">
              Kupongen kan inte längre nå någon vinstnivå — bästa raden kan som
              mest få <b>{live.max_possible}</b> rätt och lägsta redovisade
              nivå är {Math.min(...levels)}.
            </p>
          )}
          {!live.out_of_contention && <table className="grid compact playedlevels">
            <thead><tr><th>nivå</th><th>rader kvar</th>
              <th title="Oddsbaserad sannolikhet att kupongen når nivån när alla pågående matcher är slut. Inte andelen rätt just nu.">chans att nå</th>
              {live.forecast && <th title="Omgångens pott per nivå: omsättning × vinstplan, jackpot på toppnivån.">pott</th>}
              {live.forecast && <th title={FORECAST_NOTE}>prognos per rad</th>}
            </tr></thead>
            <tbody>
              {levels.map((lvl) => {
                const alive = live.alive_per_level[lvl]
                /* En förlängningsmatch utan publicerad ordinarie tid gör
                   radantalet till ett spann, inte ett faktum. */
                const aLo = live.alive_min_per_level?.[lvl]
                const aHi = live.alive_max_per_level?.[lvl]
                const aliveText = aLo != null && aLo !== aHi
                  ? `${aLo}–${aHi}` : (alive || '–')
                const p = live.chance_per_level?.[lvl]
                // Saknar en match pris finns ingen punktskattning, bara ett
                // intervall betingat på hur den matchen går.
                const lo = live.chance_min_per_level?.[lvl]
                const hi = live.chance_max_per_level?.[lvl]
                const text = !alive ? '0%'
                  : p != null ? pct(p)
                    : lo != null ? (lo === hi ? pct(lo) : `${pct(lo)}–${pct(hi)}`)
                      : '–'
                return (
                  <tr key={lvl} className={(aHi ?? alive) ? '' : 'dead'}>
                    <td><b>{lvl} rätt</b></td>
                    <td title={aLo != null && aLo !== aHi
                      ? `Beror på hur ordinarie tid slutade i ${live.alive_unproven?.join(', ')}. Svenska Spel har inte publicerat den än.`
                      : undefined}>{aliveText}</td>
                    <td className={(p ?? lo) >= 0.5 ? 'pos' : ''}
                      title={p == null && lo != null
                        ? 'Intervall: chansen beroende på hur de oprissatta matcherna går. Ingen sannolikhet gissas åt dem.'
                        : undefined}>{text}</td>
                    {live.forecast && <td>{live.forecast.levels?.[lvl] ? kr(live.forecast.levels[lvl].pot_kr) : '–'}</td>}
                    {live.forecast && <td title={live.forecast.levels?.[lvl]
                      ? `förväntat ${live.forecast.levels[lvl].expected_winners} vinnande rader i fältet` : undefined}>
                      {live.forecast.levels?.[lvl] ? <b>≈ {kr(live.forecast.levels[lvl].per_row_kr)}</b> : '–'}</td>}
                  </tr>
                )
              })}
            </tbody>
          </table>}
          {live.forecast && !live.out_of_contention && (
            <p className="hint">Prognosen per rad är vår egen skattning om omgången slutar som nu
              ({forecastBasisText(live.forecast)}), inte Svenska Spels siffra — den kommer först
              när omgången är rättad.</p>
          )}
          {!live.out_of_contention && <AliveRowsTable live={live} />}
          <p className="hint">
            {live.chance_note ? `Ingen chans visas: ${live.chance_note}.`
              : live.chance_unpriced?.length
                ? <>Chansen visas som <b>intervall</b>: {live.chance_unpriced.join(', ')} saknar
                  öppet pris, så siffran ges för alla utfall den matchen kan få —
                  <b> underkanten förutsätter att den går emot dina rader</b>, även
                  när ställningen säger annat. Ingen sannolikhet gissas åt den;
                  bedöm ställningen själv.</>
              : <>
                {live.chance_basis === 'simulerad'
                  ? 'Chans simulerad ur oddsen på kvarvarande matcher (för många kombinationer för exakt uppräkning).'
                  : 'Chans räknad exakt ur oddsen på kvarvarande matcher.'}
                {live.chance_live_matches > 0 && <> <b>{live.chance_live_matches} pågående
                  {live.chance_live_matches === 1 ? ' match' : ' matcher'} prissatta live</b> —
                  ställningen är alltså inräknad
                  {liveSourceText && <> ({liveSourceText})</>}.</>}
                {/* Modellskattningen är inget marknadspris och får aldrig läsas
                    som ett. Den syns bara på kupongen, aldrig i värde/CLV. */}
                {live.chance_modelled_matches > 0 && <> <b>{live.chance_modelled_matches}</b>
                  {live.chance_modelled_matches === 1 ? ' match saknar' : ' matcher saknar'} öppen
                  livemarknad och är <b>skattad</b> ur ställning och tid kvar, ankrad i
                  spelbolagets prematchpris. Det är en uppskattning — inget marknadspris —
                  och den påverkar aldrig värdespel eller facit.</>}
              </>}
          </p>
        </>
      )}
    </div>
  )
}

/* Ett avgjort systems exakta rader mot settlementkanonens facit. Hämtas
   först när användaren öppnar kupongen: 5 000-raderstester ska inte göra den
   vanliga Historik-vyn tung. */
function PlayedCouponDetail({ coupon, onClose, onForget = null }) {
  const [detail, setDetail] = useState(null)
  const [error, setError] = useState(null)
  const [showAll, setShowAll] = useState(false)
  useEffect(() => {
    const controller = new AbortController()
    fetch(`/api/pool/played/${coupon.id}`, {
      cache: 'no-store', signal: controller.signal,
    }).then(async (response) => {
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      return response.json()
    }).then(setDetail).catch((reason) => {
      if (reason?.name !== 'AbortError') setError(reason?.message || 'Okänt fel')
    })
    return () => controller.abort()
  }, [coupon.id])
  useEffect(() => {
    const closeOnEscape = (event) => { if (event.key === 'Escape') onClose() }
    window.addEventListener('keydown', closeOnEscape)
    return () => window.removeEventListener('keydown', closeOnEscape)
  }, [onClose])

  const events = detail?.events || []
  const rows = detail?.rows || []
  const shownRows = showAll ? rows : rows.slice(0, 30)
  const distribution = Object.entries(detail?.correct_dist || {})
    .map(([correct, count]) => [Number(correct), Number(count)])
    .sort((a, b) => b[0] - a[0])
  const eventName = (event) => [event.home, event.away].filter(Boolean).join(' – ')
    || event.description
    || `Match ${event.column}`
  return (
    <div className="played-detail-backdrop" onMouseDown={onClose}>
      <section className="played-detail" role="dialog" aria-modal="true"
        aria-labelledby="played-detail-title" onMouseDown={(event) => event.stopPropagation()}>
        <header className="played-detail-head">
          <div>
            <span>{coupon.settled_at ? 'Din rättade kupong' : 'Din pågående kupong'}</span>
            <h3 id="played-detail-title">{couponTitle(coupon)}</h3>
            <p>{couponDate(coupon)} · {coupon.n_rows} rader · {kr(coupon.cost_kr)}</p>
          </div>
          <button onClick={onClose} aria-label="Tillbaka till listan">← Tillbaka</button>
        </header>
        {!coupon.settled_at && <PlayedLiveCard c={coupon} onForget={onForget} />}
        {error && <ErrorState message={`Kupongen kunde inte hämtas: ${error}`} />}
        {!detail && !error && <LoadingState label="Hämtar rader och facit…" />}
        {detail && (
          <div className="played-detail-body">
            {coupon.settled_at && <div className="played-detail-kpis">
              <span><b>{coupon.correct_max}</b> bäst rätt</span>
              <span><b>{coupon.payout_complete ? kr(coupon.payout_kr) : 'ofullständigt'}</b> utdelning</span>
              <span><b className={coupon.roi == null ? '' : coupon.roi >= 0 ? 'pos' : 'neg'}>
                {coupon.roi == null ? '–' : `${coupon.roi >= 0 ? '+' : ''}${Math.round(coupon.roi * 100)} %`}
              </b> ROI</span>
            </div>}
            {!detail.audit_matches_stored && (
              <p className="played-detail-warning">Varning: den omräknade
                radfördelningen avviker från det sparade facitet.</p>
            )}
            <section>
              <h4>{coupon.settled_at ? 'Officiellt facit, match för match' : 'Kupongen match för match'}</h4>
              <CouponOverview nRows={rows.length} showMarket={false}
                events={events.map((event, index) => ({ ...event,
                  event_number: event.column,
                  covered: ['1', 'X', '2'].filter(sign => rows.some(row => row.signs[index] === sign)),
                }))} />
            </section>
            <section>
              <h4>Så fördelades raderna</h4>
              <div className="played-dist">
                {distribution.map(([correct, count]) => (
                  <span key={correct}><b>{count}</b> {count === 1 ? 'rad' : 'rader'} med {correct} rätt</span>
                ))}
              </div>
            </section>
            <section>
              <div className="played-rows-head">
                <div><h4>Raderna, bäst först</h4>
                  <p>Grönt tecken är rätt, rött är fel. # är radens plats i den sparade filen.</p></div>
                <b>{showAll ? rows.length : Math.min(30, rows.length)} av {rows.length}</b>
              </div>
              <div className="played-row-results">
                {shownRows.map((row) => (
                  <div className={`played-row-result${row.payout_kr > 0 ? ' prize' : ''}`}
                    key={row.index}>
                    <span className="played-row-number">#{row.index}</span>
                    <div className="played-row-signs"
                      style={{ '--played-cols': Math.max(1, events.length) }}>
                      {[...row.signs].map((sign, index) => {
                        const outcome = events[index]?.outcome
                        return <span key={index}
                          className={!outcome ? '' : sign === outcome ? 'hit' : 'miss'}
                          title={`${eventName(events[index] || { column: index + 1 })}: ${sign}, facit ${outcome || '?'}`}>
                          {sign}
                        </span>
                      })}
                    </div>
                    <b>{row.correct == null ? '–' : `${row.correct}/${events.length}`}</b>
                    {row.payout_kr > 0
                      ? <em>+{kr(row.payout_kr)}</em>
                      : row.prize_level && row.payout_kr == null
                        ? <em>belopp saknas</em> : null}
                  </div>
                ))}
              </div>
              {rows.length > 30 && (
                <button className="played-show-all" onClick={() => setShowAll((value) => !value)}>
                  {showAll ? 'Visa bara de 30 bästa' : `Visa samtliga ${rows.length} rader`}
                </button>
              )}
            </section>
          </div>
        )}
      </section>
    </div>
  )
}

function PlayedFileImport({ onImported }) {
  const [savedFile, setSavedFile] = useState(null)
  const [manualProduct, setManualProduct] = useState('')
  const [manualDraw, setManualDraw] = useState('')
  const [preview, setPreview] = useState(null)
  const [checkedPayload, setCheckedPayload] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const inputRef = useRef(null)
  const inspectRef = useRef(0)

  const changeOverride = (setter, value) => {
    ++inspectRef.current
    setter(value); setBusy(false); setPreview(null); setCheckedPayload(null)
    setError(''); setMessage('')
  }

  const payload = (file = savedFile) => ({
    filename: file?.name || '', text: file?.text || '',
    product: manualProduct || undefined,
    draw_number: manualDraw || undefined,
  })
  const inspect = async (file = savedFile, requestId = null) => {
    if (!file) return
    const id = requestId ?? ++inspectRef.current
    const checked = payload(file)
    setBusy(true); setError(''); setMessage(''); setPreview(null); setCheckedPayload(null)
    try {
      const response = await fetch('/api/pool/played/import/preview', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(checked),
      })
      const result = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(result.detail || `HTTP ${response.status}`)
      if (inspectRef.current === id) {
        setCheckedPayload(checked)
        setPreview(result.preview)
      }
    } catch (caught) {
      if (inspectRef.current === id) {
        setError(caught.message || 'Filen kunde inte kontrolleras')
      }
    } finally {
      if (inspectRef.current === id) setBusy(false)
    }
  }
  const chooseFile = async (event) => {
    const file = event.target.files?.[0]
    if (!file) return
    const requestId = ++inspectRef.current
    setBusy(true); setError(''); setMessage(''); setPreview(null); setCheckedPayload(null)
    try {
      const saved = { name: file.name, text: await file.text() }
      if (inspectRef.current !== requestId) return
      setSavedFile(saved)
      await inspect(saved, requestId)
    } catch {
      if (inspectRef.current === requestId) {
        setBusy(false)
        setError('Filen kunde inte läsas på den här enheten')
      }
    }
  }
  const confirm = async () => {
    if (!checkedPayload || !preview || preview.duplicate) return
    setBusy(true); setError(''); setMessage('')
    try {
      const response = await fetch('/api/pool/played/import', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(checkedPayload),
      })
      const result = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(result.detail || `HTTP ${response.status}`)
      setMessage(result.created
        ? `✓ ${preview.n_rows.toLocaleString('sv-SE')} rader bokförda och följs nu.`
        : 'Kupongen var redan bokförd.')
      setPreview(null); setCheckedPayload(null); setSavedFile(null)
      if (inputRef.current) inputRef.current.value = ''
      onImported?.()
    } catch (caught) {
      setError(caught.message || 'Kupongen kunde inte bokföras')
    } finally { setBusy(false) }
  }

  return (
    <section className="played-import">
      <div className="played-import-head">
        <div><b>Glömde du ”Spelad kupong”?</b>
          <span>Läs in den sparade Egna rader-filen och bokför spelet i efterhand.</span></div>
        <label className="played-import-file">
          <span>{busy ? 'Kontrollerar…' : 'Välj radfil'}</span>
          <input ref={inputRef} type="file" accept=".txt,text/plain"
            disabled={busy} onChange={chooseFile} />
        </label>
      </div>
      <p className="hint">Filen läses och kontrolleras här, men skickas aldrig till
        Svenska Spel och lägger inget nytt spel. Bekräfta bara kuponger du faktiskt betalade.</p>
      <details className="played-import-manual">
        <summary>Har filen döpts om och saknar omgång?</summary>
        <div>
          <label>Spel<select value={manualProduct}
            onChange={(event) => changeOverride(setManualProduct, event.target.value)}>
            <option value="">Läs från filen</option>
            <option value="stryktipset">Stryktipset</option>
            <option value="europatipset">Europatipset</option>
            <option value="topptipset">Topptipset · Dagens</option>
            <option value="topptipsetstryk">Topptipset · Stryk</option>
            <option value="topptipsetextra">Topptipset · Extra</option>
          </select></label>
          <label>Omgång<input type="number" min="1" inputMode="numeric"
            value={manualDraw} placeholder="t.ex. 4968"
            onChange={(event) => changeOverride(setManualDraw, event.target.value)} /></label>
          <button disabled={!savedFile || busy} onClick={() => inspect()}>
            Kontrollera igen</button>
        </div>
      </details>
      {error && <div className="played-import-status bad">⚠️ {error}</div>}
      {message && <div className="played-import-status good">{message}</div>}
      {preview && (
        <div className="played-import-preview">
          <div><b>{PRODUCT_LABEL[preview.product] || preview.product} · omgång {preview.draw_number}</b>
            <span>{preview.n_rows.toLocaleString('sv-SE')} rader · {preview.n_events} matcher
              {' · '}{kr(preview.cost_kr)}</span></div>
          {!preview.draw_known && <span className="played-import-warn">Omgången finns inte
            lokalt ännu. Den börjar samlas in och följas efter bokföringen.</span>}
          {preview.duplicate
            ? <span className="played-import-ok">✓ Exakt den här kupongen är redan bokförd.</span>
            : <button disabled={busy} onClick={confirm}>Bokför och följ kupongen</button>}
        </div>
      )}
    </section>
  )
}

export { couponLabel, couponDate, couponKindLabel, couponTitle, LiveScorecard, AliveRowsTable, PlayedLiveCard, PlayedCouponDetail, PlayedFileImport }
