// Big 9 (ATG) under Poolspel (beslut 2026-11-04-big9-i-byggaren): omgångarna,
// matcherna med ATG:s odds och folkets streck för de sex cellerna och
// byggaren (backend/app/big9_view.py → big9_builder, samma byggare som
// facitsidans standard). ATG tar bara fulla system (beslut
// 2026-11-04-big9-fullt-system): byggaren väljer en cellmängd per match och
// kupongen visar vilka rutor Saman markerar under "Spela enskilda utfall" på
// atg.se. Egen kupong (beslut 2026-11-04-big9-lagg-till-i-kupong-omforsok):
// Saman trycker på rutorna själv och ser streck, modell och kvot per vald ruta;
// byggarens system kan läsas in som start. Inga spel läggs härifrån.
import { useEffect, useRef, useState } from 'react'
import { getDetail } from '../lib/api.js'
import { kr } from '../lib/format.js'
import {
  BIG9_CELLS, cellLabel, cellShort, valueClass, pctText, rowTokens, rowsText, fileName,
  roundOptions, roundKey, fmtSwedish, systemCells, systemFormula, couponText,
  ratioClass, emptyCoupon, toggleCell, couponFromSystem, restoreCoupon, couponStats, smallPct, oneIn,
} from '../lib/big9.js'
import { EmptyState, ErrorState, LoadingState } from '../components/ui.jsx'

const ATG_URL = 'https://www.atg.se/sport/big9'
const SHOW_ROWS = 20
const SAVED_KEY = 'big9_state'
const COUPON_KEY = 'big9_kupong'
// beslut 2026-11-04-big9-hog-ev-i-appen-omforsok: tredje valet, aldrig standard
const HIGH_EV = 'hög EV'
const STRATEGY_NOTES = { [HIGH_EV]: 'färre rätt, sällsynta stora vinster' }

function readSaved(name = SAVED_KEY) {
  try { return JSON.parse(localStorage.getItem(name) || '{}') || {} } catch { return {} }
}

