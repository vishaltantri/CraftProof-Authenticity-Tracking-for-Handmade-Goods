from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import string, random
from auth import get_password_hash, verify_password, create_access_token, get_current_user_id
from database import get_db
from crypto_utils import generate_keypair, pubkey_to_hex, sign
from core import verify_full_chain
from record import CustodyRecord, GENESIS_HASH
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
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

def generate_certificate_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))

# ---------- Auth ----------

@app.post("/auth/signup")
def signup(req: SignupRequest):
    conn = get_db()
    try:
        existing = conn.execute("SELECT id FROM users WHERE email = ?", (req.email,)).fetchone()
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
            (req.name, req.email, hashed_pw, req.role, req.shop_name, pk_hex, sk_hex)
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
        user = conn.execute("SELECT id, password_hash, name, role FROM users WHERE email = ?", (req.email,)).fetchone()
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
        code = generate_certificate_code()

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

# ---------- Transfer ----------

@app.post("/pieces/{piece_id}/transfer")
def transfer_piece(piece_id: int, req: TransferRequest, user_id: int = Depends(get_current_user_id)):
    conn = get_db()
    try:
        piece = conn.execute("SELECT current_owner_id FROM pieces WHERE id = ?", (piece_id,)).fetchone()
        if not piece or piece["current_owner_id"] != user_id:
            raise HTTPException(status_code=403, detail="You are not the current owner of this piece")

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

@app.get("/c/{code}")
def get_certificate(code: str):
    conn = get_db()
    try:
        piece = conn.execute("SELECT * FROM pieces WHERE certificate_code = ?", (code,)).fetchone()
        if not piece:
            raise HTTPException(status_code=404, detail="Certificate not found")

        # Get maker name
        maker = conn.execute("SELECT name FROM users WHERE id = ?", (piece["made_by"],)).fetchone()
        maker_name = maker["name"] if maker else "Unknown"

        records = conn.execute('''
            SELECT c.*, u1.name as from_name, u2.name as to_account_name
            FROM custody_records c
            LEFT JOIN users u1 ON c.from_user_id = u1.id
            LEFT JOIN users u2 ON c.to_user_id = u2.id
            WHERE c.piece_id = ? ORDER BY c.seq_index ASC
        ''', (piece["id"],)).fetchall()

        valid, reason = verify_full_chain(piece["id"])

        timeline = []
        for r in records:
            to_display = r["to_account_name"] or r["to_name"] or "Unknown"
            timeline.append({
                "seq_index": r["seq_index"],
                "from_name": r["from_name"],
                "to_name": to_display,
                "note": r["note"],
                "timestamp": r["timestamp"],
                "record_hash": r["record_hash"]
            })

        piece_dict = dict(piece)
        piece_dict["maker_name"] = maker_name

        return {
            "piece": piece_dict,
            "timeline": timeline,
            "verified": valid,
            "reason": reason
        }
    finally:
        conn.close()

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
