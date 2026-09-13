// 5 000-test och Max-tester (research-only forwardserier).
// Bruten ur AppV3.jsx 2026-09-02.
import { useEffect, useState } from 'react'
import { get } from '../lib/api.js'
import { PRODUCT_LABEL, fmtDay, horizonLabel, pctSigned, roiCls, FORWARD_TEST, forwardTestLabel, forwardTestFilterKey, ROI_MIN_N } from '../lib/labels.js'
import { SystemDetail } from '../historik/SystemDetail.jsx'
import { SortableTable } from '../components/SortableTable.jsx'
import { forwardView } from '../lib/forwardTests.js'
import { LoadingState, EmptyState, ErrorState, kr } from '../App.jsx'

/* Researchserierna har egna uppgifter och ska därför inte ligga gömda bland
   Historiks hundratals benchmarkgrupper. En tabellrad är EN exakt fryst
   kupong. Själva raderna hämtas först när användaren öppnar testet. */
export function ForwardTestV3({ family }) {
  const meta = FORWARD_TEST[family]
  const isMaxTest = family !== 'ph5'
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [openSystem, setOpenSystem] = useState(null)
  const [filters, setFilters] = useState({ product: 'alla', horizon: 'alla', method: 'alla',
    version: meta.archived ? 'aldre' : 'aktuell' })
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
      <section className={`v3hero v3ph5hero ${isMaxTest ? 'v3max40hero' : ''}`}>
        <div>
          <span className="v3eyebrow">{meta.archived ? 'HISTORISK PILOT · INGA RIKTIGA INSATSER'
            : 'FRAMÅTRIKTAT BLINDTEST · INGA RIKTIGA INSATSER'}</span>
          <h1>{meta.title}</h1>
          <p>Följ kupongerna live eller öppna exakt radurval, sparade odds och slutresultat.
            Alla belopp är simulerade.</p>
        </div>
      </section>

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
      </details>

      {isMaxTest ? <details className="v3card v3ph5xnote">
        <summary>Systemstorlek och teststart</summary>
        {family === 'mathmax' ? <p>Detta är ett äkta matematiskt M-system:
          <b> 3 spikar × 1 halvgardering × 9 helgarderingar = 39 366 unika rader</b>.
          Alla kombinationer av de valda tecknen ingår; inget radurval reduceras bort.
          Det ska återskapas som M-system hos Svenska Spel, inte laddas upp som
          en enda extern E-radfil.</p> : family === 'reducedmax' ? <p>Detta är
          det största reducerade test som passar vår faktiska externa radväg:
          <b> 20 000 rader, alltså 20 000 kr totalt</b>. En manuell uppladdning måste delas i
          två separata E-filer med högst 10 000 rader i varje. Testet lämnar
          aldrig in något automatiskt.</p> : <p>40 000-piloten rankade 40 000
          enskilda rader ur hela 3¹³-rummet och var alltså reducerad till sin
          konstruktion. Den avslutades när de officiella leveransgränserna
          verifierades. Redan frysta kuponger ligger kvar för revision.</p>}
        <p><b>{meta.archived ? 'Historisk start' : 'Start utan bakfyllning'}:</b>{' '}
          {starts || '–'}. {meta.archived ? 'Inga nya frysningar görs.' : <>
            Båda armarna fryses tre timmar och tjugo minuter före stopp.
            Överlapp med andra armen visas per kupong i listan.</>}</p>
      </details> : null}

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
        <GroupSummary groups={groups} isMaxTest={isMaxTest} />
        <p className="v3hint">Visar {Math.min(limit, tests.length)} av {tests.length} kuponger.
          Flera metoder och frystider på samma omgång är inte oberoende försök.</p>

        {openSystem && <SystemDetail
          key={`${openSystem.product}:${openSystem.draw_number}:${openSystem.horizon}:${openSystem.config_key}`}
          product={openSystem.product} draw={openSystem.draw_number}
          horizon={openSystem.horizon} config={openSystem.config_key}
          onClose={() => setOpenSystem(null)} />}

        {!tests.length
          ? <EmptyState
              title={(data.tests || []).length
                ? "Inga tester matchar filtren"
                : "Väntar på första frysningen"}
              detail={(data.tests || []).length ? undefined
                : `Testet startar framåt: ${starts || 'nästa ofrysta omgång'}.`} />
          : <SortableTable id={`forward-${family}`} rows={tests} columns={columns}
              defaultSort={{ key: 'date', dir: 'desc' }} limit={limit}
              wrapperClassName="v3histtablewrap" className="v3histtable v3ph5table"
              renderRow={(test) => (
                <tr key={`${test.product}:${test.draw_number}:${test.horizon}:${test.config_key}`}
                  className={test.retired ? 'v3retired' : ''}>
                  <td>{test.close ? fmtDay(test.close) : fmtDay(test.frozen_at)}</td>
                  <td>{PRODUCT_LABEL[test.product] || test.product}</td>
                  <td>#{test.draw_number}</td>
                  <td>{horizonLabel(test)}{test.timely ? '' : ' · sen'}</td>
                  <td>{forwardTestLabel(test)}{test.retired && <small title={test.config_key}> · äldre testversion</small>}</td>
                  <td>{test.correct_max == null
                    ? <LiveCell
                        entry={liveEntries[`${test.product}:${test.draw_number}:${test.horizon}:${test.config_key}`]}
                        pot={live?.pots?.[`${test.product}:${test.draw_number}`]}
                        error={liveErr || liveErrors[`${test.product}:${test.draw_number}`]}
                        waiting={!live && !meta.archived} />
                    : test.payout_complete !== true
                      ? `${test.correct_max} rätt · utdelning okänd`
                      : <><b>{test.correct_max} rätt</b> · {kr(test.payout_kr)} ·{' '}
                          <span className={roiCls(test.roi)}>{pctSigned(test.roi)}</span></>}</td>
                  {meta.paired && <td><span className="v3mobilelabel">Överlapp med andra armen: </span>{test.paired_overlap == null ? 'Väntar par'
                    : <>{Math.round(test.paired_overlap * 100)} %
                      {test.unique_rows != null && ` · ${test.unique_rows.toLocaleString('sv-SE')} unika`}</>}</td>}
                  <td><button className="v3more" onClick={() => setOpenSystem(test)}>
                    Visa exakt kupong</button></td>
                </tr>
              )} />}
        {tests.length > limit && <button className="v3more" onClick={() => setLimit((value) => value + 20)}>
          Visa 20 till</button>}
      </div>

    </div>
  )
}
export function Ph5V3() { return <ForwardTestV3 family="ph5" /> }
export function MaxTestsV3() {
  const [family, setFamily] = useState('mathmax')
  return <div>
    <div className="v3subnav v3maxtabs" aria-label="Välj maxtest">
      <button className={family === 'mathmax' ? 'on' : ''}
        onClick={() => setFamily('mathmax')}>Matematiskt 39 366</button>
      <button className={family === 'reducedmax' ? 'on' : ''}
        onClick={() => setFamily('reducedmax')}>Reducerat 20 000</button>
    </div>
    <ForwardTestV3 key={family} family={family} />
  </div>
}

/* Liveläget för EN öppen testkupong i listan. Samma tal som detaljkortets
   liverättning: fastställda rätt, läget om det slutar som nu, max nåbart och
   hur många rader som fortfarande kan nå varje vinstnivå. Potten är
   omgångens pott per nivå — inte en utdelning; hur många som delar den vet
   ingen förrän SvS publicerat. */
function LiveCell({ entry, pot, error, waiting }) {
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
            {potKr ? <> · pott {top[0]} rätt ≈ {kr(potKr)} <span title="Omgångens pott per nivå ur senaste snapshot (omsättning × vinstplan, jackpot på toppnivån). Delas med alla vinnare — ingen prognos på utdelning per rad.">(delas)</span></> : null}</>}</div>
  </div>
}

/* Backendens separata produkt-/konfigurationsgrupper, samma filter som
   listan. Belopp och träffar kommer oförändrade från backend. */
function GroupSummary({ groups, isMaxTest }) {
  if (!groups?.length) return null
  const levels = groups[0].levels || []
  return <details className="v3ph5explain">
    <summary>Jämför {isMaxTest ? 'armar' : 'metoder'} · belopp och träffar</summary>
    <p className="v3hint">Valda filter · varje produkt och testversion separat.
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
  </details>
}
