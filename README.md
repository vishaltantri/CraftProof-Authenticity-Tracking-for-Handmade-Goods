# CraftProof — Authenticity Tracking for Handmade Goods

A full-stack web application that lets artisans (potters, woodworkers, jewelers, painters) create tamper-evident digital certificates for their handmade pieces. When a piece is sold to a shop/gallery and then to a final customer, each transfer is cryptographically recorded. Anyone can scan a QR code and instantly verify: *who made it, its full ownership history, and whether it's genuinely authentic.*

> **Disclaimer:** Nothing in CraftProof makes history impossible to change — an attacker with
database access can always alter the copy of the data they hold (tamper-*proof* is not achievable
here). What the system guarantees is tamper-*evidence*: any alteration shows up as an explicit,
verifiable failure on the certificate, in the independent verifier, and — for latched checkpoints —
against an external anchor.

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
│   ├── tamper_demo.py    # Admin script to simulate database tampering
│   ├── keystore.py       # Password-encrypted signing keys (AES-256-GCM envelope; Argon2id or PBKDF2)
│   ├── security_config.py# JWT secret / demo-mode configuration with fail-late startup gate
│   ├── fingerprint.py    # Physical "paper fingerprint" descriptors + template store (CraftProof 2.0)
│   ├── clone_detection.py# Same-code history cross-check: catches re-scans of a cloned tag (2.0)
│   ├── anchoring.py      # External anchoring of Merkle roots: RFC 3161 TSA or Ed25519 journal (2.0)
│   └── test_*.py         # Cryptographic, fingerprint, clone-detection, anchoring test suites
├── experiments/          # Research harnesses (see experiments/data/README.md)
│   ├── harness.py        # Attack-matrix harness: plan's attacks A–J × architectures A/B/C/D/D+fp
│   ├── benchmarks.py     # E5 latency + E6 scaling benchmarks → CSV
│   ├── build_pairs.py    # Dataset kit: manifest.csv → experiment pair files
│   └── data/README.md    # Photography checklist, consent template, manifest spec
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
| **Key Protection** | Password-encrypted private keys (AES-256-GCM envelope; Argon2id or 1.2M-iteration PBKDF2) + in-memory unlock cache | (invisible) |
| **External Anchoring** | Checkpoint roots timestamped by an RFC 3161 TSA, or Ed25519-signed journal copy outside the DB | "✓ Sealed and timestamped" |
| **Physical Fingerprint** | Photo descriptors of the object bound into the signed genesis record (`cm` commitment) | "✓ Object matches" |
| **Clone Detection** | Every scan is cross-checked against the certificate's scan history | Red banner: possible forged copy |

## 🛒 ReMarket marketplace integration

