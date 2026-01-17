import React, { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { apiFetch } from '../api/client'
import TopNav from '../components/TopNav'

type MeResponse = { user: { id: number; email: string } }

export default function Home() {
  const [me, setMe] = useState<MeResponse | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    apiFetch<MeResponse>('/auth/me')
      .then(setMe)
      .catch((e: any) => setError(e?.message ?? 'Erro'))
  }, [])

  return (
    <div className="container">
      <TopNav title="Dashboard - Licitação com IA" subtitle="Equivalente ao Streamlit" />

      <div className="card">
        <h3>Status</h3>
        {error && <div className="small" style={{ color: '#fca5a5' }}>{error}</div>}
        {me ? (
          <div className="small">Logado como: {me.user.email}</div>
        ) : (
          <div className="small">Carregando...</div>
        )}

        <div style={{ marginTop: 14 }}>
          <h3>Como usar (bem mastigado)</h3>
          <ol className="small" style={{ lineHeight: 1.8 }}>
            <li>
              Abra <Link to="/match">Match</Link>
            </li>
            <li>
              Envie um ou vários PDFs de <Link to="/editais">Editais</Link>
            </li>
            <li>
              Envie PDFs de <Link to="/datasheet">Datasheet</Link> (ou cadastre em <Link to="/dataset">Dataset</Link>)
            </li>
            <li>Clique em Rodar Match</li>
            <li>Veja o resumo e o JSON detalhado</li>
          </ol>
        </div>

        <div style={{ marginTop: 10 }}>
          <h3>Outras páginas (opcionais)</h3>
          <ul className="small" style={{ lineHeight: 1.8 }}>
            <li>
              <strong>Datasheet</strong>: extrai e salva o produto no banco
            </li>
            <li>
              <strong>Dataset</strong>: cadastra produto manualmente (JSON)
            </li>
            <li>
              <strong>Editais</strong>: faz upload e pega os IDs
            </li>
          </ul>
        </div>
      </div>
    </div>
  )
}
