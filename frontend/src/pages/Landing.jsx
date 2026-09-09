import React, { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

export default function Landing() {
  const [code, setCode] = useState('')
  const navigate = useNavigate()

  const handleVerify = () => {
    const trimmed = code.trim().toUpperCase()
    if (trimmed) navigate(`/c/${trimmed}`)
  }

  return (
    <div style={{ textAlign: 'center', marginTop: '3rem' }}>
      <h1 style={{ fontSize: '2.8rem', marginBottom: '0.8rem', lineHeight: 1.2 }}>
        Authenticity you can hold.
      </h1>
      <p style={{ fontSize: '1.15rem', color: 'var(--color-muted)', maxWidth: '560px', margin: '0 auto 2.5rem auto', fontFamily: 'var(--font-sans)', lineHeight: 1.7 }}>
        CraftProof lets you prove a handmade piece is genuine, and see its full ownership history — from the maker's hands to yours.
      </p>

      <div className="card" style={{ maxWidth: '420px', margin: '0 auto 3rem auto', textAlign: 'left' }}>
        <h3 style={{ textAlign: 'center', marginBottom: '1rem' }}>Verify a Piece</h3>
        <p style={{ fontSize: '0.9rem', color: 'var(--color-muted)', textAlign: 'center', fontFamily: 'var(--font-sans)' }}>
          Scan the QR code on the item, or type the short certificate code below:
        </p>
        <input
          type="text"
          className="input"
          placeholder="e.g. AB12CD34"
          value={code}
          onChange={e => setCode(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && handleVerify()}
          style={{ textAlign: 'center', letterSpacing: '3px', fontFamily: 'monospace', fontSize: '1.1rem' }}
        />
        <button className="btn" style={{ width: '100%' }} onClick={handleVerify}>
          Verify Certificate
        </button>
      </div>

      <div style={{ marginTop: '2rem', paddingTop: '2rem', borderTop: '1px solid var(--color-border)' }}>
        <p style={{ fontStyle: 'italic', color: 'var(--color-faint)', fontFamily: 'var(--font-sans)' }}>Are you a maker or gallery?</p>
        <Link to="/signup" className="btn btn-outline" style={{ marginTop: '0.8rem' }}>Join CraftProof</Link>
      </div>
    </div>
  )
}
