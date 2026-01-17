import React from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import Login from './pages/Login'
import Register from './pages/Register'
import Home from './pages/Home'
import Match from './pages/Match'
import Editais from './pages/Editais'
import Datasheet from './pages/Datasheet'
import Dataset from './pages/Dataset'
import { getToken } from './auth/token'

function Protected({ children }: { children: React.ReactNode }) {
  const token = getToken()
  if (!token) return <Navigate to="/login" replace />
  return <>{children}</>
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />
      <Route
        path="/"
        element={
          <Protected>
            <Home />
          </Protected>
        }
      />
      <Route
        path="/editais"
        element={
          <Protected>
            <Editais />
          </Protected>
        }
      />
      <Route
        path="/datasheet"
        element={
          <Protected>
            <Datasheet />
          </Protected>
        }
      />
      <Route
        path="/dataset"
        element={
          <Protected>
            <Dataset />
          </Protected>
        }
      />
      <Route
        path="/match"
        element={
          <Protected>
            <Match />
          </Protected>
        }
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
