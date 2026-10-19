# CraftProof — Authenticity Tracking for Handmade Goods
## Full-Stack Web App Plan (Maker → Seller → Buyer)

This is the concrete version of the earlier full-stack plan, aimed at real, non-technical users.
The cryptographic engine (hash chain + Ed25519 signatures + Merkle proofs) from your earlier
files is reused **unchanged** — what's new here is the product itself: what it's called, who uses
it, what they see, and how every crypto concept gets translated into plain language on screen.

**Core idea:** A maker (potter, woodworker, jeweler, painter) creates a digital "certificate" for
a handmade piece. When it's sold to a shop/gallery, and then to a final customer, each transfer is
recorded. Anyone — including someone with zero technical knowledge — can scan a QR code on the
item and instantly see: *who made it, its full ownership history, and a "Verified Authentic"
seal* that cannot be faked or silently edited.

---

## 1. The Golden Rule of This Project

> **Users should never see the words "hash," "signature," "Merkle," or "cryptography" anywhere
> in the product.** They should only ever see: "Verified ✓", "Certificate", "Ownership History",
> and "Report a Problem." All the cryptography from your earlier design docs happens invisibly
> underneath. Your report is where you explain the machinery; the product is where you hide it.

This single rule should guide every UI decision below.

---

## 2. Who Uses It (Personas)

| Persona | What they do | Tech comfort assumed |
|---|---|---|
| **Maker** | Creates a certificate for a new handmade piece (pottery, jewelry, art, furniture, textiles). Prints/attaches a QR code sticker to the item. | Low — should feel like filling out a simple form |
| **Seller** (shop, gallery, online marketplace) | Receives pieces from makers, marks them "in stock," and marks them "sold" to a buyer. | Low |
| **Buyer / Public** | Scans a QR code (on the item, its tag, or its packaging) to see the certificate — no account needed at all. | Zero — must work for literally anyone with a phone camera |
| **You (admin, for the demo)** | Can view raw system state, trigger a Merkle batch, or simulate tampering to show the demo catching it live. | N/A — this is your viva tool, not a real feature |

Note that **buyers never need an account** — verification is the one flow that must have zero
friction, since it's the moment that sells the whole product ("wow, I can actually check this is
real").

---

## 3. User Flows in Plain Language

### 3.1 Maker creates a piece
1. Maker logs in, clicks **"Register a New Piece."**
2. Fills a simple form: photo, title ("Hand-thrown ceramic vase"), materials, date made, short story/description.
3. Clicks **"Create Certificate."**
4. Behind the scenes: this creates the genesis custody record, signed with the maker's key. A **QR code** is generated, pointing to a public certificate page (`craftproof.app/c/AB12CD34`).
5. Maker downloads/prints the QR code as a small sticker or tag to attach to the physical piece.

