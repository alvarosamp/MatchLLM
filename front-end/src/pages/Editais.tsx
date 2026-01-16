import React, { useEffect, useMemo, useState } from 'react'
import TopNav from '../components/TopNav'
import { apiFetch } from '../api/client'

type UploadResp = {
  message?: string
  edital_id?: number
  total_chunks?: number
}

export default function Editais() {
  const [files, setFiles] = useState<File[]>([])
  const [ids, setIds] = useState<number[]>([])
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [availableIds, setAvailableIds] = useState<number[] | null>(null)

  const accept = useMemo(() => '.pdf,application/pdf', [])

  useEffect(() => {
    apiFetch<number[]>('/editais/ids')
      .then(setAvailableIds)
      .catch(() => setAvailableIds(null))
  }, [])

  async function uploadAll() {
    setError(null)
    setIds([])
    if (!files.length) {
      setError('Selecione um ou mais PDFs.')
      return
    }

    setLoading(true)
    try {
      const got: number[] = []
      for (const file of files) {
        const form = new FormData()
        form.append('file', file)
        const res = await apiFetch<UploadResp>('/editais/upload', { method: 'POST', body: form })
        if (typeof res.edital_id === 'number') got.push(res.edital_id)
      }
      setIds(got)
      // refresh list
      try {
        const list = await apiFetch<number[]>('/editais/ids')
        setAvailableIds(list)
      } catch {
        // ignore
      }
    } catch (e: any) {
      setError(e?.message ?? 'Falha ao enviar editais')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="container">
      <TopNav title="Editais" subtitle="Upload de um ou vários PDFs" />

      <div className="card">
        <div className="row">
          <div>
            <label className="small">Enviar edital(is) em PDF</label>
            <input
              type="file"
              accept={accept}
              multiple
              onChange={(e) => setFiles(Array.from(e.target.files ?? []))}
            />
            <div className="small" style={{ marginTop: 8 }}>
              A API vai processar e indexar cada edital.
            </div>
          </div>

          {error && (
            <div className="small" style={{ color: '#fca5a5' }}>
              {error}
            </div>
          )}

          <button disabled={loading} onClick={uploadAll}>
            {loading ? 'Enviando...' : 'Processar todos'}
          </button>

          {ids.length > 0 && (
            <div>
              <h3>IDs processados</h3>
              <pre>{ids.join(', ')}</pre>
              <div className="small">Use esses IDs na tela de Match.</div>
            </div>
          )}

          {availableIds && (
            <div>
              <h3>IDs disponíveis (já indexados)</h3>
              <pre>{availableIds.length ? availableIds.join(', ') : '(nenhum)'}</pre>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
