const SOURCES = { odds: 'SvS-odds', sharp: 'Pinnacle-odds', streck: 'folkets streck', none: 'underlag saknas' }

export function poolInputTitle(health) {
  if (!health || health.level === 'ok') return null
  if (health.missing_all > 0) return `Kompletta 1X2-odds saknas från båda källorna i ${health.missing_all}/${health.n_matches} matcher`
  if (health.missing_sharp > 0) {
    // pool-sharp-freshness-v1: ett cachat men inaktuellt pris räknas som saknat.
    const stale = health.stale_sharp > 0 ? ` (${health.stale_sharp} med inaktuellt pris)` : ''
    return `Pinnacle 1X2 saknas i ${health.missing_sharp}/${health.n_matches} matcher${stale}`
  }
  if (health.missing_svs > 0) return `SvS 1X2 saknas i ${health.missing_svs}/${health.n_matches} matcher`
  return `Ö/U-underlag saknas i ${health.missing_total}/${health.n_matches} matcher`
}

export function sourceLabel(source) { return SOURCES[source] || 'okänd källa' }

export function poolReviewText(health, scope = 'Aktuell analys') {
  return [
    'Granska saknat oddsunderlag i Spelkompisen.',
    `Spel: ${health.product} · omgång ${health.draw_number} · ${scope}`,
    `Analyssvar hämtat: ${health.analysis_fetched_at || 'okänd tid'}`,
    `Kontroll: ${health.version}${health.freshness_version ? ` + ${health.freshness_version}` : ''} · ${health.n_matches} matcher`,
    `Ofullständig SvS 1X2: ${health.missing_svs}. Pinnacle 1X2: ${health.missing_sharp}${health.stale_sharp ? ` (varav ${health.stale_sharp} med inaktuellt cachat pris)` : ''}. Båda: ${health.missing_all}. Ö/U: ${health.missing_total}.`,
    ...health.issues.map(m => `${m.event_number}. ${m.description}: saknar ${m.missing.join(', ')}. Sannolikhetsbas: ${sourceLabel(m.prob_source)}.${m.reason ? ` Orsak: ${m.reason}.` : ''}`),
    ...health.issues.filter(m => m.reserve_total).map(m => {
      const r = m.reserve_total
      return `${m.event_number}. Ö/U-reserv: ${r.label}; status ${r.status}; färsk/tillgänglig ${r.available ? 'ja' : 'nej'}; lina ${r.line ?? '–'}; Över ${r.over_odds ?? '–'} / Under ${r.under_odds ?? '–'}; observerat ${r.observed_at || 'okänt'}. Inte sharp, används inte av byggaren.`
    }),
    'Kontrollera källhälsa, matchning (inklusive pool_match_diagnostic), marknadsutbud och observationstider. Anta inte att allt beror på namn.',
    'Detta beskriver analysens tillgängliga priser. Pinnacle används bara om priset är högst 90 min gammalt och länken inte observerats tappad efter priset; SvS-oddsen är inte bevis på färskhet, och inget av det är en giltig historisk PIT-capture. Bakfyll inte odds eller ändra frysta kuponger.',
  ].join('\n')
}