[ReMarket](https://github.com/arpan-basak/ReMarket) is a secondhand marketplace. A seller can
attach a CraftProof certificate code to a listing; when the item sells, ReMarket knows two things
CraftProof does not — **who bought it** and **which order recorded the sale**.

The two systems meet in both directions:

| Direction | Who calls whom | What it does |
|---|---|---|
| **ReMarket → CraftProof** | ReMarket calls `GET /api/verify/{code}` | A product page shows the piece's real ownership history and authenticity verdict |
| **CraftProof → ReMarket** | CraftProof polls `GET /api/v1/sales` | A completed sale appends the buyer to the certificate's custody chain |

CraftProof is the API *client* for the sale feed: ReMarket never writes to CraftProof. The
contract lives in the partner repo's `CRAFTPROOF_INTEGRATION.md`.

### What the importer guarantees

* **Idempotence** — `remarket_imports.order_id` is a PRIMARY KEY written in the same transaction
  as the custody record, so replaying the feed can never append a sale twice.
* **Title agreement** — a sale only touches a certificate when the listing title matches the
  piece title (case- and whitespace-insensitive). A mismatch is skipped, logged and retried; a
  wrong or guessed code cannot rewrite an unrelated certificate.
* **Honest attribution** — imported records are signed by a dedicated integration service account,
  never by the previous owner, and are labelled *"Reported by ReMarket — not confirmed by the
  previous owner"* on the certificate page and in the API's `marketplace` block.
* **Cursor discipline** — the poll cursor only advances past sales that reached a terminal state,
  so a skipped sale is retried on every later sync instead of being lost.

### What it does *not* establish

A matching code and title is a safety check, **not proof of seller authority**. ReMarket's
checkout is a simulation with no payment and no physical handoff, and its buyer names are
self-reported. That is why an imported step never claims a custodian confirmed it.

### Configuration

Set these **on the CraftProof backend**, using the same sale API key configured on the ReMarket
server. Keep the key out of Git — set its value in the Render dashboard or a local `.env.local`:

| Variable | Purpose |
|---|---|
| `REMARKET_API_URL` | ReMarket base URL, e.g. `https://remarket-24rz.onrender.com` |
| `REMARKET_SALE_API_KEY` | The partner's shared bearer key (**secret**) |
| `CRAFTPROOF_REMARKET_SYNC_KEY` | Separate secret gating `POST /integrations/remarket/sync` |
| `REMARKET_SYNC_INTERVAL_SECONDS` | Poll interval, default `300`; `0` disables the poller |
| `CRAFTPROOF_REMARKET_KEY` | Path to the integration's Ed25519 signing key, kept off the DB volume |

```bash
cd backend
source venv/bin/activate
cp .env.local.example .env.local      # then fill in the real key
uvicorn main:app --port 8002 --env-file .env.local
```

The background poller only runs while the service is awake. On a free Render instance that sleeps,
point an external scheduler at the sync endpoint instead:

```bash
curl -X POST https://<your-craftproof-backend>/integrations/remarket/sync \
  -H "X-Integration-Key: $CRAFTPROOF_REMARKET_SYNC_KEY"
```

### Endpoints added

| Method | Endpoint | Auth | Purpose |
|---|---|---|---|
| `GET` | `/integrations/remarket/status` | No | Connection health and import counts (never any part of the key) |
| `GET` | `/integrations/remarket/imports` | No | Sales already written onto certificates |
| `POST` | `/integrations/remarket/sync` | `X-Integration-Key` | Run a sync now (for an external scheduler) |
| `POST` | `/integrations/remarket/sync-as-user` | Bearer | The dashboard's "Check for new sales" button |
| `GET` | `/integrations/remarket/feed` | Bearer | Read the partner's live feed without importing |
| `GET` | `/api/verify?codes=A,B,C` | No | Verify up to 50 certificates in one call, for a listing page |

The **ReMarket** page in the web app (`/marketplace`) shows the connection, what has been recorded,
and what the marketplace is currently reporting.

```bash
cd backend && source venv/bin/activate
python3 -m unittest -v test_remarket      # 15 tests
```

## 🚀 Quick Start

### Prerequisites
- Python 3.10+
- Node.js 18+

### Backend

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
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

The tamper endpoint exists for demos only — it is disabled unless the server was explicitly
started with `CRAFTPROOF_ALLOW_INSECURE_DEMO=true` (it answers `403` otherwise):

```bash
cd backend
source venv/bin/activate
CRAFTPROOF_ALLOW_INSECURE_DEMO=true python3 -m uvicorn main:app --port 8002 &
# ... then POST /admin/tamper/{piece_id}/{seq}
# or use the offline script against the DB directly:
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
| `POST` | `/pieces` | Yes | Register a new piece (optionally with its fingerprint commitment) |
| `POST` | `/pieces/with-fingerprint` | Yes | Register with a physical-fingerprint commitment (64-hex digest) |
| `POST` | `/pieces/{id}/transfer` | Yes | Transfer to another user or external buyer |
| `POST` | `/pieces/{code}/verify-object` | No | Compare a freshly captured object fingerprint against the enrolled one; records the scan and runs clone detection |
| `GET` | `/c/{code}` | No | Public certificate with server-side verification, per-step results, ledger status and any clone warning |
| `GET` | `/c/{code}/proof` | No | Raw signed fields, hashes, public keys and Merkle proofs, for independent verification (the fingerprint commitment is included in the signed fields when present) |
| `GET` | `/ledger/checkpoints` | No | Published Merkle roots with timestamps |
| `POST` | `/ledger/checkpoint` | No | Seal every record so far under a new Merkle root |
| `GET` | `/users` | No | List registered users |
| `POST` | `/admin/tamper/{piece_id}/{seq}` | — | Demo only: silently alter a record. Answers 403 unless `CRAFTPROOF_ALLOW_INSECURE_DEMO=true` |

## ⚙️ Configuration (environment variables)

| Variable | Default | Purpose |
|---|---|---|
| `CRAFTPROOF_DB` | `backend/craftproof.db` | SQLite database path |
| `JWT_SECRET_KEY` | — (**required**) | Secret for signing session tokens. Startup fails (503 on auth routes) unless a ≥32-char secret is set |
| `CRAFTPROOF_ALLOW_INSECURE_DEMO` | unset | Set to `true` ONLY for throwaway demos: installs a fixed demo JWT secret + enables `/admin/tamper`. Never in production |
| `JWT_ALGORITHM` | `HS256` | Token signing algorithm |
| `CRAFTPROOF_MATCH_THRESHOLD` | `0.70` | Object-fingerprint match threshold |
| `CRAFTPROOF_TEMPLATES_DIR` | `backend/templates` | Where enrolled object templates are stored |
| `CRAFTPROOF_ANCHOR_BACKEND` | `local` | `local` = Ed25519-signed journal; `freetsa` = real RFC 3161 timestamping |
| `CRAFTPROOF_TSA_URL` | `https://freetsa.org/tsr` | TSA endpoint (freetsa backend) |
| `CRAFTPROOF_ANCHOR_KEY` / `CRAFTPROOF_ANCHOR_JOURNAL` | `backend/anchoring/…` | Anchor key + journal paths — keep outside the DB volume so a DB exfiltration cannot rewrite history |
| `KEYSTORE_KDF`/envelope | auto | Key envelopes use Argon2id when `argon2-cffi` is installed, else PBKDF2-SHA256 (1.2M iterations) |

## 🔬 Research experiments (CraftProof 2.0)

The `experiments/` directory holds the paper's reproducible harnesses
(specified fully in `craftproof_research_paper_plan.md`):

```bash
cd backend && source venv/bin/activate
# E1: attack matrix (attacks A–J against architectures A/B/C/D/D+fp)
python3 ../experiments/harness.py --arch all --attack all --repetitions 3 \
    --out ../experiments/results/e1_results.jsonl \
    --summary-out ../experiments/results/e1_summary.json
# E5+E6: latency + scaling benchmarks → CSV
python3 ../experiments/benchmarks.py --tiers 1000 10000 \
    --out ../experiments/results/e5e6.csv
# E2 dataset kit: photography checklist + manifest → pair files
python3 ../experiments/build_pairs.py \
    --manifest ../experiments/data/manifest.csv \
    --photos-root ../experiments/data --out ../experiments/data
```

The attack harness produces the paper's defense matrix as machine-readable JSON —
see its module docstring for the architecture mapping. Test suites:
`test_crypto.py` (12), `test_fingerprint.py` (7), `test_clone_detection.py` (6),
`test_anchoring.py` (8) — run each with plain `python3 <file>`.

## 📄 License

MIT
