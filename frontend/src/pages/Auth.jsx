import React, { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

const API = import.meta.env.VITE_API_URL || 'http://localhost:8002'

export default function Auth({ mode }) {
  const navigate = useNavigate()
  const [formData, setFormData] = useState({ name: '', email: '', password: '', role: 'maker', shop_name: '' })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const handleSubmit = async (e) => {
    e.preventDefault()
    setLoading(true)
    setError('')

    const endpoint = mode === 'signup' ? '/auth/signup' : '/auth/login'

    try {
      const res = await fetch(`${API}${endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(formData)
      })

      const data = await res.json()
      if (res.ok) {
        localStorage.setItem('craftproof_token', data.access_token)
        localStorage.setItem('craftproof_user', JSON.stringify({ name: data.name, role: data.role, id: data.user_id }))
        navigate('/dashboard')
        window.location.reload()
      } else {
        setError(data.detail || 'Something went wrong')
      }
    } catch (err) {
      setError('Cannot reach the server. Is the backend running?')
    } finally {
      setLoading(false)
    }
  }

  const update = (field, value) => setFormData(prev => ({ ...prev, [field]: value }))

  return (
    <div className="card" style={{ maxWidth: '420px', margin: '2rem auto' }}>
      <h2 style={{ marginBottom: '1.5rem' }}>{mode === 'signup' ? 'Join CraftProof' : 'Welcome Back'}</h2>

      {error && (
        <div className="badge badge-error" style={{ width: '100%', marginBottom: '1rem', justifyContent: 'center' }}>
          {error}
        </div>
      )}

      <form onSubmit={handleSubmit}>
        {mode === 'signup' && (
          <>
            <div className="form-group">
              <label>Your Name</label>
              <input type="text" className="input" required value={formData.name} onChange={e => update('name', e.target.value)} />
            </div>
            <div className="form-group">
              <label>I am a…</label>
              <select className="select" value={formData.role} onChange={e => update('role', e.target.value)}>
                <option value="maker">Artisan / Maker</option>
                <option value="seller">Gallery / Shop</option>
              </select>
            </div>
            {formData.role === 'seller' && (
              <div className="form-group">
                <label>Shop / Gallery Name</label>
                <input type="text" className="input" value={formData.shop_name} onChange={e => update('shop_name', e.target.value)} />
              </div>
            )}
          </>
        )}
        <div className="form-group">
          <label>Email</label>
          <input type="email" className="input" required value={formData.email} onChange={e => update('email', e.target.value)} />
        </div>
        <div className="form-group">
          <label>Password</label>
          <input type="password" className="input" required value={formData.password} onChange={e => update('password', e.target.value)} />
        </div>
        <button type="submit" className="btn" style={{ width: '100%' }} disabled={loading}>
          {loading ? 'Please wait…' : (mode === 'signup' ? 'Create Account' : 'Sign In')}
        </button>
      </form>

      <p style={{ textAlign: 'center', marginTop: '1.5rem', fontFamily: 'var(--font-sans)', fontSize: '0.9rem', color: 'var(--color-muted)' }}>
        {mode === 'signup'
          ? <>Already have an account? <Link to="/login">Sign in</Link></>
          : <>Don't have an account? <Link to="/signup">Sign up</Link></>
        }
      </p>
    </div>
  )
}
