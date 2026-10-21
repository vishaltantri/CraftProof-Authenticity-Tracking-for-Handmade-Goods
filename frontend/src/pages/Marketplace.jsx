import React, { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { Store, RefreshCw, CheckCircle, AlertTriangle, Link2, ShoppingBag } from 'lucide-react'

import { API } from '../api'

/**
 * ReMarket integration page.
 *
 * Shows three things, in order of how much a reader should trust them:
 *   1. what CraftProof has actually recorded (imported sales — signed,
 *      checkpointed, visible on the certificate)
 *   2. what ReMarket is currently reporting (the live feed — a claim)
 *   3. the connection's health
 *
 * The partner API key never reaches this page. The live feed is read through
 * the CraftProof backend, authenticated with the viewer's own session.
 */
export default function Marketplace() {
  const [status, setStatus] = useState(null)
  const [imports, setImports] = useState([])
  const [feed, setFeed] = useState(null)
  const [feedError, setFeedError] = useState('')
  const [syncing, setSyncing] = useState(false)
  const [message, setMessage] = useState(null)

  const token = localStorage.getItem('craftproof_token')

  const loadStatus = async () => {
    try {
      const res = await fetch(`${API}/integrations/remarket/status`)
      if (res.ok) setStatus(await res.json())
      else setStatus({ configured: false, unreachable: true })
    } catch {
      setStatus({ configured: false, unreachable: true })
    }
  }

  const loadImports = async () => {
    try {
      const res = await fetch(`${API}/integrations/remarket/imports?limit=25`)
      if (res.ok) setImports((await res.json()).imports || [])
    } catch { /* leave the list as it was */ }
  }

  const loadFeed = async () => {
    if (!token) return
    setFeedError('')
    try {
      const res = await fetch(`${API}/integrations/remarket/feed?limit=20`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      const data = await res.json().catch(() => ({}))
      if (res.ok) setFeed(data.sales || [])
      else setFeedError(data.detail || 'Could not read the ReMarket feed.')
    } catch {
      setFeedError('Could not reach the CraftProof server.')
    }
  }

  useEffect(() => {
    loadStatus()
    loadImports()
    loadFeed()
  }, [])

  const syncNow = async () => {
    setSyncing(true)
    setMessage(null)
    try {
      const res = await fetch(`${API}/integrations/remarket/sync-as-user`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
      })
      const data = await res.json().catch(() => ({}))
      if (res.ok) {
        setMessage({ ok: true, data })
        loadStatus(); loadImports(); loadFeed()
      } else {
        setMessage({ ok: false, text: data.detail || 'The sync could not run.' })
      }
    } catch {
      setMessage({ ok: false, text: 'Could not reach the CraftProof server.' })
    }
    setSyncing(false)
  }

  const formatDate = (ts) => {
    if (!ts) return '—'
    const d = new Date(ts.includes('T') ? ts : ts.replace(' ', 'T') + 'Z')
    if (isNaN(d)) return ts
    return d.toLocaleString('en-GB', {
      day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit',
    })
  }

  const connected = status && status.configured
  const label = { fontFamily: 'var(--font-sans)', fontSize: '0.78rem', color: 'var(--color-faint)', textTransform: 'uppercase', letterSpacing: '0.04em' }
  const cell = { fontFamily: 'var(--font-sans)', fontSize: '0.88rem', padding: '0.6rem 0.8rem', borderBottom: '1px solid var(--color-border)', textAlign: 'left', verticalAlign: 'top' }

  return (
    <div style={{ maxWidth: '860px', margin: '0 auto' }}>
      <h2 style={{ marginBottom: '0.5rem' }}>
        <Store size={22} style={{ verticalAlign: '-3px', marginRight: '0.5rem' }} />
        ReMarket
      </h2>
      <p style={{ color: 'var(--color-muted)', fontFamily: 'var(--font-sans)', fontSize: '0.95rem', lineHeight: 1.7 }}>
        ReMarket is a secondhand marketplace. When a seller lists a piece there with its CraftProof
        code and the item sells, CraftProof reads the completed sale and records the buyer as the
        new holder, so the certificate keeps up with the piece instead of stopping at the last
        person who had a CraftProof account.
      </p>

      {/* Connection status */}
      <div className="card" style={{ padding: '1.3rem 1.5rem', margin: '1.5rem 0' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.8rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
            {connected ? (
              <span className="badge badge-success" style={{ fontSize: '0.82rem', padding: '0.35rem 0.8rem' }}>
                <CheckCircle size={14} /> Connected
              </span>
            ) : (
              <span className="badge badge-warning" style={{ fontSize: '0.82rem', padding: '0.35rem 0.8rem' }}>
                <AlertTriangle size={14} /> Not configured
              </span>
            )}
            {status && status.api_url && (
              <code style={{ fontSize: '0.8rem', color: 'var(--color-faint)' }}>{status.api_url}</code>
            )}
          </div>
          {token && (
            <button className="btn btn-sm" onClick={syncNow} disabled={syncing || !connected}>
              <RefreshCw size={14} style={{ verticalAlign: '-2px', marginRight: '0.4rem' }} />
              {syncing ? 'Checking ReMarket…' : 'Check for new sales'}
            </button>
          )}
        </div>

        {status && connected && (
          <div style={{ display: 'flex', gap: '2.5rem', flexWrap: 'wrap', marginTop: '1.2rem' }}>
            <div>
              <div style={label}>Sales recorded</div>
              <div style={{ fontSize: '1.4rem', fontWeight: 600 }}>{status.imported_sales}</div>
            </div>
            <div>
              <div style={label}>Last checked</div>
              <div style={{ fontFamily: 'var(--font-sans)', fontSize: '0.9rem', marginTop: '0.35rem' }}>
                {formatDate(status.last_sync_at)}
              </div>
            </div>
            <div>
              <div style={label}>Checks every</div>
              <div style={{ fontFamily: 'var(--font-sans)', fontSize: '0.9rem', marginTop: '0.35rem' }}>
                {status.poll_interval_seconds > 0
                  ? `${Math.round(status.poll_interval_seconds / 60)} min`
                  : 'Manual only'}
              </div>
            </div>
          </div>
        )}

        {status && !connected && (
          <p style={{ fontFamily: 'var(--font-sans)', fontSize: '0.88rem', color: 'var(--color-muted)', marginTop: '0.9rem', marginBottom: 0 }}>
            This CraftProof server has no ReMarket credentials yet. Set <code>REMARKET_API_URL</code> and{' '}
            <code>REMARKET_SALE_API_KEY</code> on the backend to switch the connection on.
          </p>
        )}
      </div>

      {/* Result of a manual sync */}
      {message && (
        <div className="detail-section" style={{ marginBottom: '1.5rem' }}>
          {message.ok ? (
            <>
              <strong>
                {message.data.imported > 0
                  ? `Recorded ${message.data.imported} new sale${message.data.imported === 1 ? '' : 's'}.`
                  : 'No new sales to record.'}
              </strong>
              {message.data.skipped && message.data.skipped.length > 0 && (
                <div style={{ fontFamily: 'var(--font-sans)', fontSize: '0.86rem', color: 'var(--color-muted)', marginTop: '0.5rem' }}>
                  {message.data.skipped.length} sale{message.data.skipped.length === 1 ? '' : 's'} left alone for now:
                  <ul style={{ margin: '0.4rem 0 0', paddingLeft: '1.2rem' }}>
                    {message.data.skipped.map((s, i) => (
                      <li key={i}>
                        {s.order_id} — {
                          s.reason === 'item_title_mismatch'
                            ? 'the listing name does not match the certificate, so nothing was changed'
                            : s.reason === 'certificate_not_found'
                              ? 'no certificate with that code exists here'
                              : s.reason
                        }
                      </li>
                    ))}
                  </ul>
                  These are checked again on the next sync.
                </div>
              )}
            </>
          ) : (
            <span style={{ color: 'var(--color-error)' }}>{message.text}</span>
          )}
        </div>
      )}

      {/* Sales CraftProof has actually recorded */}
      <h3 style={{ fontSize: '1.15rem', marginTop: '2rem', marginBottom: '0.4rem' }}>
        Recorded on certificates
      </h3>
      <p style={{ fontFamily: 'var(--font-sans)', fontSize: '0.86rem', color: 'var(--color-muted)', marginTop: 0 }}>
        Each of these added a signed step to a certificate's ownership history.
      </p>

      {imports.length === 0 ? (
        <div className="card" style={{ textAlign: 'center', color: 'var(--color-faint)', padding: '1.8rem' }}>
          <p style={{ margin: 0 }}>No ReMarket sales recorded yet.</p>
        </div>
      ) : (
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: '600px' }}>
            <thead>
              <tr>
                <th style={{ ...cell, ...label }}>Order</th>
                <th style={{ ...cell, ...label }}>Piece</th>
                <th style={{ ...cell, ...label }}>New holder</th>
                <th style={{ ...cell, ...label }}>Certificate</th>
                <th style={{ ...cell, ...label }}>Recorded</th>
              </tr>
            </thead>
            <tbody>
              {imports.map((row) => (
                <tr key={row.order_id}>
                  <td style={cell}><code style={{ fontSize: '0.8rem' }}>{row.order_id}</code></td>
                  <td style={cell}>{row.piece_title}</td>
                  <td style={cell}>{row.buyer_name}</td>
                  <td style={cell}>
                    <Link to={`/c/${row.certificate_code}`}>
                      <Link2 size={12} style={{ verticalAlign: '-1px', marginRight: '0.25rem' }} />
                      {row.certificate_code}
                    </Link>
                  </td>
                  <td style={{ ...cell, color: 'var(--color-faint)' }}>{formatDate(row.imported_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* The partner's live feed */}
      {token && (
        <>
          <h3 style={{ fontSize: '1.15rem', marginTop: '2.5rem', marginBottom: '0.4rem' }}>
            <ShoppingBag size={17} style={{ verticalAlign: '-2px', marginRight: '0.45rem' }} />
            Live on ReMarket
          </h3>
          <p style={{ fontFamily: 'var(--font-sans)', fontSize: '0.86rem', color: 'var(--color-muted)', marginTop: 0 }}>
            What the marketplace is reporting right now. A sale shows as pending until it passes
            CraftProof's checks — the listing name has to match the certificate before anything is
            written to it.
          </p>

          {feedError && (
            <div className="detail-section" style={{ color: 'var(--color-error)' }}>{feedError}</div>
          )}

          {!feedError && feed && feed.length === 0 && (
            <div className="card" style={{ textAlign: 'center', color: 'var(--color-faint)', padding: '1.8rem' }}>
              <p style={{ margin: 0 }}>ReMarket has no completed certificate sales yet.</p>
            </div>
          )}

          {!feedError && feed && feed.length > 0 && (
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: '600px' }}>
                <thead>
                  <tr>
                    <th style={{ ...cell, ...label }}>Order</th>
                    <th style={{ ...cell, ...label }}>Listing</th>
                    <th style={{ ...cell, ...label }}>Buyer</th>
                    <th style={{ ...cell, ...label }}>Code</th>
                    <th style={{ ...cell, ...label }}>State</th>
                  </tr>
                </thead>
                <tbody>
                  {feed.map((sale) => (
                    <tr key={sale.order_id}>
                      <td style={cell}><code style={{ fontSize: '0.8rem' }}>{sale.order_id}</code></td>
                      <td style={cell}>{sale.item_title}</td>
                      <td style={cell}>{sale.buyer_name}</td>
                      <td style={cell}><code style={{ fontSize: '0.8rem' }}>{sale.certificate_code}</code></td>
                      <td style={cell}>
                        {sale.imported ? (
                          <span style={{ color: 'var(--color-success)' }}>✓ Recorded</span>
                        ) : (
                          <span style={{ color: 'var(--color-faint)' }}>Pending checks</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

      {!token && (
        <p style={{ fontFamily: 'var(--font-sans)', fontSize: '0.88rem', color: 'var(--color-faint)', marginTop: '2rem' }}>
          <Link to="/login">Sign in</Link> to see the live ReMarket feed and check for new sales.
        </p>
      )}

      {/* The honest caveat. */}
      <div className="detail-section" style={{ marginTop: '2.5rem' }}>
        <strong>What a marketplace sale does and does not prove</strong>
        <p style={{ fontFamily: 'var(--font-sans)', fontSize: '0.88rem', color: 'var(--color-muted)', lineHeight: 1.7, marginBottom: 0 }}>
          A recorded sale means ReMarket reported it and the listing name matched the certificate.
          It is not proof that the seller was entitled to sell the piece, and buyer names on
          ReMarket are self-reported. Steps added this way are labelled as marketplace-reported
          wherever they appear, and are signed by the integration rather than by the previous
          owner — so nobody reading a certificate is told a marketplace's word came from the
          person who handed the piece over.
        </p>
      </div>

      <p style={{ fontFamily: 'var(--font-sans)', fontSize: '0.88rem', color: 'var(--color-faint)', marginTop: '2rem' }}>
        Building something similar? See the <Link to="/developers">API guide</Link>.
      </p>
    </div>
  )
}
