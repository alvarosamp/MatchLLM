import React, { useEffect, useState } from 'react'
import TopNav from '../components/TopNav'
import { apiFetch } from '../api/client'

type ProdutoRow = {
  id: number
  nome: string
  atributos_json: any
  criado_em?: string
}

export default function Dataset() {
  const [nome, setNome] = useState('Meu Produto')
  const [atributosRaw, setAtributosRaw] = useState('{"portas": 24, "poe": true}')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [produtos, setProdutos] = useState<ProdutoRow[] | null>(null)
  const [saved, setSaved] = useState<any>(null)

  async function refresh() {
    try {
      const list = await apiFetch<ProdutoRow[]>('/produtos')
      setProdutos(list)
    } catch {
      setProdutos(null)
    }
  }

  useEffect(() => {
    refresh()
  }, [])

  async function save() {
    setError(null)
    setSaved(null)
    setLoading(true)
    try {
      const attrs = JSON.parse(atributosRaw)
      const body = { nome, atributos: attrs }
      const res = await apiFetch<any>('/produtos/json', {
        method: 'POST',
        body: JSON.stringify(body)
      })
      setSaved(res)
      await refresh()
    } catch (e: any) {
      setError(e?.message ?? 'Falha ao salvar produto')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="container">
      <TopNav title="Dataset" subtitle="Cadastrar produto manualmente (JSON)" />

      <div className="card">
        <div className="row">
          <div>
            <label className="small">Nome do produto</label>
            <input value={nome} onChange={(e) => setNome(e.target.value)} />
          </div>

          <div>
            <label className="small">Atributos do produto (JSON)</label>
            <textarea rows={10} value={atributosRaw} onChange={(e) => setAtributosRaw(e.target.value)} />
          </div>

          {error && (
            <div className="small" style={{ color: '#fca5a5' }}>
              {error}
            </div>
          )}

          <button disabled={loading} onClick={save}>
            {loading ? 'Salvando...' : 'Salvar produto'}
          </button>

          {saved && (
            <div>
              <h3>Salvo</h3>
              <pre>{JSON.stringify(saved, null, 2)}</pre>
            </div>
          )}

          <div>
            <h3>Produtos cadastrados</h3>
            {produtos ? (
              <pre>{JSON.stringify(produtos, null, 2)}</pre>
            ) : (
              <div className="small">Não foi possível listar produtos.</div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
