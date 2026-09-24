// Mina kuponger: det du faktiskt spelat, pågående och avslutade, med samma
// filter för lista och summering. Verkliga pengar — aldrig simulerade.
import { useState } from 'react'
import { usePlayedCoupons } from './usePlayedCoupons.js'
import { PlayedCouponDetail, PlayedFileImport, couponKindLabel, couponDate } from './PlayedCoupon.jsx'
import { STATUS, couponStatus, filterCoupons, summarizeCoupons } from '../lib/coupons.js'
import { PRODUCT_LABEL, HIST_FAMILIES } from '../lib/labels.js'
import { topAliveForecast, FORECAST_NOTE, perRowText, minPayoutNote, guaranteeLines, GUARANTEE_NOTE } from '../lib/forecast.js'
import { LoadingState, EmptyState, ErrorState, SortableTable, kr } from '../App.jsx'

const FILTER_KEY = 'svs_kuponger_filter'
const DEFAULT_FILTERS = { period: 'alla', product: 'alla', status: 'alla' }
const readFilters = () => {
  try { return { ...DEFAULT_FILTERS, ...JSON.parse(sessionStorage.getItem(FILTER_KEY) || '{}') } } catch { return DEFAULT_FILTERS }
}
const signed = (v) => `${v > 0 ? '+' : ''}${kr(v)}`
const pct = (v) => (v == null ? '–' : `${v >= 0 ? '+' : ''}${(v * 100).toFixed(1)} %`)

export function StatusChip({ coupon }) {
  const status = couponStatus(coupon)
  return <span className={`v3kstatus ${status}`}>{STATUS[status]}</span>
}

// Läget i EN rad: avgjorda matcher, fastställt bäst, max möjligt. Nivåer och
// chans finns bakom "Visa kupongen".
export function LagText({ coupon }) {
  if (coupon.settled_at) return <>bäst <b>{coupon.correct_max ?? '–'}</b> rätt</>
  const live = coupon.live
  if (!live) {
    const status = couponStatus(coupon)
    return <span className="v3hint">{coupon.live_pending ? 'hämtar liveläge…'
      : status === 'datafel' ? 'liveläge otillgängligt · försöker igen'
        : status === 'ej_startad' ? 'omgången har inte startat' : 'väntar på livebild'}</span>
  }
  const fc = topAliveForecast(live)
  return <>{live.n_decided}/{live.n_events} avgjorda · fastställt <b>{live.best_secure}</b>
    {live.max_possible != null && <> · max {live.max_possible}</>}
    {live.out_of_contention && <span className="v3neg"> · ingen vinstnivå nåbar</span>}
    {fc && <> · lever mot {fc.level} rätt <b title={minPayoutNote(live.forecast, fc) || undefined}>{perRowText(fc)}</b>/rad
      <span className="v3hint" title={minPayoutNote(live.forecast, fc) || FORECAST_NOTE}> (prognos)</span></>}
    {fc && guaranteeLines(live.forecast).map((line) => (
      <span key={line} className="v3hint" title={GUARANTEE_NOTE}> · garanti: {line}</span>))}</>
}

