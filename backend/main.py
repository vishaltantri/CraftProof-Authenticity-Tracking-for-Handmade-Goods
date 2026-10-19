import asyncio
import logging
import os
from contextlib import asynccontextmanager, suppress
from fastapi import FastAPI, Depends, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import string, random
from auth import get_password_hash, verify_password, create_access_token, get_current_user_id
from database import get_db
from crypto_utils import generate_keypair, pubkey_to_hex, sign
from core import verify_chain_detailed, create_checkpoint, list_checkpoints, get_inclusion_proof
from record import CustodyRecord, GENESIS_HASH
from remarket import require_sync_key, sync_sales
from seed import seed as seed_demo_data
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def seed_demo_if_empty():
    """First boot on a fresh database (e.g. every new Render deploy, where the
    disk starts empty): fill it with the demo makers, pieces and a ledger
    checkpoint so the deployed app never opens on a blank slate."""
    conn = get_db()
    try:
        is_empty = conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"] == 0
    finally:
        conn.close()
    if is_empty:
        print("[startup] Empty database — seeding demo makers, pieces and a checkpoint")
        seed_demo_data()


async def poll_remarket_sales(interval):
    while True:
        try:
            await asyncio.to_thread(sync_sales)
        except Exception:
            logging.exception("ReMarket sale sync failed")
        await asyncio.sleep(interval)


@asynccontextmanager
async def lifespan(app):
    seed_demo_if_empty()
    task = None
    if os.environ.get("REMARKET_API_URL") and os.environ.get("REMARKET_SALE_API_KEY"):
        interval = int(os.environ.get("REMARKET_SYNC_INTERVAL_SECONDS", "60"))
        if interval > 0:
            task = asyncio.create_task(poll_remarket_sales(interval))
    try:
        yield
    finally:
        if task:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task


