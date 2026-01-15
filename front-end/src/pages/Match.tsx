import React, { useState } from 'react'
import { Link } from 'react-router-dom'
import { apiFetch } from '../api/client'

type MatchMultipleRequest = {
  produto: { nome: string; atributos: Record<string, any> }
  edital_ids: number[]
  consulta: string
  model?: string | null
  use_requisitos?: boolean
  email?: string | null
}

export default function Match() {
  const [produtoNome, setProdutoNome] = useState('Produto teste')
  const [atributosJson, setAtributosJson] = useState('{"exemplo":"valor"}')
  const [editalIds, setEditalIds] = useState('1')
  const [consulta, setConsulta] = useState('')
  const [useRequisitos, setUseRequisitos] = useState(false)
  const [out, setOut] = useState<any>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  async function run() {
    setError(null)
    setOut(null)
    setLoading(true)
    try {
      const attrs = JSON.parse(atributosJson)
      const ids = editalIds
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean)
        .map((s) => Number(s))
        .filter((n) => Number.isFinite(n))

      const payload: MatchMultipleRequest = {
        produto: { nome: produtoNome, atributos: attrs },
        edital_ids: ids,
        consulta,
        use_requisitos: useRequisitos
      }

      const res = await apiFetch<any>('/editais/match_multiple', {
        method: 'POST',
        body: JSON.stringify(payload)
      })
      setOut(res)
    } catch (e: any) {
      setError(e?.message ?? 'Erro ao rodar match')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="container">
      <div className="nav">
        <div>
          <strong>Match</strong>
          <div className="small">Chama a API protegida por JWT</div>
        </div>
        <div className="right">
          <Link to="/">Home</Link>
          <Link to="/match">Match</Link>
        </div>
      </div>

      <div className="card">
        <div className="row">
          <div>
            <label className="small">Produto (nome)</label>
            <input value={produtoNome} onChange={(e) => setProdutoNome(e.target.value)} />
          </div>
          <div>
            <label className="small">Atributos (JSON)</label>
            <textarea rows={6} value={atributosJson} onChange={(e) => setAtributosJson(e.target.value)} />
          </div>
          <div>
            <label className="small">Edital IDs (separado por vírgula)</label>
            <input value={editalIds} onChange={(e) => setEditalIds(e.target.value)} placeholder="996290707, 123" />
          </div>
          <div>
            <label className="small">Consulta</label>
            <input value={consulta} onChange={(e) => setConsulta(e.target.value)} placeholder="switch 24 portas poe" />
          </div>
          <label className="small">
            <input type="checkbox" checked={useRequisitos} onChange={(e) => setUseRequisitos(e.target.checked)} />{' '}
            Usar requisitos
          </label>

          {error && <div className="small" style={{ color: '#fca5a5' }}>{error}</div>}
          <button disabled={loading} onClick={run}>{loading ? 'Rodando...' : 'Rodar match'}</button>

          {out && (
            <div>
              <div className="small">Resposta</div>
              <pre>{JSON.stringify(out, null, 2)}</pre>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
