import React, { useState, useEffect } from 'react'
import { BrowserRouter, Routes, Route, Link, useNavigate } from 'react-router-dom'
import Landing from './pages/Landing'
import Auth from './pages/Auth'
import Dashboard from './pages/Dashboard'
import Certificate from './pages/Certificate'
import Ledger from './pages/Ledger'
import HowItWorks from './pages/HowItWorks'
import Developers from './pages/Developers'
import Marketplace from './pages/Marketplace'

function Nav() {
  const [user, setUser] = useState(null)
  const navigate = useNavigate()

  useEffect(() => {
    const readUser = () => {
      const stored = localStorage.getItem('craftproof_user')
      if (stored) {
        try { setUser(JSON.parse(stored)) } catch { /* ignore */ }
      } else {
        setUser(null)
      }
    }
    readUser()
    // Auth pages dispatch this after sign-in/out so the nav updates without a
    // full page reload — reloading a deep link 404s on static hosts that lack
    // an SPA rewrite rule (e.g. our Render deployment).
    window.addEventListener('craftproof-auth', readUser)
    return () => window.removeEventListener('craftproof-auth', readUser)
  }, [])

  const handleLogout = () => {
    localStorage.removeItem('craftproof_token')
    localStorage.removeItem('craftproof_user')
    setUser(null)
    window.dispatchEvent(new Event('craftproof-auth'))
    navigate('/')
  }

  return (
    <header className="header">
      <Link to="/" className="brand">CraftProof</Link>
      <div className="nav-links">
        <Link to="/how-it-works">How it works</Link>
        <Link to="/ledger">Checkpoints</Link>
        <Link to="/marketplace">ReMarket</Link>
        <Link to="/developers">API</Link>
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
      <Routes>
        {/* The landing page is a full-bleed design with its own header and footer. */}
        <Route path="/" element={<Landing />} />
        <Route
          path="*"
          element={
            <div className="container">
              <Nav />
              <Routes>
                <Route path="/login" element={<Auth mode="login" />} />
                <Route path="/signup" element={<Auth mode="signup" />} />
                <Route path="/dashboard" element={<Dashboard />} />
                <Route path="/c/:code" element={<Certificate />} />
                <Route path="/ledger" element={<Ledger />} />
                <Route path="/how-it-works" element={<HowItWorks />} />
                <Route path="/developers" element={<Developers />} />
                <Route path="/marketplace" element={<Marketplace />} />
              </Routes>
            </div>
          }
        />
      </Routes>
    </BrowserRouter>
  )
}

export default App