export function MinaKuponger({ openCoupon = null, onOpenCoupon, onCloseCoupon }) {
  const { data, error, reload } = usePlayedCoupons()
  const [filters, setFilters] = useState(readFilters)
  const [showImport, setShowImport] = useState(false)
  const setFilter = (key, value) => setFilters((current) => {
    const next = { ...current, [key]: value }
    try { sessionStorage.setItem(FILTER_KEY, JSON.stringify(next)) } catch { /* ok */ }
    return next
  })
  if (error && !data) return <div className="v3card">
    <ErrorState message={`Kupongerna kunde inte hämtas: ${error}`} />
    <button className="v3more" onClick={reload}>Försök igen</button>
  </div>
  if (!data) return <LoadingState label="Hämtar dina kuponger…" />
  const all = data.coupons || []
  const shown = filterCoupons(all, filters)
  const sum = summarizeCoupons(shown)
  const detail = openCoupon != null ? all.find((c) => c.id === openCoupon) : null
  const forget = async (id) => {
    await fetch(`/api/pool/played/${id}`, { method: 'DELETE' })
    onCloseCoupon?.()
    reload()
  }
  const columns = [
    { key: 'draw_close', label: 'Datum', title: 'Omgångens spelstopp' },
    { key: 'product', label: 'Spel', defaultDir: 'asc', value: (c) => PRODUCT_LABEL[c.product] || c.product },
    { key: 'draw_number', label: 'Omgång' },
    { key: 'kind', label: 'Typ', defaultDir: 'asc', value: (c) => couponKindLabel(c) || '' },
    { key: 'n_rows', label: 'Rader' },
    { key: 'cost_kr', label: 'Insats' },
    { key: 'status', label: 'Status', defaultDir: 'asc', value: (c) => STATUS[couponStatus(c)] },
    { key: 'lage', label: 'Läge', sortable: false },
    { key: 'payout_kr', label: 'Tillbaka', value: (c) => (c.settled_at && c.payout_complete ? c.payout_kr : null) },
    { key: 'roi', label: 'ROI' },
    { key: 'open', label: 'Kupong', sortable: false },
  ]
  return (
    <div className="v3kuponger">
      <div className="v3card">
        <div className="v3cardhead"><h3>🎟️ Mina kuponger</h3>
          <span className="v3hint">{all.length ? `${all.length} bokförda` : ''}</span>
          <button className="v3more" onClick={() => setShowImport((v) => !v)}>
            {showImport ? 'Dölj import' : 'Importera radfil'}</button>
        </div>
        {showImport && <PlayedFileImport onImported={() => { setShowImport(false); reload() }} />}
        {!all.length ? (
          <EmptyState title="Inga bokförda kuponger än"
            detail="Markera kupongen som spelad när du lämnar in den, eller importera den sparade radfilen." />
        ) : <>
          <div className="v3groupfilters" aria-label="Filtrera mina kuponger">
            <label><span>Period</span><select value={filters.period}
              onChange={(e) => setFilter('period', e.target.value)}>
              <option value="alla">Alla</option><option value="30d">Senaste 30 dagarna</option>
              <option value="90d">Senaste 90 dagarna</option><option value="ar">I år</option>
            </select></label>
            <label><span>Spel</span><select value={filters.product}
              onChange={(e) => setFilter('product', e.target.value)}>
              <option value="alla">Alla spel</option>
              {HIST_FAMILIES.map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}
            </select></label>
            <label><span>Status</span><select value={filters.status}
              onChange={(e) => setFilter('status', e.target.value)}>
              <option value="alla">Alla</option><option value="oppna">Pågående</option>
              <option value="rattade">Avslutade</option>
            </select></label>
          </div>
          <div className="v3ph5kpis" aria-label="Summering för valda filter">
            <div><span>Kuponger</span><b>{sum.n}</b></div>
            <div><span>Pågående</span><b>{sum.n_open}</b></div>
            <div><span>Satsat · rättade</span><b>{kr(sum.spent_kr)}</b></div>
            <div><span>Tillbaka</span><b>{kr(sum.won_kr)}</b></div>
            <div><span>Saldo</span><b className={sum.balance_kr > 0 ? 'v3pos' : sum.balance_kr < 0 ? 'v3neg' : ''}>{signed(sum.balance_kr)}</b></div>
            <div><span>ROI</span><b className={sum.roi == null ? '' : sum.roi >= 0 ? 'v3pos' : 'v3neg'}>{pct(sum.roi)}</b></div>
          </div>
          <p className="v3hint">Summeringen följer filtren. Pengar räknas bara på kuponger med
            komplett publicerad utdelning{sum.n_incomplete ? ` (${sum.n_incomplete} rättade väntar på komplett utdelning)` : ''};
            pågående kuponger är varken vinst eller förlust.</p>
          {!shown.length
            ? <EmptyState title="Inga kuponger matchar filtren" />
            : <SortableTable id="mina-kuponger" rows={shown} columns={columns}
                defaultSort={{ key: 'draw_close', dir: 'desc' }}
                wrapperClassName="v3histtablewrap" className="v3histtable v3kupongtable"
                renderRow={(c) => (
                  <tr key={c.id} className={c.settled_at ? '' : 'v3kopen'}>
                    <td>{couponDate(c)}</td>
                    <td>{PRODUCT_LABEL[c.product] || c.product}</td>
                    <td>#{c.draw_number}</td>
                    <td>{couponKindLabel(c) || <span className="v3hint">–</span>}</td>
                    <td>{c.n_rows}</td>
                    <td>{kr(c.cost_kr)}</td>
                    <td><StatusChip coupon={c} /></td>
                    <td><LagText coupon={c} /></td>
                    <td>{c.settled_at ? (c.payout_complete ? kr(c.payout_kr) : 'ofullständig') : '–'}</td>
                    <td className={c.roi == null ? '' : c.roi >= 0 ? 'v3pos' : 'v3neg'}>{c.settled_at && c.payout_complete ? pct(c.roi) : '–'}</td>
                    <td><button className="v3more" onClick={() => onOpenCoupon?.(c.id)}>Visa kupongen</button></td>
                  </tr>
                )}
                renderCard={(c) => (
                  <article key={c.id} className={`v3kupongcard${c.settled_at ? '' : ' open'}`}>
                    <header>
                      <div><b>{PRODUCT_LABEL[c.product] || c.product} · #{c.draw_number}</b>
                        <span>{couponDate(c)}{couponKindLabel(c) ? ` · ${couponKindLabel(c)}` : ''}</span></div>
                      <StatusChip coupon={c} />
                    </header>
                    <div className="v3kupongcardmeta">
                      <span>{c.n_rows} rader · {kr(c.cost_kr)}</span>
                      <span><LagText coupon={c} /></span>
                      {c.settled_at && <span>tillbaka {c.payout_complete ? kr(c.payout_kr) : 'ofullständig'}
                        {c.payout_complete && c.roi != null ? ` · ${pct(c.roi)}` : ''}</span>}
                    </div>
                    <button className="v3more" onClick={() => onOpenCoupon?.(c.id)}>Visa kupongen</button>
                  </article>
                )} />}
        </>}
      </div>
      {detail && (
        <PlayedCouponDetail key={detail.id} coupon={detail} onClose={() => onCloseCoupon?.()}
          onForget={detail.settled_at ? null : () => forget(detail.id)} />
      )}
    </div>
  )
}
