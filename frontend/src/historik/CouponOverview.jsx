import { isMathematical } from '../lib/couponView.js'

const SIGNS = ['1', 'X', '2']
const odds = (v) => v == null ? '–' : Number(v).toFixed(2)

export function CouponOverview({ events, nRows, liveByEvent = {}, showMarket = true }) {
  const math = isMathematical(events, nRows)
  return <section className="coupon-overview" aria-label="Kupong match för match">
    <p className="v3hint">{math ? 'Matematiskt system: alla kombinationer ingår.'
      : 'Reducerat system: markerade tecken ingår, men inte alla kombinationer.'}
      {' '}Grön ram = rätt resultat som finns med. Röd ram = rätt resultat som saknas.
      Streckad ram = aktuell ställning, ännu inte slutresultat.</p>
    {events.map((event) => {
      const live = liveByEvent[event.event_number]
      // En struken match kan ha ett officiellt lottat tecken: visa det,
      // men gör aldrig den pågående ställningen till facit för struken match.
      const outcome = event.outcome || (event.cancelled ? null : live?.sign)
      const provisional = !event.outcome && !(live?.final && !live?.sign_provisional)
      return <article className="coupon-match" key={event.event_number}>
        <div className="coupon-match-name">
          <span>{event.event_number}</span>
          <b>{event.home && event.away ? `${event.home} – ${event.away}`
            : event.description || live?.description || `Match ${event.event_number}`}</b>
          {(live?.score || event.cancelled) && <small>{event.cancelled ? 'Struken' : live.score}</small>}
        </div>
        <div className="coupon-signboxes">
          {SIGNS.map((sign) => {
            const selected = event.covered?.includes(sign)
            const correct = outcome === sign
            return <span key={sign} className={`coupon-sign ${selected ? 'selected' : ''} ${correct
              ? provisional ? 'provisional' : selected ? 'correct' : 'missed' : ''}`}
              aria-label={`${sign}${selected ? ', med' : ', saknas'}${correct
                ? provisional ? ', aktuell ställning' : ', rätt resultat' : ''}`}>
              <b>{sign}</b>{correct && !provisional && <i>{selected ? '✓' : '✗'}</i>}
            </span>
          })}
        </div>
        {showMarket && <details className="coupon-market">
          <summary>Odds och streck vid frysning{math ? '' : ' · radfördelning'}</summary>
          <table><thead><tr><th></th>{SIGNS.map(s => <th key={s}>{s}</th>)}</tr></thead>
            <tbody>
              <tr><th>Sharpodds</th>{SIGNS.map(s => <td key={s}>{odds(event.sharp_odds_at_freeze?.[s])}</td>)}</tr>
              <tr><th>SvS odds</th>{SIGNS.map(s => <td key={s}>{odds(event.odds_at_freeze?.[s])}</td>)}</tr>
              <tr><th>Streck, fryst</th>{SIGNS.map(s => <td key={s}>{event.streck_at_freeze?.[s] ?? '–'} %</td>)}</tr>
              <tr><th>Streck, stopp</th>{SIGNS.map(s => <td key={s}>{event.streck_at_close?.[s] ?? '–'} %</td>)}</tr>
              {!math && <tr><th>Andel rader</th>{SIGNS.map(s => <td key={s}>{event.sign_shares?.[s] == null
                ? '–' : `${Math.round(event.sign_shares[s] * 100)} %`}</td>)}</tr>}
            </tbody></table>
          {event.total_at_freeze && <p className="v3hint">Ö/U {event.total_at_freeze.line}
            {' · '}Över {odds(event.total_at_freeze.O)} · Under {odds(event.total_at_freeze.U)}</p>}
          <p className="v3hint">Senast sparade observation före frysning, aldrig efterhandsodds.
            {event.market_observed_at && ` Senaste marknadsobservation: ${new Date(event.market_observed_at).toLocaleString('sv-SE')}.`}</p>
        </details>}
      </article>
    })}
  </section>
}
