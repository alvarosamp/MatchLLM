import React from 'react'
import { Link, useLocation } from 'react-router-dom'
import { clearToken } from '../auth/token'

type NavItem = {
  to: string
  label: string
}

const items: NavItem[] = [
  { to: '/', label: 'Home' },
  { to: '/editais', label: 'Editais' },
  { to: '/datasheet', label: 'Datasheet' },
  { to: '/dataset', label: 'Dataset' },
  { to: '/match', label: 'Match' }
]

export default function TopNav({ title, subtitle }: { title: string; subtitle?: string }) {
  const loc = useLocation()

  return (
    <div className="nav">
      <div>
        <strong>{title}</strong>
        {subtitle ? <div className="small">{subtitle}</div> : null}
      </div>
      <div className="right">
        {items.map((it) => {
          const active = loc.pathname === it.to
          return (
            <Link
              key={it.to}
              to={it.to}
              style={
                active
                  ? {
                      borderColor: 'rgba(59,130,246,0.9)',
                      background: 'rgba(59,130,246,0.15)'
                    }
                  : undefined
              }
            >
              {it.label}
            </Link>
          )
        })}
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
  )
}
