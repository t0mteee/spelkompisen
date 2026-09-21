import { systemComposition } from '../lib/systemComposition.js'
import { selectionReason } from '../lib/couponView.js'

export function SystemComposition({ sys }) {
  const composition = systemComposition(sys)
  const audit = sys.experiment_audit
  return <div className="system-composition">
    <h3>Så är kupongen byggd</h3>
    <p><b>{sys.row_model_label || sys.system_type}</b> · {sys.num_rows} rader</p>
    <p>{sys.rows?.length
      ? 'Procenten visar hur stor del av dina rader som innehåller tecknet – inte matchens vinstchans. 0 % betyder att tecknet saknas helt.'
      : 'Markerade tecken kombineras i alla möjliga kombinationer i det matematiska systemet.'}</p>
    {audit && <div className="experiment-warning" role="status">
      <b>Experiment – inte bevisat bättre än Standard</b>
      <p>Beräknad chans till full pott: Standard {(audit.baseline_top_chance * 100).toFixed(2)} %
        {' → '}denna kupong {(audit.selected_top_chance * 100).toFixed(2)} %.
        Samma matchsannolikheter; inte historiskt resultat eller garanti.</p>
      <span>{audit.fallback?.length
        ? `Skyddet slog till (${audit.fallback.join(', ')}). Kupongen innehåller standardrader.`
        : `${audit.changed_rows} rader skiljer sig från Standard vid samma insats och värdevikt.`}</span>
      {composition.length === 8 && <p>Topptipset betalar bara för 8 rätt. Bättre täckning av 7 rätt ger ingen vinst.</p>}
    </div>}
    <div className="composition-head"><span>Match</span><span>1</span><span>X</span><span>2</span></div>
    {composition.map(pick => <div key={pick.event_number} className="composition-row">
      <div><b>{pick.event_number}. {pick.description}</b>
        {pick.reason && <details><summary>Motivering</summary><p>{selectionReason(pick.reason)}</p></details>}</div>
      {pick.signs.map(({ sign, selected, count, share }) => <div key={sign}
        className={`composition-sign ${selected ? 'selected' : 'omitted'} ${pick.colors?.[sign] === 'blå' ? 'blue' : pick.colors?.[sign] === 'gul' ? 'yellow' : ''}`}
        title={count == null ? selected ? 'Tecknet ingår' : 'Tecknet saknas'
          : `${sign}: ${count} av ${sys.rows.length} rader`}>
        <b>{count == null ? selected ? sign : '–' : `${(share * 100).toFixed(1)} %`}</b>
        {count != null && <small>{count} rader</small>}
      </div>)}
    </div>)}
  </div>
}
