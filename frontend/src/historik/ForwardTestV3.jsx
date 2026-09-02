// 5 000-test och Max-tester (research-only forwardserier).
// Bruten ur AppV3.jsx 2026-09-02.
import { useEffect, useState } from 'react'
import { get } from '../lib/api.js'
import { PRODUCT_LABEL, fmtDay, horizonLabel, pctSigned, roiCls, FORWARD_TEST, forwardTestLabel, forwardTestFilterKey } from '../lib/labels.js'
import { SystemDetail } from '../historik/SystemDetail.jsx'
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
  const [filters, setFilters] = useState({ product: 'alla', horizon: 'alla', method: 'alla' })
  useEffect(() => {
    let current = true
    get(meta.endpoint)
      .then((value) => { if (current) setData(value) })
      .catch((reason) => { if (current) setError(String(reason)) })
    return () => { current = false }
  }, [meta.endpoint])
  useEffect(() => {
    if (!openSystem) return undefined
    const frame = window.requestAnimationFrame(() => {
      document.getElementById('hist-system-detail')?.scrollIntoView({
        behavior: 'smooth', block: 'start',
      })
    })
    return () => window.cancelAnimationFrame(frame)
  }, [openSystem])
  if (error) return <ErrorState message={error} />
  if (!data) return <LoadingState label={meta.loading} />

  const tests = (data.tests || []).filter((test) => (
    (filters.product === 'alla' || test.product === filters.product)
    && (filters.horizon === 'alla' || test.horizon === filters.horizon)
    && (filters.method === 'alla' || forwardTestFilterKey(test) === filters.method)
  ))
  const summary = data.summary || {}
  const setFilter = (key, value) => setFilters((current) => ({ ...current, [key]: value }))
  const methodSource = (data.tests || []).length ? data.tests : data.configs || []
  const methods = [...new Map(methodSource.map((test) => [
    forwardTestFilterKey(test), forwardTestLabel(test),
  ])).entries()]
  const retiredCount = (data.tests || []).filter((test) => test.retired).length
  const starts = Object.entries(data.start_draws || {}).map(([product, draw]) => (
    `${PRODUCT_LABEL[product] || product} #${draw}`)).join(' · ')

  return (
    <div className="v3ph5">
      <section className={`v3hero v3ph5hero ${isMaxTest ? 'v3max40hero' : ''}`}>
        <div>
          <span className="v3eyebrow">{meta.archived ? 'HISTORISK PILOT · INGA RIKTIGA INSATSER'
            : 'FRAMÅTRIKTAT BLINDTEST · INGA RIKTIGA INSATSER'}</span>
          <h1>{meta.title}</h1>
          <p>Här går varje automatisk testkupong att öppna exakt som den frystes
            före spelstopp — samtliga {meta.rowLabel} rader, odds, streck, teckenvikt och
            liverättning medan omgången pågår samt slutligt facit på samma ställe.</p>
        </div>
      </section>

      <div className="v3ph5kpis">
        <div><span>Omgångar</span><b>{meta.archived
          ? summary.all_draws || 0 : summary.draws || 0}</b></div>
        <div><span>{meta.archived ? 'Sparade pilotkuponger' : 'Aktiva testkuponger'}</span>
          <b>{meta.archived ? summary.all_freezes || 0 : summary.freezes || 0}</b></div>
        <div><span>{meta.archived ? 'Facitklara' : 'Facitklara aktiva'}</span>
          <b>{meta.archived ? summary.all_evaluated || 0 : summary.evaluated || 0}</b></div>
        <div><span>{meta.archived ? 'Status'
          : meta.paired ? 'Kompletta jämförelsepar' : 'Aktiva metoder'}</span>
          <b>{meta.archived ? 'Avslutad'
            : meta.paired ? summary.paired_freezes || 0 : summary.methods || 0}</b></div>
      </div>

      <div className="v3card v3ph5explain">
        <div className="v3cardhead"><h3>Så ska testet läsas</h3></div>
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
            tjugo minuter före stopp. Det gör jämförelsen rättvis. Resultatet är
            kontrafaktiskt: systemet lämnades aldrig in, så kronor och ROI visar
            vad testet uppskattas ha gett — inte pengar som vunnits eller förlorats.</p>
          <div className="v3ph5methods">
            <span><b>Värderader</b> appens balanserade modell</span>
            <span><b>Max-EV</b> prioriterar värde hårdast</span>
            <span><b>Favoritrad</b> marknadens sannolikaste tecken</span>
            <span><b>Byggarslump</b> slumpkontroll ur samma kandidater</span>
          </div>
        </>}
      </div>

      {isMaxTest ? <div className="v3card v3ph5xnote">
        <div className="v3cardhead"><h3>Vad ”max” betyder här</h3></div>
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
            Genomsnittlig exakt radöverlapp hittills: <b>{summary.average_overlap == null
              ? 'väntar på första kompletta par'
              : `${Math.round(summary.average_overlap * 100)} %`}</b>.</>}</p>
      </div> : <div className="v3card v3ph5xnote">
        <div className="v3cardhead"><h3>Är X systematiskt underviktat?</h3></div>
        <p>Det är en rimlig misstanke, särskilt när ett binärt 1–2-hörn väljs.
          Vi ändrar inte den pågående PH5-v3-kohorten i efterhand. I stället
          mäter sidan nu X-andelen i varje kupong och markerar varje match där
          X saknas helt eller får mindre än 10 procent av raderna.</p>
        <p><b>Appens Värderader hittills:</b> X har saknats i{' '}
          {summary.model_x_omitted_events || 0} frysta matchbeslut. Av{' '}
          {summary.model_x_outcomes || 0} observerade X-facit saknades X helt i{' '}
          <span className={summary.model_x_outcomes_omitted ? 'v3neg' : 'v3pos'}>
            {summary.model_x_outcomes_omitted || 0}</span>. Samma match kan
          räknas vid både tre timmar och tjugo minuter; detta är diagnostik,
          ännu inget statistiskt modellbeslut. Kontrollerna visas separat i
          tabellen och blandas inte in i den här siffran.</p>
      </div>}

      <div className="v3card">
        <div className="v3cardhead"><h3>Alla frysta {meta.rowLabel}-kuponger</h3>
          <span className="v3hint">{tests.length} av {(data.tests || []).length}
            {retiredCount ? ` · ${retiredCount} avslutade` : ''}</span></div>
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
        </div>

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
          : <div className="v3histtablewrap"><table className="v3histtable v3ph5table">
              <thead><tr><th>Datum</th><th>Spel</th><th>Omgång</th><th>Fryst</th>
                <th>{meta.filterLabel}</th><th>Facit</th><th>X-vikt</th>
                {meta.paired && <th>Paröverlapp</th>}<th>Kupong</th></tr></thead>
              <tbody>{tests.map((test) => (
                <tr key={`${test.product}:${test.draw_number}:${test.horizon}:${test.config_key}`}
                  className={test.retired ? 'v3retired' : ''}>
                  <td>{test.close ? fmtDay(test.close) : fmtDay(test.frozen_at)}</td>
                  <td>{PRODUCT_LABEL[test.product] || test.product}</td>
                  <td>#{test.draw_number}</td>
                  <td>{horizonLabel(test)}{test.timely ? '' : ' · sen'}</td>
                  <td>{forwardTestLabel(test)}</td>
                  <td>{test.correct_max == null ? 'Öppna för liverättning'
                    : test.payout_complete === false
                      ? `${test.correct_max} rätt · utdelning okänd`
                      : <><b>{test.correct_max} rätt</b> · {kr(test.payout_kr)} ·{' '}
                          <span className={roiCls(test.roi)}>{pctSigned(test.roi)}</span></>}</td>
                  <td className={test.x_outcomes_omitted ? 'v3neg' : ''}>
                    {test.x_share == null ? '–' : `${Math.round(test.x_share * 100)} %`}
                    {test.x_omitted_events ? ` · saknas i ${test.x_omitted_events}` : ''}</td>
                  {meta.paired && <td>{test.paired_overlap == null ? 'Väntar par'
                    : <>{Math.round(test.paired_overlap * 100)} %
                      {test.unique_rows != null && ` · ${test.unique_rows.toLocaleString('sv-SE')} unika`}</>}</td>}
                  <td><button className="v3more" onClick={() => setOpenSystem(test)}>
                    Visa exakt kupong</button></td>
                </tr>
              ))}</tbody>
            </table></div>}
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
      <button className={family === 'max40' ? 'on' : ''}
        onClick={() => setFamily('max40')}>40 000-pilot · avslutad</button>
    </div>
    <ForwardTestV3 family={family} />
  </div>
}