app = FastAPI(
    title="CraftProof API",
    description=(
        "Public API for CraftProof — tamper-proof authenticity certificates for "
        "handmade goods. Verification endpoints are open and need no API key; "
        "write endpoints (registering pieces, transfers) need a bearer token from "
        "POST /auth/login. Interactive docs: /docs — raw schema: /openapi.json"
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    # Auth uses bearer tokens in the Authorization header, not cookies, so
    # credentialed requests are never needed — and wildcard origin + credentials
    # is an invalid combination per the CORS spec.
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- Pydantic models ----------

class SignupRequest(BaseModel):
    name: str
    email: str
    password: str
    role: str
    shop_name: Optional[str] = None

class LoginRequest(BaseModel):
    email: str
    password: str

class PieceRequest(BaseModel):
    title: str
    description: Optional[str] = ""
    materials: Optional[str] = ""

class TransferRequest(BaseModel):
    to_user_id: Optional[int] = None
    to_name: Optional[str] = None
    note: Optional[str] = ""

# ---------- Helpers ----------

def generate_certificate_code(conn):
    """Short, human-readable code for the QR URL. Retried until unused."""
    while True:
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        if not conn.execute("SELECT 1 FROM pieces WHERE certificate_code = ?", (code,)).fetchone():
            return code

# ---------- Auth ----------

@app.post("/auth/signup")
def signup(req: SignupRequest):
    email = req.email.strip().lower()
    if not req.name.strip():
        raise HTTPException(status_code=400, detail="Name is required")
    if len(req.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    if req.role not in ("maker", "seller"):
        raise HTTPException(status_code=400, detail="Role must be 'maker' or 'seller'")

    conn = get_db()
    try:
        existing = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        if existing:
            raise HTTPException(status_code=400, detail="Email already registered")

        sk, pk = generate_keypair()
        sk_hex = sk.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption()
        ).hex()
        pk_hex = pubkey_to_hex(pk)

        hashed_pw = get_password_hash(req.password)

        c = conn.cursor()
        c.execute(
            "INSERT INTO users (name, email, password_hash, role, shop_name, public_key, encrypted_privkey) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (req.name.strip(), email, hashed_pw, req.role, req.shop_name, pk_hex, sk_hex)
        )
        conn.commit()
        user_id = c.lastrowid

        token = create_access_token({"sub": user_id})
        return {"access_token": token, "user_id": user_id, "name": req.name, "role": req.role}
    finally:
        conn.close()

@app.post("/auth/login")
def login(req: LoginRequest):
    conn = get_db()
    try:
        user = conn.execute("SELECT id, password_hash, name, role FROM users WHERE email = ?", (req.email.strip().lower(),)).fetchone()
        if not user or not verify_password(req.password, user["password_hash"]):
            raise HTTPException(status_code=401, detail="Invalid credentials")

        token = create_access_token({"sub": user["id"]})
        return {"access_token": token, "user_id": user["id"], "name": user["name"], "role": user["role"]}
    finally:
        conn.close()

@app.get("/users")
def get_users():
    conn = get_db()
    try:
        users = conn.execute("SELECT id, name, role, shop_name FROM users").fetchall()
        return [{"id": u["id"], "name": u["name"], "role": u["role"], "shop_name": u["shop_name"]} for u in users]
    finally:
        conn.close()

# ---------- Pieces ----------

@app.post("/pieces")
def create_piece(req: PieceRequest, user_id: int = Depends(get_current_user_id)):
    conn = get_db()
    try:
        code = generate_certificate_code(conn)

        c = conn.cursor()
        c.execute(
            "INSERT INTO pieces (certificate_code, title, description, materials, made_by, current_owner_id) VALUES (?, ?, ?, ?, ?, ?)",
            (code, req.title, req.description, req.materials, user_id, user_id)
        )
        piece_id = c.lastrowid

        # Genesis custody record
        user = conn.execute("SELECT encrypted_privkey FROM users WHERE id = ?", (user_id,)).fetchone()
        sk = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(user["encrypted_privkey"]))

        rec = CustodyRecord(piece_id, 0, user_id, user_id, "Self", "Piece created", GENESIS_HASH)
        rec_hash = rec.compute_hash()
        sig = sign(sk, bytes.fromhex(rec_hash)).hex()

        c.execute(
            "INSERT INTO custody_records (piece_id, seq_index, from_user_id, to_user_id, to_name, note, timestamp, prev_hash, record_hash, signature) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (piece_id, 0, user_id, user_id, "Self", "Piece created", rec.timestamp, GENESIS_HASH, rec_hash, sig)
        )

        conn.commit()
        return {"status": "success", "certificate_code": code, "piece_id": piece_id}
    finally:
        conn.close()

@app.get("/pieces/mine")
def get_my_pieces(user_id: int = Depends(get_current_user_id)):
    conn = get_db()
    try:
        pieces = conn.execute("SELECT * FROM pieces WHERE current_owner_id = ?", (user_id,)).fetchall()
        return [dict(p) for p in pieces]
    finally:
        conn.close()

@app.get("/pieces/made")
def get_pieces_i_made(user_id: int = Depends(get_current_user_id)):
    """Everything this user created, including pieces already handed on.

    /pieces/mine only shows current holdings; a maker still wants to follow a
    piece after it leaves the studio.
    """
    conn = get_db()
    try:
        pieces = conn.execute('''
            SELECT p.*, u.name AS current_owner_name, u.shop_name AS current_owner_shop
            FROM pieces p LEFT JOIN users u ON p.current_owner_id = u.id
            WHERE p.made_by = ? ORDER BY p.id DESC
        ''', (user_id,)).fetchall()

        out = []
        for p in pieces:
            d = dict(p)
            last = conn.execute(
                "SELECT to_name, seq_index FROM custody_records WHERE piece_id = ? ORDER BY seq_index DESC LIMIT 1",
                (p["id"],)
            ).fetchone()
            d["holder"] = (d.pop("current_owner_shop", None) or d.pop("current_owner_name", None)
                           or (last["to_name"] if last else None) or "Unknown")
            d["transfers"] = last["seq_index"] if last else 0
            d["still_held"] = p["current_owner_id"] == user_id
            out.append(d)
        return out
    finally:
        conn.close()

# ---------- Transfer ----------

@app.post("/integrations/remarket/sync", tags=["Integrations"])
def sync_remarket_sales(x_integration_key: Optional[str] = Header(default=None)):
    """Pull completed ReMarket sales and append signed custody events by certificate code."""
    require_sync_key(x_integration_key)
    return sync_sales()

@app.post("/pieces/{piece_id}/transfer")
def transfer_piece(piece_id: int, req: TransferRequest, user_id: int = Depends(get_current_user_id)):
    conn = get_db()
    try:
        piece = conn.execute("SELECT current_owner_id FROM pieces WHERE id = ?", (piece_id,)).fetchone()
        if not piece or piece["current_owner_id"] != user_id:
            raise HTTPException(status_code=403, detail="You are not the current owner of this piece")

        if req.to_user_id == user_id:
            raise HTTPException(status_code=400, detail="You already hold this piece")
        if req.to_user_id:
            recipient = conn.execute("SELECT id FROM users WHERE id = ?", (req.to_user_id,)).fetchone()
            if not recipient:
                raise HTTPException(status_code=404, detail="Recipient not found")
        elif not (req.to_name or "").strip():
            raise HTTPException(status_code=400, detail="Enter the buyer's name")

        last_rec = conn.execute(
            "SELECT seq_index, record_hash FROM custody_records WHERE piece_id = ? ORDER BY seq_index DESC LIMIT 1",
            (piece_id,)
        ).fetchone()
        seq_index = last_rec["seq_index"] + 1
        prev_hash = last_rec["record_hash"]

        user = conn.execute("SELECT encrypted_privkey FROM users WHERE id = ?", (user_id,)).fetchone()
        sk = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(user["encrypted_privkey"]))

        to_name = req.to_name or "Unknown buyer"
        rec = CustodyRecord(piece_id, seq_index, user_id, req.to_user_id, to_name, req.note or "", prev_hash)
        rec_hash = rec.compute_hash()
        sig = sign(sk, bytes.fromhex(rec_hash)).hex()

        c = conn.cursor()
        c.execute(
            "INSERT INTO custody_records (piece_id, seq_index, from_user_id, to_user_id, to_name, note, timestamp, prev_hash, record_hash, signature) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (piece_id, seq_index, user_id, req.to_user_id, to_name, req.note or "", rec.timestamp, prev_hash, rec_hash, sig)
        )

        if req.to_user_id:
            c.execute("UPDATE pieces SET current_owner_id = ? WHERE id = ?", (req.to_user_id, piece_id))
        else:
            c.execute("UPDATE pieces SET current_owner_id = NULL WHERE id = ?", (piece_id,))

        conn.commit()
        return {"status": "success"}
    finally:
        conn.close()

