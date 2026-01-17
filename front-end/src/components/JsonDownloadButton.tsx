import React from 'react'

type Props = {
  data: unknown
  filename: string
  label?: string
}

export default function JsonDownloadButton({ data, filename, label = 'Baixar JSON' }: Props) {
  function onClick() {
    const json = JSON.stringify(data, null, 2)
    const blob = new Blob([json], { type: 'application/json;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
  }

  return (
    <button type="button" className="btn btn--secondary" onClick={onClick}>
      {label}
    </button>
  )
}
