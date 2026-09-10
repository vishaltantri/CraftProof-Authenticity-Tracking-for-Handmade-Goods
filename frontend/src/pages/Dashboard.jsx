import React, { useState, useEffect } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { QRCodeSVG } from 'qrcode.react'

const API = import.meta.env.VITE_API_URL || 'http://localhost:8002'

export default function Dashboard() {
  const navigate = useNavigate()
  const [pieces, setPieces] = useState([])
  const [users, setUsers] = useState([])
  const [showNew, setShowNew] = useState(false)
  const [newPiece, setNewPiece] = useState({ title: '', description: '', materials: '' })
  const [transferData, setTransferData] = useState({ to_user_id: '', to_name: '', note: '' })
  const [activeTransfer, setActiveTransfer] = useState(null)
  const [creating, setCreating] = useState(false)

  const token = localStorage.getItem('craftproof_token')

  useEffect(() => {
    if (!token) {
      navigate('/login')
      return
    }
    fetchPieces()
    fetchUsers()
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
        fetchPieces()
      }
    } catch { /* ignore */ }
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
        fetchPieces()
      }
    } catch { /* ignore */ }
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem', marginBottom: '2rem' }}>
        <h2 style={{ margin: 0 }}>My Studio / Inventory</h2>
        <button className="btn" onClick={() => setShowNew(!showNew)}>
          {showNew ? '✕ Cancel' : '+ Register New Piece'}
        </button>
      </div>

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
              <QRCodeSVG value={`${window.location.origin}/c/${p.certificate_code}`} size={140} />
            </div>
            <div style={{ marginTop: '0.5rem', fontFamily: 'monospace', fontSize: '0.9rem', letterSpacing: '2px', color: 'var(--color-muted)' }}>
              {p.certificate_code}
            </div>
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
    </div>
  )
}