### 3.2 Maker sells to a seller/gallery
1. Maker clicks **"Transfer to Seller"** on their piece's dashboard entry.
2. Picks the seller from a list (or enters the seller's CraftProof username/shop code).
3. Adds an optional note ("Delivered in person, 3rd March").
4. Clicks **"Confirm Transfer."**
5. Behind the scenes: a new signed custody record is appended, linked to the previous one.

### 3.3 Seller sells to a final customer
1. Seller finds the piece (scans its QR code, or searches their inventory).
2. Clicks **"Mark as Sold."**
3. Enters the buyer's name/email (buyer doesn't need to make an account — they're recorded as the final owner, not a system user with login access, unless they want one for future resale).
4. Confirms. This is the final custody record for now (until/unless the item is resold later).

### 3.4 Anyone verifies a piece
1. Anyone scans the QR code with their phone camera (no app needed — it's just a URL).
2. Lands on a public page: `craftproof.app/c/AB12CD34`
3. Sees:
   - A big green **"✓ Verified Authentic"** badge (or a red warning if something's wrong)
   - Photo, maker's name/story
   - A simple timeline: **Made by [Maker] → Sold to [Gallery Name] → Purchased by [Buyer]**, with dates
   - A small "How is this verified?" expandable section for curious users (this is your one chance to briefly, plainly explain the tech — see Section 8)
4. **No login, no app install, no jargon.**

### 3.5 Resale (stretch feature)
A buyer who registered can later resell their piece, becoming the "from" party in a new handoff —
this makes the system genuinely useful beyond first sale (e.g. secondhand art/craft marketplaces,
which have real authenticity problems today).

---

## 4. Translating Crypto Concepts Into UI Language

This table is one of the most valuable things you can put directly into your report — it shows
you understand both the crypto **and** the product/UX side, which is exactly what separates a
strong project from a purely academic one.

| Crypto concept (backend) | What the user sees (frontend) |
|---|---|
| Hash chain / `prev_hash` linkage | Nothing directly — it's what makes the ownership timeline provably "unbroken" |
| Digital signature by outgoing custodian | "Confirmed by [Maker/Seller name]" with a small checkmark next to their name |
| Record hash tamper-check failing | Red banner: **"⚠ This certificate's record has been altered and cannot be trusted."** |
| Merkle proof verification | Green badge: **"✓ Included in the public authenticity ledger"** |
| Published Merkle root | A small "Ledger Checkpoint #482 · 3rd March 2026" link, for the curious/technical visitor |
| The `/verify` stateless check | Runs silently the moment the certificate page loads — the user just sees the final green/red result |
| Key custody (Section 4 of the fullstack plan) | Completely invisible — happens at signup, user just picks a password |

---

## 5. Screens / Pages

| Page | Audience | Content |
|---|---|---|
| `/` (Landing page) | Everyone | Plain explanation: "CraftProof lets you prove a handmade piece is genuine, and see its full history — from the maker's hands to yours." + "Scan a certificate" search box + Sign-up CTA for makers/sellers |
| `/signup`, `/login` | Makers, Sellers | Simple form: name, email, password, role (Maker / Seller) |
| `/dashboard` | Makers, Sellers | List of pieces they currently hold, with "Register New Piece" / "Transfer" / "Mark as Sold" buttons |
| `/pieces/new` | Makers | Simple creation form (Section 3.1) |
| `/pieces/:id/transfer` | Makers, Sellers | Simple transfer form (Section 3.2/3.3) |
| `/c/:code` (**Certificate page**) | Everyone, no login | The public verification page — the heart of the product (Section 3.4) |
| `/ledger` | Curious/technical visitors | Public, friendly explanation of "checkpoints" (published Merkle roots) — optional, low priority |
| `/how-it-works` | Everyone | A short, plain-English explainer page — no jargon, maybe a simple diagram |

### Certificate page (`/c/:code`) — design this one carefully, it's the whole product

```
┌─────────────────────────────────────────┐
│  [Photo of the piece]                    │
│                                           │
│  "Hand-thrown Ceramic Vase"              │
│  by Meera Krishnan                        │
│                                           │
│   ✓  VERIFIED AUTHENTIC                  │
│                                           │
│  Ownership History                       │
│  ● Made by Meera Krishnan — 3 Mar 2026   │
│  ● Sold to Artisan Gallery — 10 Mar 2026 │
│  ● Purchased by You — 2 Apr 2026         │
│                                           │
│  [How is this verified? ▾]               │
└─────────────────────────────────────────┘
```

The "How is this verified?" expandable, in genuinely plain language (no jargon):
> "Every time this piece changed hands, the person handing it over digitally confirmed it — like
> a tamper-proof signature that can't be forged or edited after the fact. All these confirmations
> are also recorded in a shared public ledger, so even we (CraftProof) can't quietly alter this
> history without it being detectable."

That's your entire "explain hash chains + signatures + Merkle proofs to a non-technical person"
paragraph. It's honest, accurate, and jargon-free — a great thing to literally reuse in your
report's introduction as "how we communicated the cryptographic guarantees to end users."

---

## 6. Updated Data Model (renamed for the domain)

Same schema as the earlier full-stack plan, renamed for clarity:

```sql
CREATE TABLE users (
    id                SERIAL PRIMARY KEY,
    name              VARCHAR(128) NOT NULL,
    email             VARCHAR(128) UNIQUE NOT NULL,
    password_hash     VARCHAR(255) NOT NULL,
    role              VARCHAR(32) NOT NULL,   -- 'maker', 'seller', 'buyer'
    shop_name         VARCHAR(128),           -- only for sellers
    public_key        TEXT NOT NULL,
    encrypted_privkey TEXT NOT NULL,
    created_at        TIMESTAMP DEFAULT now()
);

CREATE TABLE pieces (
    id              SERIAL PRIMARY KEY,
    certificate_code VARCHAR(16) UNIQUE NOT NULL,   -- the short code in the QR URL, e.g. 'AB12CD34'
    title           VARCHAR(128) NOT NULL,
    description     TEXT,
    materials       VARCHAR(255),
    photo_url       TEXT,
    made_by         INTEGER REFERENCES users(id),
    created_at      TIMESTAMP DEFAULT now(),
    current_owner_id INTEGER REFERENCES users(id)
);

CREATE TABLE custody_records (
    id              SERIAL PRIMARY KEY,
    piece_id        INTEGER REFERENCES pieces(id),
    seq_index       INTEGER NOT NULL,
    from_user_id    INTEGER REFERENCES users(id),
    to_user_id      INTEGER REFERENCES users(id),      -- nullable if buyer has no account
    to_name         VARCHAR(128),                       -- plain name, used when buyer has no account
    note            TEXT,
    timestamp       TIMESTAMP NOT NULL,
    prev_hash       VARCHAR(64) NOT NULL,
    record_hash     VARCHAR(64) NOT NULL,
    signature       TEXT NOT NULL,
    UNIQUE(piece_id, seq_index)
);

CREATE TABLE merkle_batches (
    id              SERIAL PRIMARY KEY,
    batch_index     INTEGER UNIQUE NOT NULL,
    root_hash       VARCHAR(64) NOT NULL,
    record_ids      INTEGER[] NOT NULL,
    created_at      TIMESTAMP DEFAULT now()
);
```

Handling **buyers without accounts**: the final "sale to customer" step can record just a name
(`to_name`), with no `to_user_id` — the seller is still the one who signs that handoff (they're
the outgoing custodian confirming the sale happened), so the chain and signature model stay
intact even though the buyer isn't a system user. This is worth a sentence in your report: the
protocol only requires the **outgoing** party to sign, which is exactly what lets end customers
participate without ever creating an account.

---

## 7. QR Code Integration

- **Generation:** When a piece is created, generate its `certificate_code` (short random alphanumeric, e.g. 8 chars) and encode the URL `https://craftproof.app/c/{code}` as a QR code image.
  - Python: `qrcode` library — `pip install qrcode[pil]`
  - Or generate client-side in the browser with `qrcode.react` (React component) — avoids a backend image-generation step entirely, simplest option.
- **Display:** Show the QR code on the piece's dashboard page with a "Download / Print" button (PNG or a small printable label layout — even a simple PDF via `jsPDF` for a nicer sticker-sized printout).
- **Scanning:** No custom scanner needed — any phone's native camera app scans a QR code containing a URL and opens it directly in the browser. This is what makes verification frictionless for non-technical users; don't build a custom in-app scanner unless you have significant extra time.

---

## 8. API Endpoints (renamed)

| Method | Endpoint | Auth | Purpose |
|---|---|---|---|
| `POST` | `/auth/signup` | No | Create maker/seller account (keypair generated + encrypted invisibly) |
| `POST` | `/auth/login` | No | Login |
| `POST` | `/pieces` | Yes (maker) | Register a new piece → genesis record + QR code generated |
| `GET` | `/pieces/mine` | Yes | Dashboard: pieces the logged-in user currently holds |
| `POST` | `/pieces/{id}/transfer` | Yes (must be current holder) | Hand off to another maker/seller (or record a final sale to a named buyer) |
| `GET` | `/c/{code}` | No (public) | Full certificate data for the certificate page — this endpoint runs the full verification server-side and returns the pass/fail result alongside the display data |
| `GET` | `/c/{code}/proof` | No (public) | Raw record + Merkle proof + root, for anyone who wants to verify independently/offline (technical users, your viva demo) |
| `GET` | `/ledger/checkpoints` | No (public) | List of published Merkle roots with timestamps |

**Important UX detail:** `/c/{code}` should do the verification **server-side** and just return
`{"status": "verified"}` or `{"status": "tampered", "reason": "..."}` — don't make the browser do
crypto work for the main page, since your non-technical users' browsers/devices are the last place
you want to add complexity or failure points. Save client-side verification (if you build it at
all) for a "power user" toggle or the `/c/{code}/proof` endpoint aimed at technical visitors.

---

## 9. Build Order

Build on top of your already-working crypto core (`crypto_utils.py`, `record.py`, `chain.py`,
`merkle.py` from the earlier files — unchanged).

| Phase | Tasks |
|---|---|
| 1 | DB schema (Section 6) + auth (signup/login, invisible keypair generation) |
| 2 | "Register a new piece" flow + QR code generation |
| 3 | "Transfer" flow (maker → seller, seller → buyer-by-name) |
| 4 | `/c/{code}` public certificate endpoint — wire up server-side verification (reuse `chain.py` + `merkle.py` logic) |
| 5 | Merkle batch background job |
| 6 | Frontend: landing page, signup/login, dashboard |
| 7 | Frontend: **certificate page** — polish this one the most, it's the demo centerpiece |
| 8 | Frontend: transfer forms, QR download |
| 9 | Seed data: 2–3 makers, 2 sellers, 4–5 pieces walked through full journeys, so the demo doesn't start empty |
| 10 | Tamper-demo hook (admin-only): directly edit a `custody_records` row in the DB, then reload the certificate page live to show the red "altered" warning |
| 11 | Deploy (same approach as Section 11 of the fullstack plan) + print physical QR stickers if you want a genuinely tactile demo (put one on an actual object you bring to your viva!) |

---

## 10. Demo Script (Tailored to This Product)

This is a much stronger demo than a CLI script, because you can hand your phone to the examiner.

1. **Set the scene (30s):** "This is CraftProof — imagine an artisan pottery maker wants buyers to be able to verify their pieces are genuine and see who's owned them."
2. **Show the maker dashboard (30s):** A piece already registered, its QR code.
3. **Physically scan the QR code with your phone (30s)** — land on the certificate page live. This single moment is your best demo beat: a real phone camera, a real URL, a real result.
4. **Point out the ownership timeline and the green "Verified Authentic" badge (30s).**
5. **Open "How is this verified?" and read the plain-language explanation (30s)** — bridges into your technical explanation.
6. **Switch to admin view, tamper with a record directly in the database (1 min).**
7. **Reload the certificate page — show the badge turn red with a clear warning (30s).** This is the "wow" moment that proves the system actually works, not just looks nice.
8. **Briefly show `/c/{code}/proof` or a raw JSON view (30s)** — this is where you explain, for the technical audience (your examiners), exactly which crypto mechanism just caught the tampering: hash mismatch, signature check, or Merkle inclusion failure.
9. **Close (30s):** "Everything a buyer sees is in plain language — but underneath, every step is backed by digital signatures and a tamper-evident ledger, which I'll walk through in the report."

---

## 11. Report Structure Suggestion (Given the Product Framing)

1. **Problem & motivation** — counterfeit/misattributed handmade goods, buyers currently have no way to verify authenticity or provenance beyond "trust me."
2. **Threat model** (from the original design doc, Section 3) — adapt actor names to Maker/Seller/Buyer.
3. **Protocol design** — hash chain, signatures, Merkle proofs, with the crypto-choice justification table (Section 8/9 of the original design doc).
4. **UX design decisions** — Section 4 and 5 of this file: how cryptographic guarantees were translated into a non-technical interface, and why that separation matters (a good product must make trust *legible* to people who can't read the math).
5. **Implementation** — architecture diagram, module breakdown, key custody decision (Section 4 of the fullstack plan) and its tradeoffs.
6. **Testing / attack demonstration** — the tamper-detection tests and the live demo tampering scenario.
7. **Limitations & future work** — client-side key generation (Option 2), real PKI, resale flows, mobile app instead of browser QR scanning, rate-limiting/account security hardening.