// Egen kupong: tryck på en ruta för att lägga till eller ta bort den.
function OwnCoupon({ round, coupon, setCoupon, system }) {
  const [copied, setCopied] = useState(false)
  const stats = couponStats(round.matches, coupon, round.row_price)
  const text = couponText({ matches: round.matches }, coupon)
  const change = (next) => { setCoupon(next); setCopied(false) }
  const copy = async () => {
    try { await navigator.clipboard.writeText(text); setCopied(true) } catch { setCopied(false) }
  }
  const picked = stats.sizes.some(Boolean)
  return (
    <section className="big9-own">
      <h2>Egen kupong</h2>
      <p className="big9-hint">Tryck på en ruta för att lägga till eller ta bort den. Varje ruta
        visar folkets streck och modellens sannolikhet (ATG:s odds utan marginal); en vald ruta
        visar även kvoten modell/streck — grön över 1, röd under 1.</p>
      <div className="big9-actions">
        <button className="big9-btn" disabled={!system}
          title={system ? 'Ersätt kupongen med byggarens fulla system' : 'Bygg ett system nedan först'}
          onClick={() => change(couponFromSystem(system, round.matches))}>Läs in byggarens system</button>
        <button className="big9-btn" disabled={!picked} onClick={() => change(emptyCoupon(round.matches.length))}>Töm</button>
        <a className="big9-btn big9-atg" href={ATG_URL} target="_blank" rel="noopener noreferrer">Spela på ATG →</a>
      </div>
      <div className="big9-scroll">
        <table className="big9-table big9-pick">
          <thead><tr><th>#</th><th>Match</th>{BIG9_CELLS.map((c) => <th key={c} title={cellLabel(c)}>{cellShort(c)}</th>)}<th>Rutor</th></tr></thead>
          <tbody>
            {round.matches.map((m, i) => {
              const set = coupon[i] || []
              return (
                <tr key={m.event_number}>
                  <td>{m.event_number}</td>
                  <td className="big9-match">{m.home} – {m.away}{m.cancelled && <small>struken — rätt för alla</small>}</td>
                  {m.cells.map((c) => {
                    const on = set.includes(c.cell)
                    const streck = m.streck ? `${Math.round(m.streck[c.cell])} %` : '–'
                    return (
                      <td key={c.cell} className="big9-pickcell">
                        <button type="button" className={`big9-pickbtn ${on ? 'on' : ''}`} aria-pressed={on}
                          onClick={() => change(toggleCell(coupon, i, c.cell))}
                          title={`${cellLabel(c.cell)}: streck ${m.streck ? `${m.streck[c.cell].toFixed(1)} %` : '–'}, modell ${pctText(c.p)}, kvot ${c.value ?? '–'} — ${on ? 'tryck för att ta bort' : 'tryck för att lägga till'}`}>
                          <span>{streck}</span>
                          <small>{pctText(c.p, 0)}</small>
                          {on && <b className={ratioClass(c.value)}>{c.value != null ? c.value.toFixed(2).replace('.', ',') : '–'}</b>}
                        </button>
                      </td>
                    )
                  })}
                  <td>{set.length}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      <p className="big9-hint">Övre siffran i rutan är folkets streck, undre modellens
        sannolikhet; den fetstilta under en vald ruta är kvoten modell/streck.</p>
      <div className="big9-kpis">
        <span>form <b>{stats.form}</b></span>
        <span><b>{stats.rows}</b> rader</span>
        <span>kostnad <b>{kr(stats.cost)}</b></span>
        <span title="Produkten av modellens sannolikhet för de valda rutorna (struken match = rätt)">
          chans 9 rätt <b>{smallPct(stats.chance)}</b>{oneIn(stats.chance) && ` (${oneIn(stats.chance)})`}</span>
        <span title="Andelen av folkets rader som ligger i samma kupong: produkten av strecken, matcherna som oberoende">
          folkets andel <b>{smallPct(stats.folk)}</b></span>
        {stats.ratio != null && <span title="Chans för 9 rätt delat med folkets andel">
          kvot <b className={ratioClass(stats.ratio)}>{stats.ratio.toFixed(2).replace('.', ',')}</b></span>}
      </div>
      {stats.missing.length > 0 && picked && (
        <p className="big9-hint">Välj minst en ruta i match {stats.missing.join(', ')} — ATG räknar hela systemet.</p>
      )}
      {stats.unpriced.length > 0 && (
        <p className="big9-hint">Modellen saknar odds i match {stats.unpriced.join(', ')} — chansen visas inte.</p>
      )}
      {stats.unstreck.length > 0 && (
        <p className="big9-hint">Streck saknas i match {stats.unstreck.join(', ')} — folkets andel visas inte.</p>
      )}
      {stats.rows > 0 && (
        <>
          <p className="big9-hint">På atg.se/sport/big9: välj <b>Spela enskilda utfall</b> och markera
            de valda rutorna: <b>{systemFormula(coupon).text}</b> à {round.row_price.toFixed(2).replace('.', ',')} kr.</p>
          <div className="big9-actions">
            <button className="big9-btn" onClick={copy}>{copied ? 'Kopierat ✓' : 'Kopiera kupongen'}</button>
          </div>
        </>
      )}
    </section>
  )
}

function MatchTable({ round }) {
  return (
    <div className="big9-scroll">
      <table className="big9-table">
        <thead>
          <tr>
            <th>#</th><th>Match</th>
            <th title="ATG:s odds: 1 X 2 · Över/Under 2,5">Odds</th>
            {BIG9_CELLS.map((c) => <th key={c} title={cellLabel(c)}>{cellShort(c)}</th>)}
            <th>Utfall</th>
          </tr>
        </thead>
        <tbody>
          {round.matches.map((m) => (
            <tr key={m.event_number}>
              <td>{m.event_number}</td>
              <td className="big9-match">
                <b>{m.home} – {m.away}</b>
                <small>{m.league} · {fmtSwedish(m.start)}{m.cancelled ? ' · struken' : ''}</small>
              </td>
              <td className="big9-odds">
                {m.odds ? <>
                  {[m.odds.home, m.odds.tie, m.odds.away].map((o) => o ?? '–').join(' / ')}
                  <small>Ö {m.odds.over ?? '–'} · U {m.odds.under ?? '–'}</small>
                </> : '–'}
              </td>
              {m.cells.map((c) => (
                <td key={c.cell} className={`big9-cell ${m.outcome === c.cell ? 'hit' : ''}`}
                  title={`${cellLabel(c.cell)}: vår ${pctText(c.p)} (${m.p_source === 'odds' ? 'ATG:s odds' : 'folkets fördelning'}), folket ${m.streck ? `${m.streck[c.cell].toFixed(1)} %` : '–'}, värde ${c.value ?? '–'}`}>
                  <span className={valueClass(c.value)}>{pctText(c.p, 0)}</span>
                  <small>{m.streck ? `${Math.round(m.streck[c.cell])} %` : '–'}</small>
                </td>
              ))}
              <td>{m.outcome ? cellShort(m.outcome) : ''}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="big9-hint">Övre siffran är vår sannolikhet för cellen (ATG:s 1X2- och
        Ö/U-odds utan marginal), undre folkets streck. Grön = värde ≥ 1,08, röd &lt; 0,92.</p>
    </div>
  )
}

// Kupongen att markera hos ATG: de sex rutorna per match, valda rutor ifyllda.
function AtgCoupon({ system }) {
  const chosen = systemCells(system)
  const formula = systemFormula(chosen)
  return (
    <>
      <h3>Kupong att markera hos ATG</h3>
      <p className="big9-hint">På atg.se/sport/big9: välj <b>Spela enskilda utfall</b> och
        markera de ifyllda rutorna per match. ATG räknar hela systemet:{' '}
        <b>{formula.text}</b> à {system.row_price.toFixed(2).replace('.', ',')} kr = <b>{kr(system.cost)}</b>.</p>
      <div className="big9-scroll">
        <table className="big9-table big9-cover">
          <thead><tr><th>#</th><th>Match</th>{BIG9_CELLS.map((c) => <th key={c}>{cellShort(c)}</th>)}<th>Utfall</th></tr></thead>
          <tbody>
            {system.matches.map((m, i) => {
              const set = new Set(chosen[i] || [])
              return (
                <tr key={m.event_number}>
                  <td>{m.event_number}</td>
                  <td className="big9-match">{m.home} – {m.away}</td>
                  {BIG9_CELLS.map((c) => (
                    <td key={c} className={set.has(c) ? 'big9-mark' : 'big9-empty'}
                      title={`${cellLabel(c)}: ${set.has(c) ? 'markera' : 'lämna tom'}`}>
                      {set.has(c) ? '✓' : ''}
                    </td>
                  ))}
                  <td>{set.size}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </>
  )
}

function RowList({ system }) {
  const [all, setAll] = useState(false)
  const shown = all ? system.rows : system.rows.slice(0, SHOW_ROWS)
  return (
    <>
      <h3>Raderna i systemet</h3>
      <div className="big9-scroll">
        <table className="big9-table big9-rows">
          <thead><tr><th>Rad</th>{system.matches.map((m) => <th key={m.event_number} title={`${m.home} – ${m.away}`}>{m.event_number}</th>)}</tr></thead>
          <tbody>
            {shown.map((row, i) => (
              <tr key={row}>
                <td>{i + 1}</td>
                {rowTokens(row).map((t, j) => <td key={j} className="big9-token">{cellShort(t)}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {system.rows.length > SHOW_ROWS && (
        <button className="big9-btn" onClick={() => setAll((v) => !v)}>
          {all ? `Visa ${SHOW_ROWS} rader` : `Visa alla ${system.rows.length} rader`}
        </button>
      )}
    </>
  )
}

function SystemResult({ system, onEdit }) {
  const [mode, setMode] = useState('kupong')
  const [copied, setCopied] = useState(false)
  const coupon = couponText(system)
  const rows = rowsText(system.rows)
  const copy = async (text) => {
    try { await navigator.clipboard.writeText(text); setCopied(true) } catch { setCopied(false) }
  }
  const download = () => {
    const url = URL.createObjectURL(new Blob([rows], { type: 'text/plain' }))
    const a = document.createElement('a')
    a.href = url; a.download = fileName(system.product, system.serial); a.click()
    URL.revokeObjectURL(url)
  }
  const pick = (next) => { setMode(next); setCopied(false) }
  return (
    <div className="big9-result">
      <div className="big9-kpis">
        <span>fullt system <b>{system.form ?? systemFormula(systemCells(system)).sizes.join('·')}</b></span>
        <span><b>{system.n_rows}</b> rader</span>
        <span>insats <b>{kr(system.cost)}</b></span>
        <span title="Byggarens förväntade utdelning mot prognosomsättningen">EV <b className={system.ev_total >= system.cost ? 'pos' : ''}>{kr(system.ev_total)}</b></span>
        <span>strategi <b>{system.strategy}</b>{system.strategy_note && system.strategy === HIGH_EV && <> ({system.strategy_note})</>}</span>
        {system.standard_key && <span title={system.standard_key}>= standardens inställning</span>}
      </div>
      <p className="big9-note">{system.note}</p>
      <div className="big9-actions">
        <button className={`big9-btn ${mode === 'kupong' ? 'on' : ''}`} onClick={() => pick('kupong')}>Kupong</button>
        <button className={`big9-btn ${mode === 'rader' ? 'on' : ''}`} onClick={() => pick('rader')}>Rader</button>
        <button className={`big9-btn ${mode === 'text' ? 'on' : ''}`} onClick={() => pick('text')}>Text</button>
        <button className="big9-btn" onClick={onEdit} title="Läs in systemet i Egen kupong och ändra rutorna">Ändra i egen kupong ↑</button>
        <a className="big9-btn big9-atg" href={ATG_URL} target="_blank" rel="noopener noreferrer">Spela på ATG →</a>
      </div>
      {mode === 'kupong' && <AtgCoupon system={system} />}
      {mode === 'rader' && <RowList system={system} />}
      {mode === 'text' && (
        <>
          <textarea className="big9-text" readOnly value={coupon} rows={Math.min(16, system.matches.length + 2)} />
          <div className="big9-actions">
            <button className="big9-btn" onClick={() => copy(coupon)}>{copied ? 'Kopierat ✓' : 'Kopiera kupongen'}</button>
            <button className="big9-btn" onClick={download}>Ladda ned raderna (.txt)</button>
          </div>
          <p className="big9-hint">En rad per match med rutorna att markera under Spela
            enskilda utfall. Radfilen är hela korsprodukten (en token per match, 1O =
            hemmaseger och över 2,5) — ATG tar ingen radfil, den är bara för kontroll.</p>
        </>
      )}
    </div>
  )
}

export function Big9View() {
  const [saved] = useState(readSaved)
  const [list, setList] = useState(null)
  const [key, setKey] = useState(saved.key || '')
  const [round, setRound] = useState(null)
  const [strategy, setStrategy] = useState(saved.strategy || 'medel')
  const [budget, setBudget] = useState(saved.budget || 256)
  const [system, setSystem] = useState(null)
  const [coupon, setCoupon] = useState([])
  const ownRef = useRef(null)
  const [building, setBuilding] = useState(false)
  const [err, setErr] = useState(null)
  const [loading, setLoading] = useState(true)
  const sequence = useRef(0)

  // Omgången laddas från listans svar och från väljaren (aldrig i en effect).
  // Löpnumret gör att ett sent svar för en tidigare vald omgång kastas.
  const loadRound = (nextKey) => {
    setKey(nextKey)
    const id = ++sequence.current
    setErr(null); setRound(null); setSystem(null); setCoupon([])
    if (!nextKey) { setLoading(false); return }
    setLoading(true)
    const [product, serial] = nextKey.split('|')
    getDetail(`/api/big9/round?product=${product}&serial=${serial}`, 'Big 9-omgång')
      .then((data) => {
        if (id !== sequence.current) return
        setRound(data)
        setCoupon(restoreCoupon(readSaved(COUPON_KEY)[nextKey], data.matches.length))
      })
      .catch((e) => { if (id === sequence.current) setErr(String(e.message || e)) })
      .finally(() => { if (id === sequence.current) setLoading(false) })
  }

  useEffect(() => {
    let alive = true
    getDetail('/api/big9/rounds', 'Big 9').then((data) => {
      if (!alive) return
      setList(data)
      const options = roundOptions(data)
      const restored = options.find((r) => roundKey(r) === saved.key)
      loadRound(roundKey(restored || options[0]))
    }).catch((e) => { if (alive) { setErr(String(e.message || e)); setLoading(false) } })
    return () => { alive = false; sequence.current += 1 }
  }, [])  // eslint-disable-line

  useEffect(() => {
    try { localStorage.setItem(SAVED_KEY, JSON.stringify({ key, strategy, budget })) } catch { /* ok */ }
  }, [key, strategy, budget])

  // Den egna kupongen sparas per omgång (bara öppna omgångar behålls).
  useEffect(() => {
    if (!round || roundKey(round) !== key || coupon.length !== round.matches.length) return
    const open = new Set((list?.open || []).map(roundKey))
    const all = readSaved(COUPON_KEY)
    const next = Object.fromEntries(Object.entries(all).filter(([k]) => open.has(k)))
    if (coupon.some((set) => set.length)) next[key] = coupon
    else delete next[key]
    try { localStorage.setItem(COUPON_KEY, JSON.stringify(next)) } catch { /* ok */ }
  }, [round, key, coupon, list])

  const editSystem = () => {
    if (!round || !system) return
    setCoupon(couponFromSystem(system, round.matches))
    ownRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  const build = async () => {
    if (!round || building) return
    const id = sequence.current
    setBuilding(true); setErr(null)
    try {
      const built = await getDetail(
        `/api/big9/system?product=${round.product}&serial=${round.serial}&budget=${budget}&strategy=${encodeURIComponent(strategy)}`,
        'Big 9-bygget')
      if (id === sequence.current) setSystem(built)
    } catch (e) {
      if (id === sequence.current) setErr(String(e.message || e))
    } finally {
      setBuilding(false)
    }
  }

  const options = roundOptions(list)
  const budgets = list?.budgets || [16, 32, 64, 128, 256, 512, 1024]
  const strategies = list?.strategies || ['säker', 'medel', 'hög EV']
  const strategyNotes = list?.strategy_notes || STRATEGY_NOTES
  const turnover = round?.turnover

  return (
    <div className="big9">
      <div className="v3poolbar">
        {options.length > 0 && (
          <select className="v3drawsel" value={key} onChange={(e) => loadRound(e.target.value)}>
            {options.map((r) => (
              <option key={roundKey(r)} value={roundKey(r)}>
                {r.name} omg {r.serial} · stänger {fmtSwedish(r.close)}
                {r.open ? '' : ` (${r.status})`}{r.title ? ` · ${r.title}` : ''}
              </option>
            ))}
          </select>
        )}
        {round && (
          <span className="v3poolkpi">
            oms <b>{kr(turnover?.live)}</b>
            {turnover?.projected != null && <> · prognos <b title={turnover.basis}>{kr(turnover.used)}</b></>}
            {round.jackpot?.value > 0 && <> · 💰 {kr(round.jackpot.value)}</>}
            {' '}· återbetalning <b>{pctText(round.payout_ratio?.andel)}</b>
            {' '}· läst {fmtSwedish(round.observed_at)}
          </span>
        )}
        <a className="big9-btn big9-atg" href={ATG_URL} target="_blank" rel="noopener noreferrer">atg.se/sport/big9 →</a>
      </div>

      {err && <ErrorState message={err} />}
      {loading && <LoadingState label="Hämtar Big 9 från ATG-insamlingen…" />}
      {list && !list.available && <EmptyState title="Big 9 saknas" detail={list.note} />}
      {list?.available && !options.length && (
        <EmptyState title="Ingen Big 9-omgång" detail="ATG-insamlingen har inte sett någon omgång än." />
      )}
      {list?.available && !list.open.length && options.length > 0 && (
        <p className="big9-hint">Ingen öppen omgång just nu — visar de senaste stängda.</p>
      )}

      {round && (
        <>
          <section>
            <h2>{round.name} omgång {round.serial}{round.title ? ` · ${round.title}` : ''}</h2>
            <p className="big9-hint">
              Nio matcher, en cell per match: 1X2 × över/under {String(round.ou_limit).replace('.', ',')} mål
              {round.wildcard ? ', plus ett Wild Card per rad' : ''}. Radpris {round.row_price.toFixed(2).replace('.', ',')} kr,
              vinst på {Object.keys(round.splits).join('–').replace(/–.*–/, '–')} rätt. Spelstopp {fmtSwedish(round.close)}.
            </p>
            <MatchTable round={round} />
          </section>

          {round.open && !round.wildcard && coupon.length === round.matches.length && (
            <div ref={ownRef}>
              <OwnCoupon round={round} coupon={coupon} setCoupon={setCoupon} system={system} />
            </div>
          )}

          <section className="buildbar">
            <h2>Bygg Big 9-system</h2>
            {round.open ? (
              round.wildcard ? (
                <p className="big9-hint">{round.name} har Wild Card — byggaren gör bara fulla
                  system för Big 9 utan Wild Card.</p>
              ) : <>
                <div className="controls">
                  {strategies.map((s) => (
                    <label key={s} className={strategy === s ? 'active' : ''} title={strategyNotes[s]}>
                      <input type="radio" name="big9strategy" checked={strategy === s}
                        onChange={() => { setStrategy(s); setSystem(null) }} />{s}
                      {s === HIGH_EV && <small className="big9-strat-note">{strategyNotes[s]}</small>}
                    </label>
                  ))}
                  <label className="budget">
                    Budget{' '}
                    <select value={budget} onChange={(e) => { setBudget(Number(e.target.value)); setSystem(null) }}>
                      {budgets.map((b) => <option key={b} value={b}>{b} kr ({b * 2} rader)</option>)}
                    </select>
                  </label>
                  <button className="big9-btn primary" onClick={build} disabled={building}>
                    {building ? 'Bygger…' : 'Bygg fullt system'}
                  </button>
                </div>
                <p className="big9-hint">ATG tar bara fulla system: byggaren väljer de
                  rutor per match (av sex) som ger högst värde, och antalet rader är produkten
                  av rutorna per match — högst budgeten / 0,50 kr. Samma byggare som facitsidans
                  standard (medel, 256 kr). Säker väger träffchans tyngre (värdevikt 0,2).
                  Hög EV väljer rutorna på ren värdekvot (värdevikt 1,0): färre rätt, sällsynta
                  stora vinster — en lottsedel, ingen visad förbättring.</p>
                {system && <SystemResult system={system} onEdit={editSystem} />}
              </>
            ) : <p className="big9-hint">Omgången är stängd ({round.status}) — byggaren gäller bara öppna omgångar.</p>}
          </section>
        </>
      )}
    </div>
  )
}
