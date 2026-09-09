import React, { useState, useEffect } from 'react'
import { BrowserRouter, Routes, Route, Link, useNavigate } from 'react-router-dom'
import Landing from './pages/Landing'
import Auth from './pages/Auth'
import Dashboard from './pages/Dashboard'
import Certificate from './pages/Certificate'

function Nav() {
  const [user, setUser] = useState(null)
  const navigate = useNavigate()

  useEffect(() => {
    const stored = localStorage.getItem('craftproof_user')
    if (stored) {
      try { setUser(JSON.parse(stored)) } catch { /* ignore */ }
    }
  }, [])

  const handleLogout = () => {
    localStorage.removeItem('craftproof_token')
    localStorage.removeItem('craftproof_user')
    setUser(null)
    navigate('/')
    window.location.reload()
  }

  return (
    <header className="header">
      <Link to="/" className="brand">CraftProof</Link>
      <div className="nav-links">
        {user ? (
          <>
            <span className="nav-user">Hi, {user.name}</span>
            <Link to="/dashboard">Dashboard</Link>
            <button className="logout-btn" onClick={handleLogout}>Logout</button>
          </>
        ) : (
          <>
            <Link to="/login">Login</Link>
            <Link to="/signup">Sign Up</Link>
          </>
        )}
      </div>
    </header>
  )
}

function App() {
  return (
    <BrowserRouter>
      <div className="container">
        <Nav />
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/login" element={<Auth mode="login" />} />
          <Route path="/signup" element={<Auth mode="signup" />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/c/:code" element={<Certificate />} />
        </Routes>
      </div>
    </BrowserRouter>
  )
}

export default App
