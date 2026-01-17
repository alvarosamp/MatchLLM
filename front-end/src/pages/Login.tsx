import React, { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { apiFetch } from '../api/client'
import { setToken } from '../auth/token'

type TokenResponse = { access_token: string; token_type: string }

export default function Login() {
  const nav = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      const res = await apiFetch<TokenResponse>('/auth/login', {
        method: 'POST',
        body: JSON.stringify({ email, password })
      })
      setToken(res.access_token)
      nav('/')
    } catch (err: any) {
      setError(err?.message ?? 'Erro ao logar')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="container">
      <div className="card" style={{ maxWidth: 520, margin: '40px auto' }}>
        <h2>Entrar</h2>
        <p className="small">Use seu email e senha para obter o JWT.</p>
        <form className="row" onSubmit={onSubmit}>
          <div>
            <label className="small">Email</label>
            <input value={email} onChange={(e) => setEmail(e.target.value)} placeholder="voce@empresa.com" />
          </div>
          <div>
            <label className="small">Senha</label>
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
          </div>
          {error && <div className="small" style={{ color: '#fca5a5' }}>{error}</div>}
          <button disabled={loading}>{loading ? 'Entrando...' : 'Entrar'}</button>
        </form>
        <div style={{ marginTop: 12 }} className="small">
          Não tem conta? <Link to="/register">Criar agora</Link>
        </div>
      </div>
    </div>
  )
}