# ---------- Public Certificate ----------

def _load_certificate(conn, code):
    piece = conn.execute("SELECT * FROM pieces WHERE certificate_code = ?", (code.strip().upper(),)).fetchone()
    if not piece:
        raise HTTPException(status_code=404, detail="Certificate not found")
    return piece

@app.get("/c/{code}")
def get_certificate(code: str):
    conn = get_db()
    try:
        piece = _load_certificate(conn, code)

        # Get maker name
        maker = conn.execute("SELECT name FROM users WHERE id = ?", (piece["made_by"],)).fetchone()
        maker_name = maker["name"] if maker else "Unknown"

        records = conn.execute('''
            SELECT c.*, u1.name as from_name, u2.name as to_account_name, u2.shop_name as to_shop_name
            FROM custody_records c
            LEFT JOIN users u1 ON c.from_user_id = u1.id
            LEFT JOIN users u2 ON c.to_user_id = u2.id
            WHERE c.piece_id = ? ORDER BY c.seq_index ASC
        ''', (piece["id"],)).fetchall()

        valid, reason, checks = verify_chain_detailed(piece["id"])
        checks_by_seq = {c["seq_index"]: c for c in checks}

        timeline = []
        anchored = 0
        for r in records:
            to_display = r["to_shop_name"] or r["to_account_name"] or r["to_name"] or "Unknown"
            chk = checks_by_seq.get(r["seq_index"], {})
            inclusion = get_inclusion_proof(r["record_hash"])
            if inclusion and inclusion["included"]:
                anchored += 1
            timeline.append({
                "seq_index": r["seq_index"],
                "from_name": r["from_name"],
                "to_name": to_display,
                "note": r["note"],
                "timestamp": r["timestamp"],
                "record_hash": r["record_hash"],
                "checks": chk,
                "checkpoint": inclusion["batch_index"] if inclusion and inclusion["included"] else None,
            })

        piece_dict = dict(piece)
        piece_dict["maker_name"] = maker_name

        return {
            "piece": piece_dict,
            "timeline": timeline,
            "verified": valid,
            "reason": reason,
            "ledger": {
                "anchored_records": anchored,
                "total_records": len(timeline),
                "fully_anchored": bool(timeline) and anchored == len(timeline),
            },
        }
    finally:
        conn.close()

