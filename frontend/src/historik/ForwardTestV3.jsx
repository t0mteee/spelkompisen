// Researchserierna (5 000-test, maxtester, poolopt, 40 000-pilot): EN rad är
// EN exakt fryst kupong. Monteras i Historik → Tester. Bruten ur AppV3.jsx
// 2026-09-02; omgångsvy som standard och ruttstyrd detalj 2026-09-13.
import { useEffect, useState } from 'react'
import { get } from '../lib/api.js'
import { PRODUCT_LABEL, fmtDay, horizonLabel, pctSigned, roiCls, FORWARD_TEST, forwardTestLabel, forwardTestFilterKey, ROI_MIN_N } from '../lib/labels.js'
import { SystemDetail } from './SystemDetail.jsx'
import { SortableTable } from '../components/SortableTable.jsx'
import { forwardView } from '../lib/forwardTests.js'
import { FORECAST_NOTE, perRowText, minPayoutNote } from '../lib/forecast.js'
import { LoadingState, EmptyState, ErrorState, kr } from '../App.jsx'

const VIEW_KEY = 'svs_forward_view'
const VIEWS = ['omgangar', 'kuponger', 'metoder']
const readView = () => {
  try { const v = localStorage.getItem(VIEW_KEY); return VIEWS.includes(v) ? v : 'omgangar' } catch { return 'omgangar' }
}

