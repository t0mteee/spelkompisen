/* eslint-disable react-refresh/only-export-components -- filen delar
   medvetet komponenter och hjälpare; samma undantag som App.jsx alltid haft. */
// EN sorterbar tabell för alla jämförbara listor (rubrikklick på desktop,
// sortval + samma kortordning på mobil). `limit` kapar EFTER sorteringen —
// slicea aldrig `rows` före anropet. Bruten ur App.jsx 2026-09-02.
import { useState } from 'react'

export function useSortedRows(id, rows, columns, defaultSort) {
  const [sort, setSort] = useState(() => {
    try { return JSON.parse(localStorage.getItem(`svs_sort_${id}`)) || defaultSort } catch { return defaultSort }
  })
  const saveSort = (next) => {
    try { localStorage.setItem(`svs_sort_${id}`, JSON.stringify(next)) } catch { /* ok */ }
    return next
  }
  const toggle = (key) => setSort((s) => saveSort({
    key,
    dir: s?.key === key && s?.dir === 'desc'
      ? 'asc'
      : s?.key === key ? 'desc'
        : columns.find((c) => c.key === key)?.defaultDir || 'desc',
  }))
  const choose = (key) => setSort((s) => saveSort({
    key,
    dir: s?.key === key ? s.dir : columns.find((c) => c.key === key)?.defaultDir || 'desc',
  }))
  const activeSort = columns.some((c) => c.key === sort?.key)
    ? sort
    : defaultSort || { key: columns[0]?.key, dir: columns[0]?.defaultDir || 'desc' }
  const col = columns.find((c) => c.key === activeSort?.key)
  const sorted = [...rows]
  if (col) {
    const val = col.value || ((r) => r[col.key])
    sorted.sort((a, b) => {
      const va = val(a), vb = val(b)
      if (va == null && vb == null) return 0
      if (va == null) return 1
      if (vb == null) return -1
      const cmp = typeof va === 'string' ? va.localeCompare(vb, 'sv') : va - vb
      return activeSort.dir === 'desc' ? -cmp : cmp
    })
  }
  return { sorted, sort: activeSort, toggle, choose }
}

// `limit` kapar EFTER sorteringen — annars visas godtyckliga rader som råkar
// ligga först i indata, prydligt sorterade, vilket ser ut som en topplista utan
// att vara det. null = ingen kapning.
// `limit` kapar EFTER sorteringen — annars visas godtyckliga rader som råkar
// ligga först i indata, prydligt sorterade, vilket ser ut som en topplista utan
// att vara det. null = ingen kapning.
export function SortableTable({
  id, columns, rows, renderRow, renderCard, defaultSort, className,
  wrapperClassName = 'tablewrap', limit = null,
}) {
  const { sorted: allSorted, sort, toggle, choose } = useSortedRows(
    id, rows, columns, defaultSort)
  const sorted = limit == null ? allSorted : allSorted.slice(0, limit)
  const sortableColumns = columns.filter((c) => c.sortable !== false)
  return (
    <>
      <div className="mobile-sortbar mobile-only">
        <label htmlFor={`sort-${id}`}>Sortera</label>
        <select id={`sort-${id}`} value={sort?.key || ''}
          onChange={(e) => choose(e.target.value)}>
          {sortableColumns.map((c) => <option key={c.key} value={c.key}>{c.label}</option>)}
        </select>
        <button onClick={() => toggle(sort?.key || sortableColumns[0]?.key)}
          title="Växla sorteringsriktning">
          {sort?.dir === 'desc' ? 'Fallande ↓' : 'Stigande ↑'}
        </button>
      </div>
      <div className={`${wrapperClassName}${renderCard ? ' desktop-only' : ''}`}>
        <table className={`sorttable ${className || ''}`}>
          <thead><tr>{columns.map((c) => (
            <th key={c.key} title={c.title}
              className={c.sortable === false ? '' : 'sortable'}
              onClick={c.sortable === false ? undefined : () => toggle(c.key)}>
              {c.label}{sort?.key === c.key ? (sort.dir === 'desc' ? ' ▼' : ' ▲') : ''}
            </th>))}
          </tr></thead>
          <tbody>{sorted.map(renderRow)}</tbody>
        </table>
      </div>
      {renderCard && (
        <div className="sortcards mobile-only">{sorted.map(renderCard)}</div>
      )}
    </>
  )
}
