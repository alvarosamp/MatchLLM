import React, { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { apiFetch } from '../api/client'

export default function Register() {
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
      await apiFetch('/auth/register', {
        method: 'POST',
        body: JSON.stringify({ email, password })
      })
      nav('/login')
    } catch (err: any) {
      setError(err?.message ?? 'Erro ao registrar')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="container">
      <div className="card" style={{ maxWidth: 520, margin: '40px auto' }}>
        <h2>Criar conta</h2>
        <p className="small">Cria usuário no banco e habilita login.</p>
        <form className="row" onSubmit={onSubmit}>
          <div>
            <label className="small">Email</label>
            <input value={email} onChange={(e) => setEmail(e.target.value)} placeholder="voce@empresa.com" />
          </div>
          <div>
            <label className="small">Senha</label>
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="min 6" />
          </div>
          {error && <div className="small" style={{ color: '#fca5a5' }}>{error}</div>}
          <button disabled={loading}>{loading ? 'Criando...' : 'Criar'}</button>
        </form>
        <div style={{ marginTop: 12 }} className="small">
          Já tem conta? <Link to="/login">Entrar</Link>
        </div>
      </div>
    </div>
  )
}