export function ForwardTestV3({ family, open = null, onOpenCoupon = null, onCloseCoupon = null }) {
  const meta = FORWARD_TEST[family]
  const isMaxTest = family !== 'ph5'
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  // Öppen kupong: rutten styr när föräldern skickar `open`, annars lokalt.
  const [localOpen, setLocalOpen] = useState(null)
  const openSystem = open || localOpen
  const openCoupon = (test) => { setLocalOpen(test); onOpenCoupon?.(test) }
  const closeCoupon = () => { setLocalOpen(null); onCloseCoupon?.() }
  const [filters, setFilters] = useState({ product: 'alla', horizon: 'alla', method: 'alla',
    version: meta.archived ? 'aldre' : 'aktuell' })
  const [mode, setMode] = useState(readView)
  const [limit, setLimit] = useState(20)
  useEffect(() => {
    let current = true
    get(meta.endpoint)
      .then((value) => { if (current) setData(value) })
      .catch((reason) => { if (current) setError(String(reason)) })
    return () => { current = false }
  }, [meta.endpoint])
  // Liveläge för alla öppna testkuponger i listan, utan att öppna dem:
  // en hämtning per familj var 30:e sekund medan fliken är synlig, samma
  // livebild som detaljkortet. Försvinner en kupong ur livesvaret har
  // settlementjobbet rättat den — då hämtas översikten om en gång.
  const [live, setLive] = useState(null)
  const [liveErr, setLiveErr] = useState(null)
  const openCount = (data?.tests || []).filter((test) => test.correct_max == null).length
  useEffect(() => {
    if (!openCount || meta.archived) return undefined
    let current = true
    let pending = false
    let controller = null
    const refresh = () => {
      if (!current || pending || document.visibilityState === 'hidden') return
      pending = true
      controller = new AbortController()
      get(`/api/pool/systems/live-overview?family=${family}`, { signal: controller.signal })
        .then((value) => {
          if (!current) return
          setLive(value)
          setLiveErr(null)
          if ((value.tests || []).length < openCount) {
            get(meta.endpoint).then((fresh) => { if (current) setData(fresh) }).catch(() => {})
          }
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
  }, [family, openCount, meta.archived, meta.endpoint])
  if (error) return <ErrorState message={error} />
  if (!data) return <LoadingState label={meta.loading} />

  const view = forwardView(data, filters)
  const { tests, groups } = view
  const setFilter = (key, value) => {
    setFilters((current) => ({ ...current, [key]: value }))
    setLimit(20)
  }
  const chooseMode = (next) => {
    setMode(next); setLimit(20)
    try { localStorage.setItem(VIEW_KEY, next) } catch { /* ok */ }
  }
  const methodSource = (data.tests || []).length ? data.tests : data.configs || []
  const methods = [...new Map(methodSource.map((test) => [
    forwardTestFilterKey(test), forwardTestLabel(test),
  ])).entries()]
  const retiredCount = (data.tests || []).filter((test) => test.retired).length
  const starts = Object.entries(data.start_draws || {}).map(([product, draw]) => (
    `${PRODUCT_LABEL[product] || product} #${draw}`)).join(' · ')
  const liveEntries = Object.fromEntries((live?.tests || []).map((test) => [
    `${test.product}:${test.draw_number}:${test.horizon}:${test.config_key}`, test]))
  const liveErrors = live?.errors || {}
  const testKey = (test) => `${test.product}:${test.draw_number}:${test.horizon}:${test.config_key}`
  const facitCell = (test) => (test.correct_max == null
    ? <LiveCell entry={liveEntries[testKey(test)]}
        pot={live?.pots?.[`${test.product}:${test.draw_number}`]}
        forecast={live?.forecasts?.[`${test.product}:${test.draw_number}`]}
        error={liveErr || liveErrors[`${test.product}:${test.draw_number}`]}
        waiting={!live && !meta.archived} />
    : test.payout_complete !== true
      ? `${test.correct_max} rätt · utdelning okänd`
      : <><b>{test.correct_max} rätt</b> · {kr(test.payout_kr)} ·{' '}
          <span className={roiCls(test.roi)}>{pctSigned(test.roi)}</span></>)
  // Omgångsvyn: datum, spel och omgång EN gång, därefter en kompakt rad per
  // metod × frystid. Flera metoder på samma omgång är inte oberoende försök.
  const drawGroups = (() => {
    const map = new Map()
    for (const test of tests) {
      const key = `${test.product}:${test.draw_number}`
      if (!map.has(key)) {
        map.set(key, { key, product: test.product, draw_number: test.draw_number,
          close: test.close || test.frozen_at, tests: [] })
      }
      map.get(key).tests.push(test)
    }
    return [...map.values()].sort((a, b) => new Date(b.close || 0) - new Date(a.close || 0))
  })()
  const shownGroups = drawGroups.slice(0, limit)
  const columns = [
    { key: 'date', label: 'Datum', value: (test) => test.close || test.frozen_at },
    { key: 'product', label: 'Spel', value: (test) => PRODUCT_LABEL[test.product] || test.product },
    { key: 'draw_number', label: 'Omgång' },
    { key: 'horizon_minutes', label: 'Fryst' },
    { key: 'method', label: meta.filterLabel, value: forwardTestLabel },
    { key: 'correct_max', label: 'Facit' },
    ...(meta.paired ? [{ key: 'paired_overlap', label: 'Paröverlapp' }] : []),
    { key: 'coupon', label: 'Kupong', sortable: false },
  ]

  return (
    <div className="v3ph5">
      <details className="v3card v3ph5explain">
        <summary>Så fungerar testet och metoderna</summary>
        {isMaxTest ? <>
          <p>Två modellarmar får exakt samma {meta.rowLabel}-radersbudget, marknadsdata
            och frysningstid. <b>EV medel</b> balanserar sannolikhet och värde;
            <b> EV högt</b> pressar urvalet hårdare mot värde och skrällutdelning.
            Skillnaden i facit kan då kopplas till armvalet, inte till en annan
            omgång eller ett senare odds. {meta.archived
              ? 'Piloten fryser inga nya kuponger.' : ''}</p>
          <div className="v3ph5methods v3max40methods">
            <span><b>EV medel</b> medelstrategi · 50 % värdevikt</span>
            <span><b>EV högt</b> tuff strategi · 80 % värdevikt</span>
          </div>
        </> : <>
          <p>Fyra olika metoder får samma budget och fryses både tre timmar och
            tjugo minuter före stopp. Jämför metoder inom samma omgång och frystid; tiderna är inte oberoende försök. Resultatet är
            kontrafaktiskt: systemet lämnades aldrig in, så kronor och ROI visar
            vad testet uppskattas ha gett — inte pengar som vunnits eller förlorats.</p>
          <div className="v3ph5methods">
            <span><b>Värderader</b> appens balanserade modell</span>
            <span><b>Max-EV</b> prioriterar värde hårdast</span>
            <span><b>Favoritrad</b> marknadens sannolikaste tecken</span>
            <span><b>Slumpurval</b> samma tillåtna tecken som Värderader, men raderna lottas utan EV-rankning</span>
          </div>
        </>}
        {isMaxTest && <>
          {family === 'mathmax' ? <p>Detta är ett äkta matematiskt M-system:
            <b> 3 spikar × 1 halvgardering × 9 helgarderingar = 39 366 unika rader</b>.
            Alla kombinationer av de valda tecknen ingår; inget radurval reduceras bort.</p>
            : family === 'reducedmax' ? <p>Detta är det största reducerade test som passar
              vår faktiska externa radväg: <b>20 000 rader, alltså 20 000 kr totalt</b>.
              Testet lämnar aldrig in något automatiskt.</p>
              : family === 'max40' ? <p>40 000-piloten rankade 40 000 enskilda rader ur hela
                3¹³-rummet och var alltså reducerad till sin konstruktion. Den avslutades när
                de officiella leveransgränserna verifierades.</p> : null}
          <p><b>{meta.archived ? 'Historisk start' : 'Start utan bakfyllning'}:</b>{' '}
            {starts || '–'}. {meta.archived ? 'Inga nya frysningar görs.' : 'Armarna fryses tre timmar och tjugo minuter före stopp.'}</p>
        </>}
      </details>

      <div className="v3card">
        <div className="v3cardhead"><h3>Testkuponger</h3>
          <span className="v3hint">Filtren styr både listan och summeringen.
            {retiredCount ? ` ${retiredCount} kuponger från äldre testversioner finns i arkivet.` : ''}</span></div>
        <div className="v3groupfilters" aria-label={`Filtrera ${meta.rowLabel}-tester`}>
          <label><span>Spel</span><select value={filters.product}
            onChange={(event) => setFilter('product', event.target.value)}>
            <option value="alla">Alla spel</option>
            {(data.products || []).map((product) => <option key={product} value={product}>
              {PRODUCT_LABEL[product] || product}</option>)}
          </select></label>
          <label><span>Fryst</span><select value={filters.horizon}
            onChange={(event) => setFilter('horizon', event.target.value)}>
            <option value="alla">Båda tiderna</option>
            <option value="h3">3 timmar före</option>
            <option value="m20">20 minuter före</option>
          </select></label>
          <label><span>{meta.filterLabel}</span><select value={filters.method}
            onChange={(event) => setFilter('method', event.target.value)}>
            <option value="alla">Alla {isMaxTest ? 'armar' : 'metoder'}</option>
            {methods.map(([key, label]) => <option key={key} value={key}>
              {label}</option>)}
          </select></label>
          <label><span>Testversion</span><select value={filters.version}
            onChange={(event) => setFilter('version', event.target.value)}>
            <option value="aktuell">Aktuell version</option>
            <option value="aldre">Äldre versioner (arkiv)</option>
            <option value="alla">Alla versioner</option>
          </select></label>
        </div>

        <div className="v3ph5kpis" aria-label="Summering för valda filter">
          <div><span>Omgångar</span><b>{view.draws}</b></div>
          <div><span>Testkuponger</span><b>{view.coupons}</b></div>
          <div><span>Med matchfacit</span><b>{view.facit}</b></div>
          <div><span>Med utvärderbart belopp</span><b>{view.evaluated}</b></div>
        </div>
        <div className="v3subnav v3viewtoggle" aria-label="Visning">
          {[['omgangar', 'Omgångar'], ['kuponger', 'Kuponger'],
            ['metoder', isMaxTest ? 'Jämför armar' : 'Jämför metoder']].map(([id, label]) => (
            <button key={id} className={mode === id ? 'on' : ''} onClick={() => chooseMode(id)}>{label}</button>
          ))}
        </div>

        {openSystem && <SystemDetail
          key={testKey(openSystem)}
          product={openSystem.product} draw={openSystem.draw_number}
          horizon={openSystem.horizon} config={openSystem.config_key}
          onClose={closeCoupon} />}

        {mode === 'metoder' && <GroupSummary groups={groups} isMaxTest={isMaxTest} />}
        {mode !== 'metoder' && !tests.length && (
          <EmptyState
            title={(data.tests || []).length ? 'Inga tester matchar filtren' : 'Väntar på första frysningen'}
            detail={(data.tests || []).length ? undefined
              : `Testet startar framåt: ${starts || 'nästa ofrysta omgång'}.`} />
        )}
        {mode === 'omgangar' && tests.length > 0 && <>
          <p className="v3hint">Visar {Math.min(limit, drawGroups.length)} av {drawGroups.length} omgångar.
            Flera metoder och frystider på samma omgång är inte oberoende försök.</p>
          {shownGroups.map((group) => (
            <section key={group.key} className="v3drawblock" aria-label={`${PRODUCT_LABEL[group.product] || group.product} ${group.draw_number}`}>
              <div className="v3drawblockhead">
                <b>{PRODUCT_LABEL[group.product] || group.product} #{group.draw_number}</b>
                <span className="v3hint">{fmtDay(group.close)}</span>
                {group.tests.some((test) => test.correct_max == null)
                  ? <span className="v3kstatus live">öppen</span>
                  : <span className="v3kstatus rattad">rättad</span>}
              </div>
              <div className="v3drawrows">
                {[...group.tests].sort((a, b) => ((b.horizon_minutes || 0) - (a.horizon_minutes || 0))
                  || forwardTestLabel(a).localeCompare(forwardTestLabel(b), 'sv')).map((test) => (
                  <div key={testKey(test)} className={`v3drawrow${test.retired ? ' v3retired' : ''}`}>
                    <span><b>{forwardTestLabel(test)}</b>{test.retired && <small title={test.config_key}> · äldre version</small>}</span>
                    <span>{horizonLabel(test)}{test.timely ? '' : ' · sen'}</span>
                    <span>{facitCell(test)}{meta.paired && test.paired_overlap != null
                      && <span className="v3hint"> · överlapp {Math.round(test.paired_overlap * 100)} %</span>}</span>
                    <button className="v3more" onClick={() => openCoupon(test)}>Kupong</button>
                  </div>
                ))}
              </div>
            </section>
          ))}
          {drawGroups.length > limit && <button className="v3more" onClick={() => setLimit((value) => value + 20)}>
            Visa 20 till</button>}
        </>}
        {mode === 'kuponger' && tests.length > 0 && <>
          <p className="v3hint">Visar {Math.min(limit, tests.length)} av {tests.length} kuponger.</p>
          <SortableTable id={`forward-${family}`} rows={tests} columns={columns}
            defaultSort={{ key: 'date', dir: 'desc' }} limit={limit}
            wrapperClassName="v3histtablewrap" className="v3histtable v3ph5table"
            renderRow={(test) => (
              <tr key={testKey(test)} className={test.retired ? 'v3retired' : ''}>
                <td>{test.close ? fmtDay(test.close) : fmtDay(test.frozen_at)}</td>
                <td>{PRODUCT_LABEL[test.product] || test.product}</td>
                <td>#{test.draw_number}</td>
                <td>{horizonLabel(test)}{test.timely ? '' : ' · sen'}</td>
                <td>{forwardTestLabel(test)}{test.retired && <small title={test.config_key}> · äldre testversion</small>}</td>
                <td>{facitCell(test)}</td>
                {meta.paired && <td><span className="v3mobilelabel">Överlapp med andra armen: </span>{test.paired_overlap == null ? 'Väntar par'
                  : <>{Math.round(test.paired_overlap * 100)} %
                    {test.unique_rows != null && ` · ${test.unique_rows.toLocaleString('sv-SE')} unika`}</>}</td>}
                <td><button className="v3more" onClick={() => openCoupon(test)}>Visa exakt kupong</button></td>
              </tr>
            )} />
          {tests.length > limit && <button className="v3more" onClick={() => setLimit((value) => value + 20)}>
            Visa 20 till</button>}
        </>}
      </div>
    </div>
  )
}

/* Liveläget för EN öppen testkupong i listan. Samma tal som detaljkortets
   liverättning: fastställda rätt, läget om det slutar som nu, max nåbart och
   hur många rader som fortfarande kan nå varje vinstnivå. Potten är
   omgångens pott per nivå — inte en utdelning; hur många som delar den vet
   ingen förrän SvS publicerat. */
function LiveCell({ entry, pot, forecast, error, waiting }) {
  if (!entry) {
    if (error) return <span className="v3hint" title={error}>liveläge otillgängligt · öppna kupongen</span>
    return <span className="v3hint">{waiting ? 'hämtar liveläge…' : 'Öppna för liverättning'}</span>
  }
  const living = Object.entries(entry.alive_per_level || {})
    .map(([level, count]) => [Number(level), Number(count)])
    .filter(([, count]) => count > 0)
    .sort((a, b) => b[0] - a[0])
  const top = living[0]
  const potKr = top ? pot?.per_level?.[top[0]] : null
  const perRow = top ? forecast?.levels?.[top[0]] : null
  const started = entry.n_decided > 0 || entry.current_known > 0
  return <div className="v3livecell">
    <div>
      <b>{entry.best_secure} fastställt</b>
      {entry.current_known > 0 && entry.current_best != null
        && <> · läge <b>{entry.current_best}</b>/{entry.current_known}</>}
      {' '}· max {entry.max_possible} · {entry.n_decided}/{entry.n_events} avgjorda
    </div>
    <div className="v3hint">{!started ? 'omgången har inte startat'
      : entry.out_of_contention ? 'ingen rad kan längre nå någon vinstnivå'
        : !living.length ? 'inga rader lever'
          : <>lever: {living.map(([level, count]) => `${level} rätt → ${count.toLocaleString('sv-SE')} rader`).join(' · ')}
            {potKr ? <> · pott {top[0]} rätt {kr(potKr)}</> : null}
            {perRow ? <> · <b>{perRowText(perRow)}/rad</b> <span title={minPayoutNote(forecast, perRow) || FORECAST_NOTE}>(prognos)</span></> : null}</>}</div>
  </div>
}

/* Backendens separata produkt-/konfigurationsgrupper, samma filter som
   listan. Belopp och träffar kommer oförändrade från backend. */
function GroupSummary({ groups, isMaxTest }) {
  if (!groups?.length) return <EmptyState title="Inga grupper matchar filtren" />
  const levels = groups[0].levels || []
  return <div className="v3groupsummarybox">
    <p className="v3hint">Jämför {isMaxTest ? 'armar' : 'metoder'} · valda filter · varje produkt och testversion separat.
      Belopp kräver tidsriktig frysning och komplett utdelning; träffar räknar bästa rad per kupong.
      ROI visas från {ROI_MIN_N} utvärderbara omgångar, vilket inte i sig är stöd för modellen.</p>
    <div className="v3histtablewrap"><table className="v3histtable v3groupsummary">
      <thead><tr><th>Kategori</th><th>Kuponger</th><th>Simulerad kostnad</th><th>Simulerat tillbaka</th><th>Simulerat saldo</th>
        {levels.map((level) => <th key={level}>{level} rätt</th>)}<th>ROI</th></tr></thead>
      <tbody>{groups.map((group) => <tr key={group.key}>
        <td title={group.config_key}><b>{forwardTestLabel(group)}</b> · {group.horizon_minutes != null ? `${group.horizon_minutes} min` : group.horizon}
          <br />{PRODUCT_LABEL[group.product] || group.product}{group.retired ? ' · äldre testversion' : ''}</td>
        <td>{group.n_facit} med matchfacit · {group.n_settled} med belopp
          {group.n_open ? ` · ${group.n_open} öppna` : ''}</td>
        <td>{kr(group.cost_kr)}</td>
        <td>{kr(group.payout_kr)}</td>
        <td className={roiCls(group.balance_kr)}>{group.balance_kr > 0 ? '+' : ''}{kr(group.balance_kr)}</td>
        {levels.map((level) => <td key={level}>{group.hits?.[level] || 0}</td>)}
        <td className={group.n_settled >= ROI_MIN_N ? roiCls(group.roi) : ''}>
          {group.n_settled < ROI_MIN_N ? `${group.n_settled}/${ROI_MIN_N} omgångar`
            : group.roi == null ? '–' : pctSigned(group.roi)}</td>
      </tr>)}</tbody></table></div>
  </div>
}
