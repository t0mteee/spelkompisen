/* eslint-disable react-refresh/only-export-components -- filen delar
   medvetet komponenter och hjälpare; samma undantag som App.jsx alltid haft. */
// Små UI-atomer och hooks som alla vyer delar. Brutna ur App.jsx 2026-09-02.
import { Component, useState } from 'react'

// Komponentbibliotek: appskalet bor i AppV3.jsx (laddas av main.jsx) och
// importerar alla tunga byggstenar, konstanter och helpers härifrån —
// se exportblocket i slutet av filen.

// Ren presentationskomponent — måste bo på modulnivå, annars skapas en ny
// komponenttyp vid varje render av föräldern.
export const InfoDot = ({ text }) => <span className="idot" title={text}>i</span>
export function useStoredBool(key, initial = false) {
  const [value, setValue] = useState(() => {
    try {
      const saved = localStorage.getItem(key)
      return saved == null ? initial : saved === '1'
    } catch { return initial }
  })
  const update = (next) => setValue((previous) => {
    const resolved = typeof next === 'function' ? next(previous) : next
    try { localStorage.setItem(key, resolved ? '1' : '0') } catch { /* ok */ }
    return resolved
  })
  return [value, update]
}
export function LoadingState({ label = 'Hämtar data…' }) {
  return <div className="loading-state" role="status"><span className="spinner" aria-hidden="true" />{label}</div>
}
export function EmptyState({ title, detail }) {
  return <div className="empty-state"><b>{title}</b>{detail && <span>{detail}</span>}</div>
}
export function ErrorState({ message }) {
  return <div className="error state-error" role="alert"><b>Något gick fel</b><span>{message}</span></div>
}

/* ---------- insamling (launchd – körs även när appen är stängd) ---------- */
export class ErrBoundary extends Component {
  constructor(p) { super(p); this.state = { err: null } }
  static getDerivedStateFromError(err) { return { err } }
  render() {
    if (this.state.err) return <div className="error">Fel: {String(this.state.err?.stack || this.state.err).slice(0, 600)}</div>
    return this.props.children
  }
}
