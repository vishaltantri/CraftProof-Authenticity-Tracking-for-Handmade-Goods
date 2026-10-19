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
│   ├── verify_cli.py     # Independent verifier — re-checks a certificate without trusting the server
│   ├── test_crypto.py    # Tests for the crypto engine and the attacks it must catch
│   ├── seed.py           # Demo data: makers, galleries, pieces mid-journey
│   └── tamper_demo.py    # Admin script to simulate database tampering
└── frontend/             # React + Vite SPA
    └── src/
        ├── App.jsx           # Router + auth-aware navigation
        ├── pages/
        │   ├── Landing.jsx   # Public landing page with certificate lookup
        │   ├── Auth.jsx      # Login / Signup forms
        │   ├── Dashboard.jsx # Maker/Seller inventory + QR codes + printable tags
        │   ├── Certificate.jsx # Public certificate verification page
        │   ├── Ledger.jsx    # Published checkpoints ("public ledger")
        │   └── HowItWorks.jsx # Plain-language explainer
        └── index.css         # Artisan-themed design system
```

## 🔐 Cryptographic Engine

| Concept | Implementation | What the User Sees |
|---|---|---|
| **Hash Chain** | SHA-256 linked records (`prev_hash → record_hash`) | Unbroken ownership timeline |
| **Digital Signatures** | Ed25519 — each transfer signed by outgoing custodian | "✓ Confirmed by [Name]" |
| **Merkle Proofs** | Binary Merkle tree over all custody records, published as numbered checkpoints | "✓ Sealed in the public ledger" |
| **Tamper Detection** | Hash recomputation + signature verification on page load | Green badge or red warning |

## 🚀 Quick Start

### ReMarket sale import

CraftProof reads completed sales from ReMarket using the certificate code. No seller or buyer CraftProof account ID is needed. Configure these **on the CraftProof backend**, using the same sale API key configured on the ReMarket server:

```text
REMARKET_API_URL=https://<your-remarket-host>
REMARKET_SALE_API_KEY=<shared ReMarket sale API key>
CRAFTPROOF_REMARKET_SYNC_KEY=<a separate secret for manual sync requests>
```

For local development, put these values in the Git-ignored `backend/.env.local` file, then run `./venv/Scripts/python.exe -m uvicorn main:app --env-file .env.local --host 127.0.0.1 --port 8002` from the `backend` folder on Windows. The local ReMarket URL is `http://127.0.0.1:8000`; a deployed CraftProof service needs a publicly reachable HTTPS ReMarket URL and its own private key settings.

CraftProof polls ReMarket once per minute while the backend is running. Set `REMARKET_SYNC_INTERVAL_SECONDS=0` to disable polling, or set a positive number of seconds to change the interval. To run a sync immediately:

```bash
curl -X POST https://<your-craftproof-backend>/integrations/remarket/sync \
  -H "X-Integration-Key: <CRAFTPROOF_REMARKET_SYNC_KEY>"
```

The response reports imported, already imported, and skipped sales. A missing certificate or an item title that does not match the certificate title is skipped and retried on the next sync. Titles are compared without regard to case or repeated spaces. Each imported order is recorded once, and the buyer name appears in the public certificate history. Buyer names are self reported by ReMarket; a matching certificate code and title cannot prove that the ReMarket seller was the rightful owner. ReMarket's current checkout is a demonstration without payment or handoff verification. The polling process runs only while CraftProof is awake, so an always-on deployment or an external scheduler calling the sync endpoint is needed for timely updates.

Run the import checks from `backend` with `python -m unittest -v test_remarket`.

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

### Demo data

Don't demo an empty app — seed three makers, two galleries and five pieces at different
stages of their journey (all accounts use the password `craftproof123`):

```bash
cd backend
source venv/bin/activate
python3 seed.py            # add demo data
python3 seed.py --reset    # or wipe the database and start clean
```

### Running the tests

```bash
cd backend
source venv/bin/activate
python3 test_crypto.py
```

12 tests covering the primitives (canonical JSON, hash sensitivity, signature rejection, Merkle
proofs with an odd leaf count, leaf/node domain separation) and the attacks the chain must
catch — edited records, deleted records, and a forgery where the attacker recomputes the hash
but still cannot produce the custodian's signature.

### Verifying independently

The green badge is computed by the server — so the server has to be trusted. `verify_cli.py`
removes that assumption: it pulls the raw proof data and re-checks every hash, signature and
Merkle proof locally.

```bash
cd backend
source venv/bin/activate
python3 verify_cli.py AB12CD34
```

It prints a pass/fail line per check per record, and exits non-zero if anything fails.

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

Reload the certificate page — the green badge turns red: **"⚠ WARNING: ALTERED RECORD — Record 0 content hash mismatch"**, and the altered step in the ownership timeline is called out individually.

Then run the independent verifier on the same certificate to show that the detection doesn't
depend on the server being honest:

```bash
python3 verify_cli.py AB12CD34
```

```
Record 0: 3 -> Self  (2026-06-12T08:08:19+00:00)
  [FAIL] content hash mismatch — this record was altered after signing
         stored:      d11cdcb870f4dd646b4cb2d5a6b13071cea76c13e3498518f620162941c6bd29
         recomputed:  a05d23cfdf050ef7e2a41ece93ed067fe03c0784aa372e1d7f4570ae6f50ab93
```

## 🛠️ API Endpoints

| Method | Endpoint | Auth | Purpose |
|---|---|---|---|
| `POST` | `/auth/signup` | No | Create account (keypair generated invisibly) |
| `POST` | `/auth/login` | No | Login, receive JWT |
| `POST` | `/pieces` | Yes | Register a new piece + genesis record |
| `GET` | `/pieces/mine` | Yes | List pieces you currently hold |
| `GET` | `/pieces/made` | Yes | List pieces you created, including ones handed on |
| `POST` | `/pieces/{id}/transfer` | Yes | Transfer to another user or external buyer |
| `GET` | `/c/{code}` | No | Public certificate with server-side verification, per-step results and ledger status |
| `GET` | `/c/{code}/proof` | No | Raw signed fields, hashes, public keys and Merkle proofs, for independent verification |
| `GET` | `/ledger/checkpoints` | No | Published Merkle roots with timestamps |
| `POST` | `/ledger/checkpoint` | No | Seal every record so far under a new Merkle root |
| `GET` | `/users` | No | List registered users |
| `POST` | `/admin/tamper/{piece_id}/{seq}` | No | Demo: silently alter a record |

## 📄 License

MIT
