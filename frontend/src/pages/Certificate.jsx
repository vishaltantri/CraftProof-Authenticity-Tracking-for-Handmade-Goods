import React, { useState, useEffect } from 'react'
import { useParams } from 'react-router-dom'
import { CheckCircle, AlertTriangle } from 'lucide-react'

const API = import.meta.env.VITE_API_URL || 'http://localhost:8002'

export default function Certificate() {
  const { code } = useParams()
  const [data, setData] = useState(null)
  const [error, setError] = useState(false)
  const [showTech, setShowTech] = useState(false)

  useEffect(() => {
    fetch(`${API}/c/${code}`)
      .then(res => {
        if (!res.ok) throw new Error('Not found')
        return res.json()
      })
      .then(setData)
      .catch(() => setError(true))
  }, [code])

  if (error) {
    return (
      <div style={{ textAlign: 'center', marginTop: '4rem' }}>
        <h2>Certificate not found</h2>
        <p style={{ color: 'var(--color-muted)' }}>The code "{code}" doesn't match any registered piece.</p>
      </div>
    )
  }

  if (!data) {
    return <div style={{ textAlign: 'center', marginTop: '4rem', color: 'var(--color-faint)' }}>Verifying certificate…</div>
  }

  const formatDate = (ts) => {
    try {
      const d = new Date(ts)
      return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })
    } catch {
      return ts
    }
  }

  return (
    <div className="card" style={{ maxWidth: '620px', margin: '2rem auto', padding: '0', overflow: 'hidden' }}>
      {/* Header */}
      <div style={{ padding: '2.5rem 2.5rem 2rem', textAlign: 'center', borderBottom: '1px solid var(--color-border)' }}>
        <h2 style={{ fontSize: '1.8rem', marginBottom: '0.3rem' }}>{data.piece.title}</h2>
        <p style={{ color: 'var(--color-muted)', fontStyle: 'italic', marginBottom: '0.3rem', fontSize: '1rem' }}>
          by {data.piece.maker_name}
        </p>
        {data.piece.description && (
          <p style={{ color: 'var(--color-faint)', fontSize: '0.9rem', marginBottom: '1.5rem' }}>{data.piece.description}</p>
        )}

        {data.verified ? (
          <div className="badge badge-success" style={{ fontSize: '1.05rem', padding: '0.8rem 1.8rem' }}>
            <CheckCircle size={20} /> VERIFIED AUTHENTIC
          </div>
        ) : (
          <div className="badge badge-error" style={{ fontSize: '1.05rem', padding: '0.8rem 1.8rem', flexDirection: 'column', display: 'inline-flex' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <AlertTriangle size={20} /> WARNING: ALTERED RECORD
            </div>
            <span style={{ fontSize: '0.8rem', marginTop: '0.4rem', fontWeight: 'normal' }}>
              This certificate cannot be trusted. ({data.reason})
            </span>
          </div>
        )}
      </div>

      {/* Timeline */}
      <div style={{ padding: '2rem 2.5rem' }}>
        <h3 style={{ fontSize: '1.15rem', marginBottom: '1.5rem' }}>Ownership History</h3>
        <ul className="timeline">
          {data.timeline.map((event, i) => (
            <li key={i} className="timeline-item">
              <div className="timeline-date">{formatDate(event.timestamp)}</div>
              <div className="timeline-title">
                {i === 0
                  ? `Crafted by ${event.from_name}`
                  : `Transferred to ${event.to_name}`
                }
              </div>
              {event.note && event.note !== 'Piece created' && (
                <div style={{ fontSize: '0.88rem', color: 'var(--color-muted)', marginTop: '0.15rem', fontStyle: 'italic' }}>
                  "{event.note}"
                </div>
              )}
              {i > 0 && (
                <div style={{ fontSize: '0.8rem', color: 'var(--color-success)', marginTop: '0.15rem' }}>
                  ✓ Confirmed by {event.from_name}
                </div>
              )}
            </li>
          ))}
        </ul>
      </div>

      {/* Tech explanation */}
      <div style={{ background: 'var(--color-accent)', padding: '1.2rem 2.5rem', borderTop: '1px solid var(--color-border)' }}>
        <button
          onClick={() => setShowTech(!showTech)}
          style={{ background: 'none', border: 'none', padding: 0, font: 'inherit', color: 'var(--color-ink)', cursor: 'pointer', fontWeight: 600, display: 'flex', justifyContent: 'space-between', width: '100%', fontFamily: 'var(--font-sans)', fontSize: '0.9rem' }}
        >
          <span>How is this verified?</span>
          <span>{showTech ? '▾' : '▸'}</span>
        </button>

        {showTech && (
          <div style={{ marginTop: '1rem', fontSize: '0.9rem', color: 'var(--color-muted)', fontFamily: 'var(--font-sans)', lineHeight: 1.7 }}>
            <p style={{ marginTop: 0 }}>
              Every time this piece changed hands, the person handing it over digitally confirmed the transfer — like a tamper-proof signature that can't be forged or edited after the fact.
            </p>
            <p>
              All these confirmations are also recorded in a shared public ledger, so even we (CraftProof) can't quietly alter this history without it being detectable.
            </p>
            <div style={{ marginTop: '1rem', paddingTop: '1rem', borderTop: '1px solid var(--color-border)' }}>
              <a href={`${API}/c/${code}`} target="_blank" rel="noopener noreferrer" style={{ color: 'var(--color-faint)', fontSize: '0.85rem' }}>
                View raw verification data (JSON) →
              </a>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
