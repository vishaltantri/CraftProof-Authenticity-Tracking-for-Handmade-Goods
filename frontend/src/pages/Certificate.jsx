import React, { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import { CheckCircle, AlertTriangle, Stamp, Clock, Copy, Check } from 'lucide-react'

import { API } from '../api'

export default function Certificate() {
  const { code } = useParams()
  const [data, setData] = useState(null)
  const [error, setError] = useState(false)
  const [showTech, setShowTech] = useState(false)
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    fetch(`${API}/c/${code}`)
      .then(res => {
        if (!res.ok) throw new Error('Not found')
        return res.json()
      })
      .then(setData)
      .catch(() => setError(true))
  }, [code])

  const copyLink = async () => {
    try {
      await navigator.clipboard.writeText(window.location.href)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch { /* clipboard unavailable */ }
  }

  if (error) {
    return (
      <div style={{ textAlign: 'center', marginTop: '4rem' }}>
        <h2>Certificate not found</h2>
        <p style={{ color: 'var(--color-muted)' }}>The code "{code}" doesn't match any registered piece.</p>
        <Link to="/" className="btn btn-outline btn-sm" style={{ marginTop: '1rem' }}>Try another code</Link>
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

  // Name the failing check in plain language, for the one event that broke.
  const problemWith = (checks) => {
    if (!checks || checks.ok !== false) return null
    if (!checks.content_ok) return 'The details of this step were changed after it was confirmed.'
    if (!checks.linkage_ok) return 'This step does not follow on from the one before it.'
    if (!checks.signature_ok) return 'The confirmation for this step could not be matched to the person named.'
    return 'This step could not be verified.'
  }

  const ledger = data.ledger || {}

  // A cloned tag means we cannot vouch for the OBJECT, even though the
  // recorded history is intact. The headline verdict must never read
  // "verified authentic" in that state — that badge is exactly the
  // false assurance this whole system exists to remove.
  const cloned = Boolean(data.clone && data.clone.flagged)

  return (
    <div className="card" style={{ maxWidth: '620px', margin: '2rem auto', padding: '0', overflow: 'hidden' }}>
      {/* Header */}
      <div style={{ padding: '2.5rem 2.5rem 2rem', textAlign: 'center', borderBottom: '1px solid var(--color-border)' }}>
        <h2 style={{ fontSize: '1.8rem', marginBottom: '0.3rem' }}>{data.piece.title}</h2>
        <p style={{ color: 'var(--color-muted)', fontStyle: 'italic', marginBottom: '0.3rem', fontSize: '1rem' }}>
          by {data.piece.maker_name}
        </p>
        {data.piece.materials && (
          <p style={{ color: 'var(--color-faint)', fontSize: '0.85rem', fontFamily: 'var(--font-sans)', marginBottom: '0.5rem' }}>
            {data.piece.materials}
          </p>
        )}
        {data.piece.description && (
          <p style={{ color: 'var(--color-faint)', fontSize: '0.9rem', marginBottom: '1.5rem' }}>{data.piece.description}</p>
        )}

        {data.verified && !cloned && (
          <div className="badge badge-success" style={{ fontSize: '1.05rem', padding: '0.8rem 1.8rem' }}>
            <CheckCircle size={20} /> VERIFIED AUTHENTIC
          </div>
        )}
        {data.verified && cloned && (
          <div className="badge badge-warning" style={{ fontSize: '1rem', padding: '0.8rem 1.5rem', flexDirection: 'column', display: 'inline-flex', maxWidth: '100%' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <AlertTriangle size={20} /> OBJECT NOT CONFIRMED
            </div>
            <span style={{ fontSize: '0.8rem', marginTop: '0.4rem', fontWeight: 'normal' }}>
              The recorded history is unaltered, but we cannot confirm the object this tag is on is the original one.
            </span>
          </div>
        )}
        {!data.verified && (
          <div className="badge badge-error" style={{ fontSize: '1.05rem', padding: '0.8rem 1.8rem', flexDirection: 'column', display: 'inline-flex' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <AlertTriangle size={20} /> WARNING: ALTERED RECORD
            </div>
            <span style={{ fontSize: '0.8rem', marginTop: '0.4rem', fontWeight: 'normal' }}>
              This certificate cannot be trusted. ({data.reason})
            </span>
          </div>
        )}

        {/* Physical clone warning (plan W5): this tag has been scanned
            alongside several different physical objects */}
        {cloned && (
          <div className="badge badge-error" style={{ fontSize: '0.95rem', padding: '0.8rem 1.5rem', marginTop: '0.8rem', flexDirection: 'column', display: 'inline-flex', maxWidth: '100%', textAlign: 'left' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <AlertTriangle size={20} /> POSSIBLE TAG CLONING DETECTED
            </div>
            <span style={{ fontSize: '0.8rem', marginTop: '0.4rem', fontWeight: 'normal' }}>
              {data.clone.reason || 'This tag has been shown with several different objects.'}
            </span>
            <span style={{ fontSize: '0.8rem', marginTop: '0.2rem', fontWeight: 'normal' }}>
              Do not trust the object this tag is attached to — check it in person with the maker.
            </span>
          </div>
        )}

        {/* Public-ledger status */}
        {data.verified && ledger.total_records > 0 && (
          <div style={{ marginTop: '1rem', fontFamily: 'var(--font-sans)', fontSize: '0.85rem' }}>
            {ledger.fully_anchored ? (
              <span style={{ color: 'var(--color-success)', display: 'inline-flex', alignItems: 'center', gap: '0.4rem' }}>
                <Stamp size={15} /> Sealed in the <Link to="/ledger" style={{ color: 'var(--color-success)', textDecoration: 'underline' }}>public ledger</Link>
              </span>
            ) : (
              <span style={{ color: 'var(--color-faint)', display: 'inline-flex', alignItems: 'center', gap: '0.4rem' }}>
                <Clock size={15} /> {ledger.anchored_records} of {ledger.total_records} steps sealed in the{' '}
                <Link to="/ledger" style={{ textDecoration: 'underline' }}>public ledger</Link> so far
              </span>
            )}
          </div>
        )}
      </div>

      {/* Timeline */}
      <div style={{ padding: '2rem 2.5rem' }}>
        <h3 style={{ fontSize: '1.15rem', marginBottom: '1.5rem' }}>Ownership History</h3>
        <ul className="timeline">
          {data.timeline.map((event, i) => {
            const problem = problemWith(event.checks)
            return (
              <li key={i} className={`timeline-item${problem ? ' timeline-item-bad' : ''}`}>
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
                {problem ? (
                  <div style={{ fontSize: '0.82rem', color: 'var(--color-error)', marginTop: '0.25rem', fontFamily: 'var(--font-sans)' }}>
                    ⚠ {problem}
                  </div>
                ) : (
                  <div style={{ fontSize: '0.8rem', color: 'var(--color-success)', marginTop: '0.15rem', fontFamily: 'var(--font-sans)' }}>
                    ✓ Confirmed by {event.from_name}
                    {event.checkpoint ? ` · sealed in checkpoint #${event.checkpoint}` : ''}
                  </div>
                )}
              </li>
            )
          })}
        </ul>

        <div style={{ marginTop: '1.5rem', display: 'flex', gap: '0.8rem', flexWrap: 'wrap' }}>
          <button className="btn btn-outline btn-sm" onClick={copyLink}>
            {copied
              ? <><Check size={14} style={{ verticalAlign: '-2px', marginRight: '0.4rem' }} />Link copied</>
              : <><Copy size={14} style={{ verticalAlign: '-2px', marginRight: '0.4rem' }} />Copy link</>}
          </button>
          <Link to="/how-it-works" className="btn btn-outline btn-sm">How is this checked?</Link>
        </div>
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
              Every time this piece changed hands, the person handing it over digitally confirmed the transfer — like a tamper-evident signature: any later edit to that confirmation is caught and shown, rather than being impossible to attempt.
            </p>
            <p>
              All these confirmations are also recorded in a shared public ledger, so even we (CraftProof) can't quietly alter this history without it being detectable.
            </p>
            <div style={{ marginTop: '1rem', paddingTop: '1rem', borderTop: '1px solid var(--color-border)', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
              <a href={`${API}/c/${code}/proof`} target="_blank" rel="noopener noreferrer" style={{ color: 'var(--color-faint)', fontSize: '0.85rem' }}>
                Check it yourself: full verification data (JSON) →
              </a>
              <a href={`${API}/c/${code}`} target="_blank" rel="noopener noreferrer" style={{ color: 'var(--color-faint)', fontSize: '0.85rem' }}>
                View raw certificate data (JSON) →
              </a>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