@app.get("/c/{code}/proof")
def get_certificate_proof(code: str):
    """Everything a third party needs to re-verify this certificate themselves.

    Returns the exact signed fields, the record hashes, the signer public keys
    and the Merkle inclusion proofs — so nobody has to take the server's word
    for the green badge. See backend/verify_cli.py for a reference verifier.
    """
    conn = get_db()
    try:
        piece = _load_certificate(conn, code)
        records = conn.execute(
            "SELECT * FROM custody_records WHERE piece_id = ? ORDER BY seq_index ASC", (piece["id"],)
        ).fetchall()

        out = []
        for r in records:
            signer = conn.execute("SELECT name, public_key FROM users WHERE id = ?", (r["from_user_id"],)).fetchone()
            out.append({
                # These eight fields, canonically JSON-encoded, are what gets hashed.
                "signed_fields": {
                    "piece_id": r["piece_id"],
                    "seq_index": r["seq_index"],
                    "from_user_id": r["from_user_id"],
                    "to_user_id": r["to_user_id"],
                    "to_name": r["to_name"],
                    "note": r["note"],
                    "timestamp": r["timestamp"],
                    "prev_hash": r["prev_hash"],
                },
                "record_hash": r["record_hash"],
                "signature": r["signature"],
                "signer": {
                    "name": signer["name"] if signer else None,
                    "public_key": signer["public_key"] if signer else None,
                },
                "merkle": get_inclusion_proof(r["record_hash"]),
            })

        valid, reason, _ = verify_chain_detailed(piece["id"])
        return {
            "certificate_code": piece["certificate_code"],
            "piece_id": piece["id"],
            "algorithms": {
                "hash": "SHA-256 over canonical JSON (sorted keys, no whitespace)",
                "signature": "Ed25519 over the raw 32-byte record hash",
                "merkle": "SHA-256 binary tree, 0x00 leaf prefix / 0x01 node prefix, last node duplicated when odd",
                "genesis_prev_hash": GENESIS_HASH,
            },
            "records": out,
            "server_verdict": {"verified": valid, "reason": reason},
        }
    finally:
        conn.close()

# ---------- Public integration API ----------

@app.get("/api/verify/{code}", tags=["Public API"], summary="Verify a certificate by code")
def api_verify(code: str):
    """One-call authenticity check for third-party sites.

    Returns a plain-language verdict plus the piece's full ownership history —
    no API key, no cryptographic internals to parse. Integrators who want to
    re-verify the cryptography themselves should use /c/{code}/proof instead.
    """
    conn = get_db()
    try:
        piece = _load_certificate(conn, code)

        maker = conn.execute("SELECT name FROM users WHERE id = ?", (piece["made_by"],)).fetchone()
        records = conn.execute(
            "SELECT * FROM custody_records WHERE piece_id = ? ORDER BY seq_index ASC", (piece["id"],)
        ).fetchall()
        valid, reason, _ = verify_chain_detailed(piece["id"])

        holder = None
        if piece["current_owner_id"]:
            h = conn.execute("SELECT name, shop_name FROM users WHERE id = ?", (piece["current_owner_id"],)).fetchone()
            if h:
                holder = h["shop_name"] or h["name"]
        elif records:
            holder = records[-1]["to_name"]

        history = []
        anchored = 0
        for r in records:
            frm = conn.execute("SELECT name FROM users WHERE id = ?", (r["from_user_id"],)).fetchone()
            from_name = frm["name"] if frm else "Unknown"
            to = conn.execute("SELECT name, shop_name FROM users WHERE id = ?", (r["to_user_id"],)).fetchone() if r["to_user_id"] else None
            to_name = (to["shop_name"] or to["name"]) if to else (r["to_name"] or "Unknown")
            event = f"Created by {from_name}" if r["seq_index"] == 0 else f"{from_name} → {to_name}"
            inclusion = get_inclusion_proof(r["record_hash"])
            if inclusion and inclusion["included"]:
                anchored += 1
            history.append({
                "date": r["timestamp"],
                "event": event,
                "note": r["note"] or None,
            })

        return {
            "certificate_code": piece["certificate_code"],
            "authentic": valid,
            "reason": None if valid else reason,
            "piece": {
                "title": piece["title"],
                "description": piece["description"],
                "materials": piece["materials"],
                "maker": maker["name"] if maker else None,
                "created_at": records[0]["timestamp"] if records else None,
            },
            "current_holder": holder,
            "history": history,
            "ledger": {
                "records": len(records),
                "anchored": anchored,
            },
            "verify_url": f"/c/{piece['certificate_code']}",
        }
    finally:
        conn.close()

# ---------- Public ledger (Merkle checkpoints) ----------

@app.get("/ledger/checkpoints")
def get_checkpoints():
    return list_checkpoints()

@app.post("/ledger/checkpoint")
def publish_checkpoint():
    """Seal every record recorded so far under a single Merkle root."""
    result = create_checkpoint()
    if result is None:
        raise HTTPException(status_code=400, detail="Nothing to checkpoint yet")
    return result

# ---------- Tamper endpoint (admin/demo only) ----------

@app.post("/admin/tamper/{piece_id}/{seq_index}")
def tamper_record(piece_id: int, seq_index: int, new_note: str = "FORGED"):
    """Demo-only: directly alter a record's note without updating the hash/signature."""
    conn = get_db()
    try:
        conn.execute(
            "UPDATE custody_records SET note = ? WHERE piece_id = ? AND seq_index = ?",
            (new_note, piece_id, seq_index)
        )
        conn.commit()
        return {"status": "tampered", "message": f"Record {seq_index} of piece {piece_id} altered to: '{new_note}'"}
    finally:
        conn.close()
