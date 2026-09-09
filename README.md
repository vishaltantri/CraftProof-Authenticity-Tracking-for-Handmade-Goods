# CraftProof — Authenticity Tracking for Handmade Goods

A full-stack web application that lets artisans (potters, woodworkers, jewelers, painters) create tamper-proof digital certificates for their handmade pieces. When a piece is sold to a shop/gallery and then to a final customer, each transfer is cryptographically recorded. Anyone can scan a QR code and instantly verify: *who made it, its full ownership history, and whether it's genuinely authentic.*

> **Golden Rule:** Users never see the words "hash," "signature," "Merkle," or "cryptography." They only see: "Verified ✓", "Certificate", "Ownership History." All the cryptography happens invisibly underneath.

## 🏗️ Architecture

```
craftproof/
├── backend/              # Python FastAPI server
│   ├── main.py           # REST API endpoints
│   ├── auth.py           # JWT authentication + bcrypt password hashing
│   ├── database.py       # SQLite schema & connection
│   ├── record.py         # Custody record model with deterministic hashing
│   ├── core.py           # Chain verification & Merkle tree logic
│   ├── crypto_utils.py   # Ed25519 keypair generation, signing, verification
│   ├── merkle.py         # Merkle tree construction & proof generation
│   └── tamper_demo.py    # Admin script to simulate database tampering
└── frontend/             # React + Vite SPA
    └── src/
        ├── App.jsx           # Router + auth-aware navigation
        ├── pages/
        │   ├── Landing.jsx   # Public landing page with certificate lookup
        │   ├── Auth.jsx      # Login / Signup forms
        │   ├── Dashboard.jsx # Maker/Seller inventory + QR codes
        │   └── Certificate.jsx # Public certificate verification page
        └── index.css         # Artisan-themed design system
```

## 🔐 Cryptographic Engine

| Concept | Implementation | What the User Sees |
|---|---|---|
| **Hash Chain** | SHA-256 linked records (`prev_hash → record_hash`) | Unbroken ownership timeline |
| **Digital Signatures** | Ed25519 — each transfer signed by outgoing custodian | "✓ Confirmed by [Name]" |
| **Merkle Proofs** | Binary Merkle tree over all custody records | "✓ Included in the public ledger" |
| **Tamper Detection** | Hash recomputation + signature verification on page load | Green badge or red warning |

## 🚀 Quick Start

### Prerequisites
- Python 3.10+
- Node.js 18+

### Backend

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install fastapi uvicorn cryptography pyjwt bcrypt pydantic
uvicorn main:app --port 8002
```

### Frontend

```bash
cd frontend
npm install
npm run dev -- --port 5174
```

Then open **http://localhost:5174**

## 📋 User Flows

### 1. Maker Registers a Piece
Sign up → Fill a simple form (title, materials, story) → Get a QR code sticker to attach to the physical item.

### 2. Maker Transfers to a Gallery
Click "Transfer" → Select the gallery → Confirm. The transfer is cryptographically signed.

### 3. Gallery Sells to a Buyer
Click "Transfer" → Enter buyer's name (no account needed) → Confirm. The gallery signs the handoff.

### 4. Anyone Verifies
Scan the QR code → See a green "✓ VERIFIED AUTHENTIC" badge + full ownership timeline. No login, no app install, no jargon.

## 🧪 Tamper Detection Demo

```bash
cd backend
source venv/bin/activate
python3 tamper_demo.py 1 0 "FORGED: not actually handmade"
```

Reload the certificate page — the green badge turns red: **"⚠ WARNING: ALTERED RECORD — Record 0 content hash mismatch"**

## 🛠️ API Endpoints

| Method | Endpoint | Auth | Purpose |
|---|---|---|---|
| `POST` | `/auth/signup` | No | Create account (keypair generated invisibly) |
| `POST` | `/auth/login` | No | Login, receive JWT |
| `POST` | `/pieces` | Yes | Register a new piece + genesis record |
| `GET` | `/pieces/mine` | Yes | List pieces you currently hold |
| `POST` | `/pieces/{id}/transfer` | Yes | Transfer to another user or external buyer |
| `GET` | `/c/{code}` | No | Public certificate with server-side verification |
| `GET` | `/users` | No | List registered users |
| `POST` | `/admin/tamper/{piece_id}/{seq}` | No | Demo: silently alter a record |

## 📄 License

MIT
