import React, { useEffect, useMemo, useState } from 'react'
import TopNav from '../components/TopNav'
import { apiFetch } from '../api/client'

type ProdutoRow = {
  id: number
  nome: string
  atributos_json: any
  criado_em?: string
}

type UploadProdutoResp = {
  message?: string
  produto?: any
}

export default function Datasheet() {
  const [files, setFiles] = useState<File[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [out, setOut] = useState<any>(null)
  const [produtos, setProdutos] = useState<ProdutoRow[] | null>(null)

  const accept = useMemo(() => '.pdf,application/pdf', [])

  async function refreshProdutos() {
    try {
      const list = await apiFetch<ProdutoRow[]>('/produtos')
      setProdutos(list)
    } catch {
      setProdutos(null)
    }
  }

  useEffect(() => {
    refreshProdutos()
  }, [])

  async function uploadAll() {
    setError(null)
    setOut(null)
    if (!files.length) {
      setError('Selecione um ou mais PDFs de datasheet.')
      return
    }

    setLoading(true)
    try {
      const results: any[] = []
      for (const file of files) {
        const form = new FormData()
        form.append('file', file)
        const res = await apiFetch<UploadProdutoResp>('/produtos/upload', { method: 'POST', body: form })
        results.push({ file: file.name, response: res })
      }
      setOut(results)
      await refreshProdutos()
    } catch (e: any) {
      setError(e?.message ?? 'Falha ao processar datasheet')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="container">
      <TopNav title="Datasheet" subtitle="Extrai produto a partir de PDF e salva no banco" />

      <div className="card">
        <div className="row">
          <div>
            <label className="small">Enviar datasheet(s) em PDF</label>
            <input
              type="file"
              accept={accept}
              multiple
              onChange={(e) => setFiles(Array.from(e.target.files ?? []))}
            />
            <div className="small" style={{ marginTop: 8 }}>
              Obs: o Streamlit aceita TXT também, mas a API atual processa PDF.
            </div>
          </div>

          {error && (
            <div className="small" style={{ color: '#fca5a5' }}>
              {error}
            </div>
          )}

          <button disabled={loading} onClick={uploadAll}>
            {loading ? 'Processando...' : 'Extrair e salvar produto(s)'}
          </button>

          {out && (
            <div>
              <h3>Resultado</h3>
              <pre>{JSON.stringify(out, null, 2)}</pre>
            </div>
          )}

          <div>
            <h3>Produtos no banco</h3>
            {produtos ? (
              <pre>{JSON.stringify(produtos.map((p) => ({ id: p.id, nome: p.nome })), null, 2)}</pre>
            ) : (
              <div className="small">Não foi possível listar produtos.</div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
