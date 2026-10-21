import React, { useState, useEffect } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { QRCodeSVG } from 'qrcode.react'
import { Download, Store } from 'lucide-react'

import { API } from '../api'

export default function Dashboard() {
  const navigate = useNavigate()
  const [pieces, setPieces] = useState([])
  const [users, setUsers] = useState([])
  const [showNew, setShowNew] = useState(false)
  const [newPiece, setNewPiece] = useState({ title: '', description: '', materials: '' })
  const [transferData, setTransferData] = useState({ to_user_id: '', to_name: '', note: '' })
  const [activeTransfer, setActiveTransfer] = useState(null)
  const [creating, setCreating] = useState(false)
  const [made, setMade] = useState([])
  const [error, setError] = useState('')

  const token = localStorage.getItem('craftproof_token')

  useEffect(() => {
    if (!token) {
      navigate('/login')
      return
    }
    fetchPieces()
    fetchUsers()
    fetchMade()
  }, [])

  const fetchPieces = async () => {
    try {
      const res = await fetch(`${API}/pieces/mine`, {
        headers: { 'Authorization': `Bearer ${token}` }
      })
      if (res.ok) setPieces(await res.json())
      else if (res.status === 401) navigate('/login')
    } catch { /* server down */ }
  }

  const fetchMade = async () => {
    try {
      const res = await fetch(`${API}/pieces/made`, {
        headers: { 'Authorization': `Bearer ${token}` }
      })
      if (res.ok) setMade(await res.json())
    } catch { /* ignore */ }
  }

  const fetchUsers = async () => {
    try {
      const res = await fetch(`${API}/users`)
      if (res.ok) setUsers(await res.json())
    } catch { /* ignore */ }
  }

  const handleCreate = async (e) => {
    e.preventDefault()
    setCreating(true)
    try {
      const res = await fetch(`${API}/pieces`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
        body: JSON.stringify(newPiece)
      })
      if (res.ok) {
        setShowNew(false)
        setNewPiece({ title: '', description: '', materials: '' })
        setError('')
        fetchPieces()
        fetchMade()
      } else {
        const data = await res.json().catch(() => ({}))
        setError(data.detail || 'Could not create the certificate.')
      }
    } catch {
      setError('Cannot reach the server.')
    }
    setCreating(false)
  }

  const handleTransfer = async (e, pieceId) => {
    e.preventDefault()
    const payload = {
      to_user_id: transferData.to_user_id ? parseInt(transferData.to_user_id) : null,
      to_name: transferData.to_name || null,
      note: transferData.note
    }
    try {
      const res = await fetch(`${API}/pieces/${pieceId}/transfer`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
        body: JSON.stringify(payload)
      })
      if (res.ok) {
        setActiveTransfer(null)
        setTransferData({ to_user_id: '', to_name: '', note: '' })
        setError('')
        fetchPieces()
        fetchMade()
      } else {
        const data = await res.json().catch(() => ({}))
        setError(data.detail || 'Could not record the transfer.')
      }
    } catch {
      setError('Cannot reach the server.')
    }
  }

  // Render the on-screen QR into a printable PNG label with the code underneath.
  const downloadQr = (code) => {
    const svg = document.getElementById(`qr-${code}`)
    if (!svg) return
    const xml = new XMLSerializer().serializeToString(svg)
    const img = new Image()
    img.onload = () => {
      const size = 600, pad = 40, caption = 60
      const canvas = document.createElement('canvas')
      canvas.width = size + pad * 2
      canvas.height = size + pad * 2 + caption
      const ctx = canvas.getContext('2d')
      ctx.fillStyle = '#ffffff'
      ctx.fillRect(0, 0, canvas.width, canvas.height)
      ctx.drawImage(img, pad, pad, size, size)
      ctx.fillStyle = '#1a1814'
      ctx.font = '32px monospace'
      ctx.textAlign = 'center'
      ctx.fillText(code, canvas.width / 2, size + pad + 42)
      const link = document.createElement('a')
      link.href = canvas.toDataURL('image/png')
      link.download = `craftproof-${code}.png`
      link.click()
    }
    img.src = 'data:image/svg+xml;base64,' + btoa(unescape(encodeURIComponent(xml)))
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem', marginBottom: '2rem' }}>
        <h2 style={{ margin: 0 }}>My Studio / Inventory</h2>
        <button className="btn" onClick={() => setShowNew(!showNew)}>
          {showNew ? '✕ Cancel' : '+ Register New Piece'}
        </button>
      </div>

      {error && (
        <div className="badge badge-error" style={{ width: '100%', marginBottom: '1rem', justifyContent: 'center' }}>
          {error}
        </div>
      )}

      {showNew && (
        <div className="card">
          <h3>Register a Handmade Piece</h3>
          <form onSubmit={handleCreate}>
            <div className="form-group">
              <label>Title</label>
              <input className="input" required placeholder="e.g. Hand-thrown ceramic vase" value={newPiece.title} onChange={e => setNewPiece({ ...newPiece, title: e.target.value })} />
            </div>
            <div className="form-group">
              <label>Materials</label>
              <input className="input" placeholder="e.g. Stoneware clay, ash glaze" value={newPiece.materials} onChange={e => setNewPiece({ ...newPiece, materials: e.target.value })} />
            </div>
            <div className="form-group">
              <label>Story / Description</label>
              <textarea className="textarea" rows="3" placeholder="Tell the story of this piece…" value={newPiece.description} onChange={e => setNewPiece({ ...newPiece, description: e.target.value })} />
            </div>
            <button type="submit" className="btn" disabled={creating}>
              {creating ? 'Creating…' : 'Create Digital Certificate'}
            </button>
          </form>
        </div>
      )}

      {pieces.length === 0 && !showNew && (
        <div className="card" style={{ textAlign: 'center', padding: '3rem', color: 'var(--color-faint)' }}>
          <p style={{ fontSize: '1.1rem' }}>No pieces currently in your possession.</p>
          <p style={{ fontSize: '0.9rem' }}>Click "+ Register New Piece" to get started.</p>
        </div>
      )}

      {pieces.map(p => (
        <div key={p.id} className="card card-flex" style={{ display: 'flex', gap: '2rem', flexWrap: 'wrap' }}>
          <div style={{ textAlign: 'center', flexShrink: 0 }}>
            <div style={{ padding: '1rem', background: '#fff', border: '1px solid var(--color-border)', borderRadius: '6px', display: 'inline-block' }}>
              <QRCodeSVG id={`qr-${p.certificate_code}`} value={`${window.location.origin}/c/${p.certificate_code}`} size={140} />
            </div>
            <div style={{ marginTop: '0.5rem', fontFamily: 'monospace', fontSize: '0.9rem', letterSpacing: '2px', color: 'var(--color-muted)' }}>
              {p.certificate_code}
            </div>
            <button className="btn btn-outline btn-sm" style={{ marginTop: '0.6rem' }} onClick={() => downloadQr(p.certificate_code)}>
              <Download size={13} style={{ verticalAlign: '-2px', marginRight: '0.4rem' }} />
              Download tag
            </button>
          </div>

          <div style={{ flex: 1, minWidth: '200px' }}>
            <h3 style={{ marginBottom: '0.3rem' }}>{p.title}</h3>
            {p.description && <p style={{ color: 'var(--color-muted)', fontSize: '0.9rem', margin: '0.3rem 0' }}>{p.description}</p>}
            {p.materials && <p style={{ fontSize: '0.85rem', margin: '0.3rem 0' }}><strong>Materials:</strong> {p.materials}</p>}

            <div className="action-row" style={{ marginTop: '1.5rem', display: 'flex', gap: '0.8rem', flexWrap: 'wrap' }}>
              <Link to={`/c/${p.certificate_code}`} className="btn btn-outline btn-sm">View Certificate</Link>
              <button className="btn btn-sm" onClick={() => {
                setActiveTransfer(activeTransfer === p.id ? null : p.id)
                setTransferData({ to_user_id: '', to_name: '', note: '' })
              }}>
                {activeTransfer === p.id ? '✕ Cancel' : 'Transfer'}
              </button>
            </div>

            {activeTransfer === p.id && (
              <div className="detail-section" style={{ marginTop: '1rem' }}>
                <h4 style={{ marginBottom: '1rem' }}>Transfer this piece</h4>
                <form onSubmit={e => handleTransfer(e, p.id)}>
                  <div className="form-group">
                    <label>Transfer to registered user (optional)</label>
                    <select className="select" value={transferData.to_user_id} onChange={e => setTransferData({ ...transferData, to_user_id: e.target.value })}>
                      <option value="">-- External Buyer (no account) --</option>
                      {users.filter(u => u.id !== p.current_owner_id).map(u => (
                        <option key={u.id} value={u.id}>{u.shop_name || u.name} ({u.role})</option>
                      ))}
                    </select>
                  </div>
                  {!transferData.to_user_id && (
                    <div className="form-group">
                      <label>Buyer's Name</label>
                      <input className="input" placeholder="e.g. John Doe" value={transferData.to_name} onChange={e => setTransferData({ ...transferData, to_name: e.target.value })} />
                    </div>
                  )}
                  <div className="form-group">
                    <label>Transfer Note</label>
                    <input className="input" placeholder="e.g. Sold at craft fair" value={transferData.note} onChange={e => setTransferData({ ...transferData, note: e.target.value })} />
                  </div>
                  <button type="submit" className="btn">Confirm & Sign Transfer</button>
                </form>
              </div>
            )}
          </div>
        </div>
      ))}

      {/* Pieces that have left the studio — still worth following. */}
      {made.filter(p => !p.still_held).length > 0 && (
        <div style={{ marginTop: '3rem' }}>
          <h3 style={{ marginBottom: '0.3rem' }}>Pieces You've Made</h3>
          <p style={{ color: 'var(--color-faint)', fontFamily: 'var(--font-sans)', fontSize: '0.88rem', marginTop: 0 }}>
            These have moved on, but their certificates are still live.
          </p>
          <div className="card" style={{ padding: '0.5rem 0' }}>
            {made.filter(p => !p.still_held).map(p => (
              <div key={p.id} className="past-piece">
                <div>
                  <div style={{ fontWeight: 600 }}>{p.title}</div>
                  <div style={{ fontFamily: 'var(--font-sans)', fontSize: '0.85rem', color: 'var(--color-muted)' }}>
                    Now with {p.holder} · {p.transfers} {p.transfers === 1 ? 'handover' : 'handovers'}
                  </div>
                  {/* A maker normally never finds out their work was resold. */}
                  {p.marketplace && (
                    <div style={{ fontFamily: 'var(--font-sans)', fontSize: '0.82rem', color: 'var(--color-faint)', marginTop: '0.15rem', display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
                      <Store size={12} />
                      Resold on {p.marketplace.source} to {p.marketplace.buyer_name}
                    </div>
                  )}
                </div>
                <Link to={`/c/${p.certificate_code}`} className="btn btn-outline btn-sm">View Certificate</Link>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
