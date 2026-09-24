// Historik → Facit & prognos: omgångsfakta ur settlementlagret (PH1) och
// omsättningsprognosen. 100 % pool (ytgränsen 2026-08-05). Egna kuponger bor
// i Mina kuponger, experiment i Tester (2026-09-13).
import { useEffect, useState } from 'react'
import { get } from '../lib/api.js'
import { PRODUCT_LABEL, HIST_FAMILIES, IS_FAMILY, fmtDay } from '../lib/labels.js'
import { MiniSpark } from '../components/badges.jsx'
import { LoadingState, EmptyState, ErrorState, kr } from '../App.jsx'

export function HistorikV3({ initialProduct, onChooseProduct = null }) {
  const [product, setProduct] = useState(initialProduct || 'alla')
  const [data, setData] = useState(null)
  const [err, setErr] = useState(null)
  const [expanded, setExpanded] = useState(null)
  const [detail, setDetail] = useState({})
  const [halsa, setHalsa] = useState(null)
  const [overview, setOverview] = useState(null)
  const [showAllDraws, setShowAllDraws] = useState(false)

  // ETT filter styr hela sidan: prognos och omsättning för valt spel.
  const single = product !== 'alla'
  const chooseProduct = (next) => {
    setProduct(next); setData(null); setErr(null); setExpanded(null)
    onChooseProduct?.(next === 'alla' ? null : next)
  }

  useEffect(() => {
    if (!single) return undefined
    let current = true
    get(`/api/pool/history?product=${product}&limit=400${IS_FAMILY(product) ? '&family=1' : ''}`)
      .then((value) => { if (current) setData(value) })
      .catch((e) => { if (current) setErr(String(e)) })
    return () => { current = false }
  }, [product, single])
  useEffect(() => {
    get('/api/pool/turnover-prognos').then(setHalsa).catch(() => setHalsa(null))
  }, [])
  useEffect(() => {
    Promise.all(HIST_FAMILIES.map((p) =>
      get(`/api/pool/history?product=${p.id}&limit=1${IS_FAMILY(p.id) ? '&family=1' : ''}`)
        .then((j) => [p.id, j]).catch(() => [p.id, null])))
      .then((pairs) => setOverview(Object.fromEntries(pairs)))
  }, [])

  const toggle = (n, rowProduct) => {
    const key = `${rowProduct || product}:${n}`
    const next = expanded === key ? null : key
    setExpanded(next)
    if (next != null && !detail[key]) {
      get(`/api/pool/history?product=${rowProduct || product}&draw=${n}`)
        .then((j) => setDetail((d) => ({ ...d, [key]: j })))
        .catch(() => { /* raden visar ändå nivåerna */ })
    }
  }
  const draws = data?.draws || []
  const shownDraws = showAllDraws ? draws : draws.slice(0, 20)
  const sparkVals = [...draws].reverse().map((d) => d.turnover)

  return (
    <div className="v3facit">
      <div className="v3histbar">
        <nav className="v3subnav" aria-label="Spel">
          <button className={product === 'alla' ? 'on' : ''}
            onClick={() => chooseProduct('alla')}>Alla spel</button>
          {HIST_FAMILIES.map((p) => (
            <button key={p.id} className={product === p.id ? 'on' : ''}
              onClick={() => chooseProduct(p.id)}>{p.label}</button>
          ))}
        </nav>
        <span className="v3hint">Filtret styr prognos och omsättning. Dina kuponger och
          testerna har egna flikar.</span>
      </div>

      {/* -------------------------- prognosträff -------------------------- */}
      {halsa && (
        <div className="v3card">
          <div className="v3cardhead"><h3>🧬 Prognosträff och κ-fönster</h3></div>
          <span className="v3hint">Slutomsättningen driver hela EV-räkningen, så
            prognosfelet hör hemma i poolens facit — det låg tidigare i Labb bland
            oddsmätningarna. Rullande backtest: medianabsolutfel, räknat enbart på
            data som fanns FÖRE respektive omgång (sann median). Prognosen väljer per
            spel det läge som har lägst fel: samma veckodag, samma dagtyp (vardag/helg)
            eller senaste sex oavsett dag.</span>
          <div className="v3histtablewrap">
            <table className="v3histtable">
              <thead><tr><th>Spel</th><th>Prognosfel (veckodag)</th>
                <th>Dagtyp</th>
                <th>Blandad</th>
                <th title="Avgjorda omgångar efter 2026-07-24. Krävs innan nya
                  κ-varianter får föreslås.">PH4-fönster</th>
                <th title="Omgångar med observerad jackpot vid spelstopp (senast
                  verifierade snapshot före stängning). Prognosen är jackpotblind
                  tills kravet är nått.">Jackpot vid stopp</th></tr></thead>
              <tbody>
                {Object.entries(halsa)
                  .filter(([p]) => !single || p === product)
                  .map(([p, h]) => (
                    <tr key={p}>
                      <td>{PRODUCT_LABEL[p] || p}</td>
                      <td>{h.medianfel_veckodag == null ? '–'
                        : `${(h.medianfel_veckodag * 100).toFixed(0)} %`}</td>
                      <td>{h.medianfel_dagtyp == null ? '–'
                        : `${(h.medianfel_dagtyp * 100).toFixed(0)} %`}</td>
                      <td>{h.medianfel_blandad == null ? '–'
                        : `${(h.medianfel_blandad * 100).toFixed(0)} %`}</td>
                      <td>{h.ph4_oot}/{h.ph4_oot_krav}</td>
                      <td>{h.jackpot_close_n ?? 0}/{h.jackpot_close_krav ?? '–'}</td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
          {Object.entries(halsa)
            .filter(([p, h]) => (!single || p === product) && (h.jackpot_rader || []).length > 0)
            .map(([p, h]) => (
              <div key={`jp-${p}`} className="v3histtablewrap">
                <span className="v3hint">{PRODUCT_LABEL[p] || p}: prognos mot utfall
                  i omgångar med jackpot vid stopp. Underlag för en jackpotdimension
                  i prognosen — ingen modell förrän {h.jackpot_close_krav} omgångar.</span>
                <table className="v3histtable">
                  <thead><tr><th>Stopp</th><th>Jackpot</th><th>Prognos</th>
                    <th>Utfall</th><th>Fel</th></tr></thead>
                  <tbody>
                    {h.jackpot_rader.map((r) => (
                      <tr key={r.close}>
                        <td>{String(r.close).slice(0, 10)}</td>
                        <td>{kr(r.jackpot_close)}</td>
                        <td>{r.prognos == null ? '–' : kr(r.prognos)}</td>
                        <td>{kr(r.net_sale)}</td>
                        <td className={r.fel == null ? 'v3hint' : (r.fel > 0 ? 'v3neg' : 'v3pos')}>
                          {r.fel == null ? '–' : `${r.fel > 0 ? '+' : ''}${(r.fel * 100).toFixed(0)} %`}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ))}
        </div>
      )}

      {/* --------------------- omsättning och utdelning -------------------- */}
      {!single && overview && (
        <div className="v3card">
          <div className="v3cardhead"><h3>💰 Omsättning och utdelning</h3></div>
          <span className="v3hint">Välj ett spel ovan för hela historiken.</span>
          <div className="v3histtablewrap">
            <table className="v3histtable">
              <thead><tr><th>Spel</th><th>Omgångar</th><th>Median toppvinst</th>
                <th>Utan toppvinnare</th><th>Medelomsättning</th></tr></thead>
              <tbody>
                {HIST_FAMILIES.map((p) => {
                  const o = overview[p.id]
                  return (
                    <tr key={p.id} className="v3histrowline" role="button" tabIndex={0}
                      onClick={() => chooseProduct(p.id)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                          e.preventDefault(); chooseProduct(p.id)
                        }
                      }}>
                      <td>{p.label}</td>
                      <td>{o?.total ?? '–'}</td>
                      <td>{o?.stats?.median_top_amount ? kr(o.stats.median_top_amount) : '–'}</td>
                      <td>{o?.stats?.rollover_rate != null
                        ? `${Math.round(100 * o.stats.rollover_rate)} %` : '–'}</td>
                      <td>{o?.stats?.mean_turnover ? kr(o.stats.mean_turnover) : '–'}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {single && (
        <div className="v3card">
          <div className="v3cardhead"><h3>💰 Omsättning och utdelning ·{' '}
            {PRODUCT_LABEL[product] || product}</h3></div>
          {err && <ErrorState message={err} />}
          {!data && !err && <LoadingState label="Hämtar historik…" />}
          {data && !data.available && (
            <EmptyState title="Inga settlade omgångar ännu för detta spel"
              detail="Backfillen fyller på bakåt och snapshot-varvet settlar nya omgångar löpande." />
          )}
          {data?.available && (
            <>
              <div className="v3histkpis">
                <div className="v3kpi"><b>{data.total}</b><span>omgångar</span></div>
                <div className="v3kpi"><b>{String(data.first_close || '').slice(0, 4)}–{String(data.last_close || '').slice(0, 4)}</b><span>tidsspann</span></div>
                <div className="v3kpi"><b>{data.stats?.median_top_amount ? kr(data.stats.median_top_amount) : '–'}</b><span>median toppvinst</span></div>
                <div className="v3kpi"><b>{data.stats?.rollover_rate != null ? Math.round(100 * data.stats.rollover_rate) : 0} %</b><span>utan toppvinnare</span></div>
                <div className="v3kpi"><b>{data.stats?.mean_turnover ? kr(data.stats.mean_turnover) : '–'}</b><span>medelomsättning</span></div>
              </div>
              {data.cancelled_count > 0 && (
                <span className="v3hint">{data.cancelled_count} inställda omgångar
                  finns kvar i arkivet men är exkluderade ur statistik och facit.</span>
              )}
              {sparkVals.filter(Boolean).length > 2 && (
                <div className="v3sparkbox">
                  <span className="v3hint">Omsättning, äldst → nyast ({draws.length} omgångar)</span>
                  <MiniSpark values={sparkVals} width={640} height={60} />
                </div>
              )}
              <div className="v3histtablewrap">
                <table className="v3histtable">
                  <thead><tr>
                    <th>Omg</th><th>Stängde</th><th>Omsättning</th>
                    <th>Toppnivå</th><th>Utdelning</th><th></th>
                  </tr></thead>
                  <tbody>
                    {shownDraws.map((d) => {
                      const top = d.tiers?.[0]
                      const rowKey = `${d.product || product}:${d.draw_number}`
                      return [
                        <tr key={`${d.product || product}-${d.draw_number}`} className="v3histrowline"
                          role="button" tabIndex={0}
                          onClick={() => toggle(d.draw_number, d.product)}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter' || e.key === ' ') {
                              e.preventDefault(); toggle(d.draw_number, d.product)
                            }
                          }}>
                          <td>{d.draw_number}</td>
                          <td>{fmtDay(d.close)}</td>
                          <td>{d.turnover ? kr(d.turnover) : '–'}</td>
                          <td>{top ? `${top.name}: ${top.winners ?? '–'} st` : '–'}
                            {d.top_winners === 0 && <span className="v3roll" title="Ingen vinnare på toppnivån — potten rullar">🎰</span>}
                            {d.n_cancelled > 0 && <span className="v3cancel" title={`${d.n_cancelled} struken/strukna matcher`}>⚠️</span>}</td>
                          <td>{top?.amount ? kr(top.amount) : '–'}</td>
                          <td className="v3expand">{expanded === rowKey ? '▲' : '▼'}</td>
                        </tr>,
                        expanded === rowKey && (
                          <tr key={`${d.product || product}-${d.draw_number}-x`} className="v3histdetail"><td colSpan="6">
                            <div className="v3tiers">
                              {(d.tiers || []).map((t) => (
                                <span key={t.name} className="v3tier">
                                  {t.name}: <b>{t.winners ?? '–'}</b> à <b>{t.amount ? kr(t.amount) : '–'}</b>
                                </span>
                              ))}
                            </div>
                            {!detail[rowKey] && <LoadingState label="Hämtar matchfacit…" />}
                            {detail[rowKey]?.available && (
                              <table className="v3facit">
                                <tbody>
                                  {detail[rowKey].draw.events.map((e) => (
                                    <tr key={e.event_number} className={e.cancelled ? 'cancelled' : ''}>
                                      <td>{e.event_number}</td>
                                      <td>{e.home && e.away ? `${e.home} – ${e.away}` : e.description}</td>
                                      <td className="v3outcome">{e.cancelled ? '⚠️ struken' : e.outcome || '–'}</td>
                                      <td className="v3hint">
                                        {e.streck?.['1'] != null
                                          ? `folket ${e.streck['1']}/${e.streck['X']}/${e.streck['2']} %` : ''}
                                      </td>
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            )}
                          </td></tr>
                        ),
                      ]
                    })}
                  </tbody>
                </table>
              </div>
              {draws.length > 20 && (
                <button className="v3more"
                  onClick={() => setShowAllDraws(!showAllDraws)}>
                  {showAllDraws ? 'visa senaste 20 ▲'
                    : `visa alla ${draws.length} omgångar ▼`}</button>
              )}
            </>
          )}
        </div>
      )}

      <div className="v3note">
        Historiskt <b>facit</b> ur settlementlagret (PH1): utfall, slutstreck,
        slutomsättning och utdelning per nivå. Kohorten är <code>final_only</code>
        {' '}— odds- och streckrörelser finns bara för lokalt observerade omgångar
        och kan aldrig bakfyllas.
      </div>
    </div>
  )
}
