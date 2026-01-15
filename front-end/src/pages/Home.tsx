import React, { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { apiFetch } from '../api/client'
import { clearToken } from '../auth/token'

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
      <div className="nav">
        <div>
          <strong>MatchLLM</strong>
          <div className="small">Front React + JWT</div>
        </div>
        <div className="right">
          <Link to="/">Home</Link>
          <Link to="/match">Match</Link>
          <button
            onClick={() => {
              clearToken()
              window.location.href = '/login'
            }}
          >
            Sair
          </button>
        </div>
      </div>

      <div className="card">
        <h3>Status</h3>
        {error && <div className="small" style={{ color: '#fca5a5' }}>{error}</div>}
        {me ? (
          <div className="small">Logado como: {me.user.email}</div>
        ) : (
          <div className="small">Carregando...</div>
        )}
        <div style={{ marginTop: 12 }} className="small">
          Próximo: usar tela de Match para chamar `/editais/match_multiple`.
        </div>
      </div>
    </div>
  )
}
