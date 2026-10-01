// spel-ai-kompisens beslut och förslag (#/beslut, #/beslut/<id>).
// Det här är den ENDA platsen där Saman svarar: betrodd kod i Spelkompisen,
// inte agentens app (docs/spel-ai-kompisen-design.md 5.5). Agentens app
// visar samma lista men länkar hit för svaret.
import { useEffect, useState } from 'react'
import { get } from '../lib/api.js'
import { LoadingState, ErrorState } from '../components/ui.jsx'
import { answerText, deadlineText, isDecision, kindLabel, recommendedIndex, splitInbox } from '../lib/inbox.js'

async function postAnswer(id, val, kommentar) {
  const r = await fetch(`/api/spelai/inbox/${id}/svar`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ val, kommentar: kommentar || null }),
  })
  if (!r.ok) {
    let detail = null
    try { detail = (await r.json()).detail } catch { /* ingen detail */ }
    throw new Error(detail || `svaret kunde inte sparas (${r.status})`)
  }
  return r.json()
}

function InboxCard({ item, focused, onAnswered }) {
  const [comment, setComment] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const rec = recommendedIndex(item)
  const decision = isDecision(item)
  const send = async (val, onlyComment = false) => {
    setBusy(true)
    setError(null)
    try {
      await postAnswer(item.id, val, comment.trim() || null)
      setComment('')
      onAnswered(onlyComment)
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }
  return (
    <article id={`beslut-${item.id}`} className={`v3beslut${focused ? ' focus' : ''}`}>
      <div className="v3beslut-chips">
        <span>{kindLabel(item.typ)}</span>
        <span>{item.kalla}</span>
        {item.sista_tid && <span className="warn">{deadlineText(item.sista_tid)}</span>}
      </div>
      <h3>{item.rubrik}</h3>
      <p className="v3beslut-why">{item.varfor}</p>
      {decision ? (
        <div className="v3beslut-actions">
          {(item.alternativ || []).map((alt, index) => (
            <button key={index} type="button" disabled={busy}
              className={index === rec ? 'primary' : ''}
              onClick={() => send(String(index))}>
              {index === rec ? 'Godkänn: ' : 'Välj: '}{alt.text}
            </button>
          ))}
        </div>
      ) : (
        <div className="v3beslut-actions two">
          <button type="button" className="primary" disabled={busy} onClick={() => send('kor_nu')}>
            {item.typ === 'forslag_spelrad' ? 'Bra råd' : 'Kör nu'}
          </button>
          <button type="button" disabled={busy} onClick={() => send('nej')}>Nej</button>
        </div>
      )}
      <label className="v3beslut-comment">
        <span>Kommentar (följer med ditt val, eller skickas ensam)</span>
        <textarea rows={2} value={comment} onChange={(e) => setComment(e.target.value)} />
      </label>
      <button type="button" disabled={busy || !comment.trim()} onClick={() => send('kommentar', true)}>
        Skicka bara kommentaren
      </button>
      {error && <p className="v3beslut-error" role="alert">{error}</p>}
      {(item.kommentarer || []).length > 0 && (
        <ul className="v3beslut-comments">
          {item.kommentarer.map((k, i) => <li key={i}>{k.kommentar}</li>)}
        </ul>
      )}
    </article>
  )
}

export function BeslutView({ focus = null }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [saved, setSaved] = useState(null)
  const [notiser, setNotiser] = useState(null)
  const load = () => get('/api/spelai/inbox')
    .then((value) => { setData(value); setError(null) })
    .catch((e) => setError(e.message))
  useEffect(() => {
    load()
    get('/api/spelai/notiser').then(setNotiser).catch(() => setNotiser(null))
  }, [])
  useEffect(() => {
    if (focus == null || !data) return
    document.getElementById(`beslut-${focus}`)?.scrollIntoView({ block: 'start' })
  }, [focus, data])

  if (error && !data) return <ErrorState message={`Inkorgen kunde inte hämtas (${error})`} />
  if (!data) return <LoadingState label="Hämtar beslut…" />
  if (!data.tabeller) {
    return (
      <section className="v3beslutvy">
        <h2>Beslut</h2>
        <p className="v3beslut-why">spel-ai-kompisens inkorg är inte installerad ännu.</p>
      </section>
    )
  }
  const { beslut, forslag, besvarade } = splitInbox(data.poster)
  const answered = (onlyComment) => {
    setSaved(onlyComment ? 'Kommentaren är sparad.' : 'Svaret är sparat.')
    load()
  }
  return (
    <div className="v3beslutvy">
      <section>
        <h2>Beslut</h2>
        <p className="v3beslut-why">
          Agentens och Spelkompisens beslut på ett ställe. Ditt svar sparas här med tid,
          och agenten kan aldrig svara åt dig.
        </p>
        {saved && <p className="v3beslut-saved" role="status">{saved}</p>}
        {beslut.length
          ? beslut.map((item) => (
            <InboxCard key={item.id} item={item} focused={focus === item.id} onAnswered={answered} />))
          : <p className="v3beslut-why">Inga beslut väntar.</p>}
      </section>
      <section>
        <h2>Förslag från agenten</h2>
        <p className="v3beslut-why">
          Förbättringar genomförs i agentens app efter 24 h om du inte säger nej. Spelråd är bara råd.
        </p>
        {forslag.length
          ? forslag.map((item) => (
            <InboxCard key={item.id} item={item} focused={focus === item.id} onAnswered={answered} />))
          : <p className="v3beslut-why">Inga nya förslag.</p>}
      </section>
      <section>
        <h2>Notiser</h2>
        {notiser?.aktiv
          ? (<p className="v3beslut-why">
              Agenten skickar notiser via ntfy, tysta timmar {notiser.tysta_timmar}.{' '}
              <a href={notiser.prenumerera} target="_blank" rel="noreferrer">Prenumerera</a>
              {' '}med ntfy-appen på mobilen.
            </p>)
          : <p className="v3beslut-why">Notiserna är inte påslagna ännu.</p>}
      </section>
      {besvarade.length > 0 && (
        <section>
          <h2>Besvarade</h2>
          <ul className="v3beslut-done">
            {besvarade.slice(0, 30).map((item) => (
              <li key={item.id}>
                <b>{item.rubrik}</b>
                <span>{kindLabel(item.typ)} · {item.kalla} · {answerText(item)}</span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  )
}
