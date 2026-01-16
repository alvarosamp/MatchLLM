import * as XLSX from 'xlsx'

export function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

function escCsvCell(value: any): string {
  const s = value == null ? '' : String(value)
  if (/[",\n\r]/.test(s)) return `"${s.replace(/"/g, '""')}"`
  return s
}

export function toCsv(rows: Record<string, any>[], columns: string[]): string {
  const header = columns.map(escCsvCell).join(',')
  const lines = rows.map((r) => columns.map((c) => escCsvCell(r[c])).join(','))
  return [header, ...lines].join('\n')
}

export function csvBlob(csv: string): Blob {
  return new Blob([csv], { type: 'text/csv;charset=utf-8' })
}

export function xlsxBlobFromRows(
  sheets: Array<{ name: string; rows: Record<string, any>[]; columns?: string[] }>
): Blob {
  const wb = XLSX.utils.book_new()
  for (const sheet of sheets) {
    const cols = sheet.columns ?? Object.keys(sheet.rows?.[0] ?? {})
    const data = [cols, ...sheet.rows.map((r) => cols.map((c) => r[c]))]
    const ws = XLSX.utils.aoa_to_sheet(data)
    XLSX.utils.book_append_sheet(wb, ws, sheet.name.slice(0, 31))
  }
  const out = XLSX.write(wb, { type: 'array', bookType: 'xlsx' })
  return new Blob([out], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })
}
