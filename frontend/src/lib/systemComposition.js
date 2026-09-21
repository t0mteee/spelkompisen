export function systemComposition(sys) {
  const rows = Array.isArray(sys?.rows) && sys.rows.length ? sys.rows : null
  return (sys?.picks || []).map((pick, col) => ({
    ...pick,
    signs: ['1', 'X', '2'].map(sign => {
      const count = rows ? rows.filter(row => row[col] === sign).length : null
      return { sign, selected: pick.signs.includes(sign), count,
        share: rows ? count / rows.length : null }
    }),
  }))
}
